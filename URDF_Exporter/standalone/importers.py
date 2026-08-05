from __future__ import annotations

import json
import math
import os
import re
import shutil
from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

from URDF_Exporter.core.Structure import RobotStructure
from URDF_Exporter.standalone.adapters import InventorAdapterError, prepare_native_assembly
from URDF_Exporter.standalone.cad_snap import extract_occ_snap_features
from URDF_Exporter.standalone.occ_loader import load_ocp


GEOMETRY_EXTENSIONS = {".stl", ".step", ".stp", ".brep", ".iges", ".igs"}
MANIFEST_SUFFIX = ".petasos.json"
DEFAULT_DENSITY_KG_M3 = 1000.0
LENGTH_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "ft": 304.8,
}


class ImportFailure(ValueError):
    pass


@dataclass
class ImportedPart:
    part_id: str
    name: str
    source_file: str
    mesh_file: str
    position_mm: list[float]
    rotation_rpy: list[float]
    physical: dict[str, Any]
    material: str = "silver_default"
    cad_source_file: str | None = None
    snap_source: str | None = None
    snap_features: list[dict[str, Any]] | None = None


def safe_name(value: str, fallback: str = "part") -> str:
    value = value.strip()
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not cleaned:
        cleaned = f"{fallback}_{sha1(value.encode('utf-8')).hexdigest()[:7]}"
    if cleaned[0].isdigit():
        cleaned = f"{fallback}_{cleaned}"
    return cleaned


def _unique_name(candidate: str, used: set[str]) -> str:
    name = candidate
    index = 2
    while name in used:
        name = f"{candidate}_{index}"
        index += 1
    used.add(name)
    return name


def _vector(value: Any, default: list[float]) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != len(default):
        return list(default)
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return list(default)


def _rpy_matrix(rpy: list[float]) -> list[list[float]]:
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def _row_major_matrix(position: list[float], rpy: list[float], position_scale: float) -> list[float]:
    rotation = _rpy_matrix(rpy)
    return [
        rotation[0][0], rotation[0][1], rotation[0][2], position[0] * position_scale,
        rotation[1][0], rotation[1][1], rotation[1][2], position[1] * position_scale,
        rotation[2][0], rotation[2][1], rotation[2][2], position[2] * position_scale,
        0.0, 0.0, 0.0, 1.0,
    ]


def _three_matrix(position_mm: list[float], rpy: list[float]) -> list[float]:
    row = _row_major_matrix(position_mm, rpy, 1.0)
    return [
        row[0], row[4], row[8], row[12],
        row[1], row[5], row[9], row[13],
        row[2], row[6], row[10], row[14],
        row[3], row[7], row[11], row[15],
    ]


def _load_manifest(source_dir: str) -> dict[str, Any] | None:
    paths = sorted(
        (
            path
            for path in Path(source_dir).rglob("*")
            if path.is_file() and path.name.lower().endswith(MANIFEST_SUFFIX)
        ),
        key=lambda path: (len(path.relative_to(source_dir).parts), str(path).casefold()),
    )
    if not paths:
        return None
    path = paths[0]
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportFailure(f"조립 정보 파일을 읽을 수 없습니다: {exc}") from exc
    if data.get("format") != "petasos-assembly" or str(data.get("version")) != "1.0":
        raise ImportFailure("조립 정보는 Petasos Assembly Exchange 1.0 형식이어야 합니다.")
    if not isinstance(data.get("parts"), list):
        raise ImportFailure("조립 정보에 parts 배열이 필요합니다.")
    return data


def _matrix_identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matrix_multiply(
    left: list[list[float]],
    right: list[list[float]],
) -> list[list[float]]:
    return [
        [
            sum(left[row][pivot] * right[pivot][column] for pivot in range(4))
            for column in range(4)
        ]
        for row in range(4)
    ]


def _occurrence_matrix(location) -> list[list[float]]:
    transform = location.Transformation()
    return [
        [float(transform.Value(row, column)) for column in range(1, 5)]
        for row in range(1, 4)
    ] + [[0.0, 0.0, 0.0, 1.0]]


def _matrix_pose(matrix: list[list[float]]) -> tuple[list[float], list[float]]:
    rotation = [row[:3] for row in matrix[:3]]
    for column in range(3):
        length = math.sqrt(sum(rotation[row][column] ** 2 for row in range(3)))
        if length > 1e-12:
            for row in range(3):
                rotation[row][column] /= length
    pitch = math.asin(max(-1.0, min(1.0, -rotation[2][0])))
    if abs(math.cos(pitch)) > 1e-8:
        roll = math.atan2(rotation[2][1], rotation[2][2])
        yaw = math.atan2(rotation[1][0], rotation[0][0])
    else:
        roll = math.atan2(-rotation[1][2], rotation[1][1])
        yaw = 0.0
    return (
        [matrix[0][3], matrix[1][3], matrix[2][3]],
        [roll, pitch, yaw],
    )


def _step_schema(source_path: Path) -> str:
    try:
        header = source_path.read_text(encoding="latin-1", errors="ignore")[:65536]
    except OSError:
        return "STEP"
    match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", header, re.IGNORECASE)
    if not match:
        return "STEP"
    schema = match.group(1).upper()
    if "AP242" in schema:
        return "STEP AP242"
    if "AP214" in schema:
        return "STEP AP214"
    if "AP203" in schema or "CONFIG_CONTROL_DESIGN" in schema:
        return "STEP AP203"
    return f"STEP ({schema[:48]})"


def _xde_label_name(label) -> str:
    from OCP import TDataStd

    attribute = TDataStd.TDataStd_Name()
    if not label.FindAttribute(TDataStd.TDataStd_Name.GetID_s(), attribute):
        return ""
    try:
        return str(attribute.Get().ToExtString()).strip()
    except Exception:
        return ""


def _read_step_occurrences(source_path: Path) -> list[dict[str, Any]]:
    try:
        load_ocp()
        from OCP import IFSelect, STEPCAFControl, TCollection, TDF, TDocStd, XCAFDoc
    except ImportError as exc:
        raise ImportFailure(
            "STEP 조립품 입력에는 XDE를 포함한 cadquery-ocp 패키지가 필요합니다."
        ) from exc

    document = TDocStd.TDocStd_Document(
        TCollection.TCollection_ExtendedString("XmlXCAF")
    )
    reader = STEPCAFControl.STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetPropsMode(True)
    if reader.ReadFile(str(source_path)) != IFSelect.IFSelect_RetDone:
        raise ImportFailure(f"STEP 파일을 읽지 못했습니다: {source_path.name}")
    if not reader.Transfer(document):
        raise ImportFailure(f"STEP 조립 구조를 변환하지 못했습니다: {source_path.name}")

    shape_tool = XCAFDoc.XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free_shapes = TDF.TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_shapes)
    occurrences: list[dict[str, Any]] = []

    def visit(
        label,
        parent_matrix: list[list[float]],
        path_names: list[str],
        instance_name: str = "",
    ) -> None:
        if shape_tool.IsAssembly_s(label):
            components = TDF.TDF_LabelSequence()
            shape_tool.GetComponents_s(label, components, False)
            for component_index in range(1, components.Length() + 1):
                component = components.Value(component_index)
                referred = TDF.TDF_Label()
                if not shape_tool.GetReferredShape_s(component, referred):
                    continue
                local_matrix = _occurrence_matrix(
                    shape_tool.GetLocation_s(component)
                )
                component_name = _xde_label_name(component)
                referred_name = _xde_label_name(referred)
                chosen_name = component_name or referred_name or f"part_{len(occurrences) + 1}"
                visit(
                    referred,
                    _matrix_multiply(parent_matrix, local_matrix),
                    path_names + [chosen_name],
                    chosen_name,
                )
            return

        shape = shape_tool.GetShape_s(label)
        if shape.IsNull():
            return
        definition_name = _xde_label_name(label)
        name = instance_name or definition_name or f"part_{len(occurrences) + 1}"
        occurrences.append({
            "name": name,
            "path": path_names or [name],
            "shape": shape,
            "matrix": parent_matrix,
        })

    for root_index in range(1, free_shapes.Length() + 1):
        root = free_shapes.Value(root_index)
        root_name = _xde_label_name(root) or source_path.stem
        visit(root, _matrix_identity(), [root_name], root_name)
    return occurrences


def _prepare_step_assembly(source_dir: str, project_name: str) -> Path | None:
    root = Path(source_dir)
    step_paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".step", ".stp"}
        ),
        key=lambda path: (len(path.relative_to(root).parts), path.name.casefold()),
    )
    if not step_paths:
        return None

    candidates: list[tuple[Path, list[dict[str, Any]]]] = []
    failures: list[str] = []
    for path in step_paths:
        try:
            occurrences = _read_step_occurrences(path)
            if occurrences:
                candidates.append((path, occurrences))
        except ImportFailure as exc:
            failures.append(str(exc))
    if not candidates:
        if len(step_paths) == 1 and failures:
            raise ImportFailure(failures[0])
        return None

    assembly_candidates = [
        candidate for candidate in candidates if len(candidate[1]) > 1
    ]
    if assembly_candidates:
        source_path, occurrences = max(
            assembly_candidates,
            key=lambda candidate: len(candidate[1]),
        )
    elif len(step_paths) == 1:
        source_path, occurrences = candidates[0]
    else:
        return None

    generated_dir = root / ".petasos_step_parts"
    generated_dir.mkdir(parents=True, exist_ok=True)
    used_files: set[str] = set()
    parts = []
    from OCP import BRepTools

    for index, occurrence in enumerate(occurrences, 1):
        display_name = str(occurrence["name"] or f"part_{index}")
        file_stem = _unique_name(safe_name(display_name, f"part_{index}"), used_files)
        relative_geometry = Path(".petasos_step_parts") / f"{file_stem}.brep"
        output_path = root / relative_geometry
        if not BRepTools.BRepTools.Write_s(occurrence["shape"], str(output_path)):
            raise ImportFailure(f"{display_name}: STEP 부품 형상을 분리하지 못했습니다.")
        position, rotation = _matrix_pose(occurrence["matrix"])
        parts.append({
            "id": f"occurrence_{index}",
            "name": display_name,
            "geometry": relative_geometry.as_posix(),
            "transform": {
                "position": position,
                "rotation": rotation,
            },
            "assembly_path": [str(value) for value in occurrence["path"]],
        })

    schema = _step_schema(source_path)
    warnings = []
    if len(parts) == 1:
        warnings.append({
            "severity": "warning",
            "code": "flattened_step",
            "message": (
                f"{source_path.name}: STEP에서 조립 계층이나 복수 부품 인스턴스를 "
                "찾지 못했습니다. CAD에서 조립 구조 유지 및 단일 솔리드 결합 해제 "
                "옵션으로 다시 내보내세요."
            ),
        })
    manifest = {
        "format": "petasos-assembly",
        "version": "1.0",
        "source": {
            "application": f"OpenCascade XDE · {schema}",
            "document": source_path.name,
            "adapter": "opencascade_xde",
        },
        "assembly": {
            "name": project_name or source_path.stem,
            "units": "mm",
            "angle_units": "rad",
            "up_axis": "z",
            "handedness": "right",
        },
        "parts": parts,
        "joints": [],
        "warnings": warnings,
    }
    manifest_path = root / "step-assembly.petasos.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


def _load_mesh_physical(source_path: str, mesh_path: str) -> dict[str, Any]:
    try:
        import trimesh
    except ImportError as exc:
        raise ImportFailure("STL 입력에는 trimesh 패키지가 필요합니다.") from exc

    loaded = trimesh.load(source_path, force="mesh")
    if hasattr(loaded, "dump") and not hasattr(loaded, "vertices"):
        loaded = loaded.dump(concatenate=True)
    shutil.copy2(source_path, mesh_path)
    scaled = loaded.copy()
    scaled.apply_scale(0.001)
    if not scaled.is_watertight:
        return {
            "mass": 1.0,
            "center_of_mass": [0.0, 0.0, 0.0],
            "inertia": [0.01, 0.01, 0.01, 0.0, 0.0, 0.0],
            "density": DEFAULT_DENSITY_KG_M3,
            "provenance": "mesh_fallback",
            "confidence": 0.2,
        }
    inertia = (scaled.moment_inertia * DEFAULT_DENSITY_KG_M3)
    return {
        "mass": float(scaled.volume * DEFAULT_DENSITY_KG_M3),
        "center_of_mass": [float(value) for value in scaled.center_mass],
        "inertia": [
            float(inertia[0, 0]), float(inertia[1, 1]), float(inertia[2, 2]),
            float(inertia[0, 1]), float(inertia[0, 2]), float(inertia[1, 2]),
        ],
        "density": DEFAULT_DENSITY_KG_M3,
        "provenance": "mesh_estimate",
        "confidence": 0.7,
    }


def _load_occ_shape(source_path: str, extension: str):
    try:
        load_ocp()
        from OCP import BRep, BRepTools, IFSelect, IGESControl, STEPControl, TopoDS
    except ImportError as exc:
        raise ImportFailure("STEP/BREP/IGES 입력에는 cadquery-ocp 패키지가 필요합니다.") from exc

    if extension in {".step", ".stp"}:
        reader = STEPControl.STEPControl_Reader()
        if reader.ReadFile(source_path) != IFSelect.IFSelect_RetDone:
            raise ImportFailure(f"STEP 파일을 읽지 못했습니다: {os.path.basename(source_path)}")
        reader.TransferRoots()
        return reader.OneShape()
    if extension in {".iges", ".igs"}:
        reader = IGESControl.IGESControl_Reader()
        if reader.ReadFile(source_path) != IFSelect.IFSelect_RetDone:
            raise ImportFailure(f"IGES 파일을 읽지 못했습니다: {os.path.basename(source_path)}")
        reader.TransferRoots()
        return reader.OneShape()
    shape = TopoDS.TopoDS_Shape()
    builder = BRep.BRep_Builder()
    if not BRepTools.BRepTools.Read_s(shape, source_path, builder):
        raise ImportFailure(f"BREP 파일을 읽지 못했습니다: {os.path.basename(source_path)}")
    return shape


def _load_cad_details(
    source_path: str,
    extension: str,
    mesh_path: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[float]]:
    load_ocp()
    from OCP import BRepBndLib, BRepGProp, BRepMesh, Bnd, GProp, StlAPI

    shape = _load_occ_shape(source_path, extension)
    props = GProp.GProp_GProps()
    BRepGProp.BRepGProp.VolumeProperties_s(shape, props)
    volume_mm3 = float(props.Mass())
    center = props.CentreOfMass()
    inertia = props.MatrixOfInertia()
    bounds = Bnd.Bnd_Box()
    BRepBndLib.BRepBndLib.Add_s(shape, bounds)
    cad_bounds = [float(value) for value in bounds.Get()]
    if mesh_path:
        BRepMesh.BRepMesh_IncrementalMesh(shape, 0.5, False, 0.5, False)
        writer = StlAPI.StlAPI_Writer()
        writer.Write(shape, mesh_path)
    scale = DEFAULT_DENSITY_KG_M3 * 1e-15
    physical = {
        "mass": max(volume_mm3 * DEFAULT_DENSITY_KG_M3 * 1e-9, 1e-6),
        "center_of_mass": [
            float(center.X()) / 1000.0,
            float(center.Y()) / 1000.0,
            float(center.Z()) / 1000.0,
        ],
        "inertia": [
            float(inertia.Value(1, 1)) * scale,
            float(inertia.Value(2, 2)) * scale,
            float(inertia.Value(3, 3)) * scale,
            float(inertia.Value(1, 2)) * scale,
            float(inertia.Value(1, 3)) * scale,
            float(inertia.Value(2, 3)) * scale,
        ],
        "density": DEFAULT_DENSITY_KG_M3,
        "provenance": "cad_geometry_estimate",
        "confidence": 0.75,
    }
    return physical, extract_occ_snap_features(shape), cad_bounds


def _load_cad_physical(source_path: str, mesh_path: str, extension: str) -> dict[str, Any]:
    physical, _, _ = _load_cad_details(source_path, extension, mesh_path)
    return physical


def _align_snap_features_to_mesh(
    features: list[dict[str, Any]],
    cad_bounds: list[float],
    mesh_path: str,
) -> list[dict[str, Any]]:
    """Match neutral-CAD local coordinates to a unitless STL preview."""

    if not features or len(cad_bounds) != 6:
        return features
    try:
        import trimesh

        mesh = trimesh.load(mesh_path, force="mesh")
        if hasattr(mesh, "dump") and not hasattr(mesh, "vertices"):
            mesh = mesh.dump(concatenate=True)
        mesh_bounds = mesh.bounds
        mesh_min = [float(value) for value in mesh_bounds[0]]
        mesh_max = [float(value) for value in mesh_bounds[1]]
    except Exception:
        return features

    cad_min = cad_bounds[:3]
    cad_max = cad_bounds[3:]
    cad_size = [cad_max[index] - cad_min[index] for index in range(3)]
    mesh_size = [mesh_max[index] - mesh_min[index] for index in range(3)]
    cad_diagonal = math.sqrt(sum(value * value for value in cad_size))
    mesh_diagonal = math.sqrt(sum(value * value for value in mesh_size))
    if cad_diagonal <= 1e-12 or mesh_diagonal <= 1e-12:
        return features
    scale = mesh_diagonal / cad_diagonal
    if not math.isfinite(scale) or scale <= 1e-9 or scale >= 1e9:
        return features
    cad_center = [
        (cad_min[index] + cad_max[index]) / 2.0 for index in range(3)
    ]
    mesh_center = [
        (mesh_min[index] + mesh_max[index]) / 2.0 for index in range(3)
    ]
    offset = [
        mesh_center[index] - cad_center[index] * scale for index in range(3)
    ]
    aligned: list[dict[str, Any]] = []
    for raw_feature in features:
        feature = dict(raw_feature)
        position = _vector(feature.get("position"), [0.0, 0.0, 0.0])
        feature["position"] = [
            position[index] * scale + offset[index] for index in range(3)
        ]
        if feature.get("radius") is not None:
            feature["radius"] = float(feature["radius"]) * abs(scale)
        feature["cad_to_mesh_scale"] = scale
        aligned.append(feature)
    return aligned


def _manifest_physical(spec: dict[str, Any], length_to_mm: float) -> dict[str, Any] | None:
    physical = spec.get("physical")
    if not isinstance(physical, dict):
        return None
    raw_inertia = physical.get("inertia")
    if not isinstance(raw_inertia, (list, tuple)) or len(raw_inertia) != 6:
        return None
    try:
        inertia = [float(value) for value in raw_inertia]
    except (TypeError, ValueError):
        return None
    try:
        mass = float(physical["mass"])
    except (KeyError, TypeError, ValueError):
        return None
    if mass <= 0:
        return None
    center = _vector(physical.get("center_of_mass"), [0.0, 0.0, 0.0])
    return {
        "mass": mass,
        "center_of_mass": [value * length_to_mm / 1000.0 for value in center],
        "inertia": inertia,
        "density": physical.get("density"),
        "provenance": "cad_metadata",
        "confidence": float(physical.get("confidence", 1.0)),
    }


def _part_spec_transform(spec: dict[str, Any], length_to_mm: float, degrees: bool) -> tuple[list[float], list[float]]:
    transform = spec.get("transform") if isinstance(spec.get("transform"), dict) else {}
    position = [value * length_to_mm for value in _vector(transform.get("position"), [0.0, 0.0, 0.0])]
    rotation = _vector(transform.get("rotation"), [0.0, 0.0, 0.0])
    if degrees:
        rotation = [math.radians(value) for value in rotation]
    return position, rotation


def build_project(source_dir: str, mesh_dir: str, project_name: str) -> dict[str, Any]:
    os.makedirs(mesh_dir, exist_ok=True)
    manifest = _load_manifest(source_dir)
    if manifest is None:
        _prepare_step_assembly(source_dir, project_name)
        manifest = _load_manifest(source_dir)
    if manifest is None:
        try:
            prepare_native_assembly(source_dir, project_name)
        except InventorAdapterError as exc:
            raise ImportFailure(str(exc)) from exc
        manifest = _load_manifest(source_dir)
    geometry_names = sorted(
        str(path.relative_to(source_dir))
        for path in Path(source_dir).rglob("*")
        if path.is_file() and path.suffix.lower() in GEOMETRY_EXTENSIONS
    )
    if not geometry_names:
        raise ImportFailure("지원되는 형상 파일이 없습니다.")

    geometry_lookup = {os.path.basename(name).casefold(): name for name in geometry_names}
    assembly = manifest.get("assembly", {}) if manifest else {}
    source_application = str(
        (manifest or {}).get("source", {}).get("application", "Neutral CAD")
    )
    source_adapter = str((manifest or {}).get("source", {}).get("adapter", ""))
    is_inventor_source = "inventor" in source_application.casefold()
    is_position_only_source = (
        is_inventor_source or source_adapter.casefold() == "opencascade_xde"
    )
    units = str(assembly.get("units", "mm")).lower()
    if units not in LENGTH_TO_MM:
        raise ImportFailure(f"지원하지 않는 길이 단위입니다: {units}")
    length_to_mm = LENGTH_TO_MM[units]
    angle_units = str(assembly.get("angle_units", "rad")).lower()
    if angle_units not in {"rad", "deg"}:
        raise ImportFailure("angle_units는 rad 또는 deg여야 합니다.")
    degrees = angle_units == "deg"

    specs = manifest.get("parts", []) if manifest else [
        {"id": os.path.splitext(name)[0], "name": os.path.splitext(name)[0], "geometry": name}
        for name in geometry_names
    ]
    warnings: list[dict[str, Any]] = [
        item
        for item in ((manifest or {}).get("warnings") or [])
        if isinstance(item, dict)
    ]
    used_names: set[str] = set()
    parts: list[ImportedPart] = []
    part_id_to_name: dict[str, str] = {}

    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            continue
        part_id = str(spec.get("id") or f"part_{index + 1}")
        geometry_key = os.path.basename(str(spec.get("geometry") or "")).casefold()
        source_name = geometry_lookup.get(geometry_key)
        display_name = str(spec.get("name") or spec.get("geometry") or part_id)
        if not source_name:
            warnings.append({
                "severity": "error",
                "code": "missing_geometry",
                "message": f"{display_name}: 연결된 형상 파일이 없습니다.",
            })
            continue
        name = _unique_name(safe_name(display_name), used_names)
        source_path = os.path.join(source_dir, source_name)
        mesh_path = os.path.join(mesh_dir, name + ".stl")
        extension = os.path.splitext(source_name)[1].lower()
        cad_source_name: str | None = None
        cad_source_path: str | None = None
        snap_features: list[dict[str, Any]] = []
        if extension == ".stl":
            physical = _load_mesh_physical(source_path, mesh_path)
            cad_geometry_key = os.path.basename(
                str(spec.get("cad_geometry") or "")
            ).casefold()
            cad_source_name = geometry_lookup.get(cad_geometry_key)
            if cad_source_name:
                cad_extension = os.path.splitext(cad_source_name)[1].lower()
                if cad_extension != ".stl":
                    cad_source_path = os.path.join(source_dir, cad_source_name)
                    try:
                        _, snap_features, cad_bounds = _load_cad_details(
                            cad_source_path,
                            cad_extension,
                        )
                        snap_features = _align_snap_features_to_mesh(
                            snap_features,
                            cad_bounds,
                            mesh_path,
                        )
                    except Exception as exc:
                        warnings.append({
                            "severity": "warning",
                            "code": "cad_snap_unavailable",
                            "message": (
                                f"{display_name}: CAD 스냅 형상을 읽지 못해 "
                                f"메쉬 추정으로 대체합니다. ({exc})"
                            ),
                        })
                        cad_source_name = None
        else:
            cad_source_name = source_name
            cad_source_path = source_path
            physical, snap_features, cad_bounds = _load_cad_details(
                source_path,
                extension,
                mesh_path,
            )
            snap_features = _align_snap_features_to_mesh(
                snap_features,
                cad_bounds,
                mesh_path,
            )
        manifest_physical = _manifest_physical(spec, length_to_mm)
        if manifest_physical:
            physical = manifest_physical
        else:
            warnings.append({
                "severity": "warning",
                "code": "estimated_physical",
                "message": f"{display_name}: 질량과 관성을 기본 밀도 {DEFAULT_DENSITY_KG_M3:g} kg/m³로 추정했습니다.",
            })
        position, rotation = _part_spec_transform(spec, length_to_mm, degrees)
        material = safe_name(str(spec.get("material", "silver_default")), "material")
        part = ImportedPart(
            part_id=part_id,
            name=name,
            source_file=source_name,
            mesh_file=os.path.basename(mesh_path),
            position_mm=position,
            rotation_rpy=rotation,
            physical=physical,
            material=material,
            cad_source_file=cad_source_name,
            snap_source="opencascade" if snap_features else None,
            snap_features=snap_features,
        )
        parts.append(part)
        part_id_to_name[part_id] = name

    if not parts:
        raise ImportFailure("가져올 수 있는 부품이 없습니다.")

    joints: dict[str, dict[str, Any]] = {}
    active_joint_count = 0
    rigid_group_candidate_count = 0
    recovered_connection_count = 0
    manifest_joints = manifest.get("joints", []) if manifest else []
    for index, joint in enumerate(manifest_joints):
        if not isinstance(joint, dict):
            continue
        parent = part_id_to_name.get(str(joint.get("parent", "")))
        child = part_id_to_name.get(str(joint.get("child", "")))
        if not parent or not child or parent == child:
            warnings.append({
                "severity": "warning",
                "code": "invalid_joint",
                "message": f"{joint.get('name', f'joint_{index + 1}')}: 연결 부품을 찾을 수 없어 건너뛰었습니다.",
            })
            continue
        origin = joint.get("origin") if isinstance(joint.get("origin"), dict) else {}
        xyz = [value * length_to_mm / 1000.0 for value in _vector(origin.get("xyz"), [0.0, 0.0, 0.0])]
        rpy = _vector(origin.get("rpy"), [0.0, 0.0, 0.0])
        if degrees:
            rpy = [math.radians(value) for value in rpy]
        joint_type = str(joint.get("type", "fixed")).lower()
        if joint_type not in {"fixed", "revolute", "continuous", "prismatic"}:
            joint_type = "fixed"
        limits = joint.get("limits") if isinstance(joint.get("limits"), dict) else {}
        lower = float(limits.get("lower", 0.0))
        upper = float(limits.get("upper", 0.0))
        if degrees and joint_type == "revolute":
            lower, upper = math.radians(lower), math.radians(upper)
        elif joint_type == "prismatic":
            lower *= length_to_mm / 1000.0
            upper *= length_to_mm / 1000.0
        joint_name = _unique_name(safe_name(str(joint.get("name") or f"joint_{index + 1}"), "joint"), set(joints))
        provenance = str(joint.get("provenance") or "cad_metadata")
        provenance_key = provenance.casefold()
        if is_position_only_source and joint_type == "fixed":
            if "recovered" in provenance_key or "disconnected" in provenance_key:
                recovered_connection_count += 1
            else:
                # Inventor fixed constraints describe a rigid placement, not a
                # kinematic URDF joint. Keep the edge only so every occurrence
                # remains visible at its imported absolute pose in the editor.
                provenance = "inventor_fixed_group_candidate"
                rigid_group_candidate_count += 1
        elif "recovered" in provenance_key or "disconnected" in provenance_key:
            recovered_connection_count += 1
        else:
            active_joint_count += 1
        joints[joint_name] = {
            "parent": parent,
            "child": child,
            "type": joint_type,
            "xyz": xyz,
            "rpy": rpy,
            "_manual_rpy": rpy,
            "axis": _vector(joint.get("axis"), [0.0, 0.0, 1.0]),
            "lower_limit": lower,
            "upper_limit": upper,
            "provenance": provenance,
        }

    part_by_name = {part.name: part for part in parts}
    if not joints and len(parts) > 1:
        root = parts[0]
        for index, child in enumerate(parts[1:], 1):
            joints[f"recovered_joint_{index}"] = {
                "parent": root.name,
                "child": child.name,
                "type": "fixed",
                "xyz": [
                    (child.position_mm[i] - root.position_mm[i]) / 1000.0
                    for i in range(3)
                ],
                "rpy": child.rotation_rpy,
                "_manual_rpy": child.rotation_rpy,
                "axis": [0.0, 0.0, 1.0],
                "lower_limit": 0.0,
                "upper_limit": 0.0,
                "provenance": "recovered",
            }
            recovered_connection_count += 1
        warnings.append({
            "severity": "warning",
            "code": "recovered_topology",
            "message": "조인트 정보가 없어 첫 부품을 기준으로 고정 조인트를 생성했습니다.",
        })

    children = {info["child"] for info in joints.values()}
    root_name = next((part.name for part in parts if part.name not in children), parts[0].name)
    existing_links = {root_name} | children | {info["parent"] for info in joints.values()}
    recovery_index = 1
    for part in parts:
        if part.name in existing_links:
            continue
        root = part_by_name[root_name]
        joint_name = f"recovered_root_{recovery_index}"
        recovery_index += 1
        joints[joint_name] = {
            "parent": root_name,
            "child": part.name,
            "type": "fixed",
            "xyz": [(part.position_mm[i] - root.position_mm[i]) / 1000.0 for i in range(3)],
            "rpy": part.rotation_rpy,
            "_manual_rpy": part.rotation_rpy,
            "axis": [0.0, 0.0, 1.0],
            "lower_limit": 0.0,
            "upper_limit": 0.0,
            "provenance": "recovered",
        }
        recovered_connection_count += 1
        warnings.append({
            "severity": "warning",
            "code": "disconnected_part",
            "message": f"{part.name}: 연결 정보가 없어 루트에 고정했습니다.",
        })

    inertial = {part.name: part.physical for part in parts}
    materials = {part.name: {"material": part.material} for part in parts}
    colors = {"silver_default": "0.700 0.700 0.700 1.000"}
    visual_transforms = {
        part.name: _row_major_matrix(part.position_mm, part.rotation_rpy, 0.001)
        for part in parts
    }
    preview_transforms = {
        part.name: _three_matrix(part.position_mm, part.rotation_rpy)
        for part in parts
    }
    cad_snap_features = {
        part.name: {
            "source": part.snap_source,
            "cad_file": part.cad_source_file,
            "features": part.snap_features or [],
        }
        for part in parts
        if part.snap_features
    }
    structure = RobotStructure(joints, inertial, materials, visual_transforms)
    tree = structure.build_tree_data()
    assembly_info = (manifest or {}).get("assembly", {})
    preview_up_axis = str(assembly_info.get("up_axis", "z")).lower()
    if preview_up_axis not in {"x", "y", "z"}:
        preview_up_axis = "z"
    if is_position_only_source and (rigid_group_candidate_count or recovered_connection_count):
        warnings.append({
            "severity": "warning",
            "code": "position_only_safe_topology",
            "message": (
                "CAD 형상과 조립 위치만 유지했습니다. fixed/복구 연결은 URDF 조인트로 "
                "사용하지 않습니다. 함께 움직이는 부품을 하나의 링크로 그룹화한 뒤 "
                "실제 회전·직선 조인트만 다시 연결하세요."
            ),
        })

    tree.update({
        "_standalone": True,
        "_project_name": safe_name(project_name, "robot"),
        "_preview_transforms": preview_transforms,
        "_preview_units_per_meter": 1000.0,
        "_preview_up_axis": preview_up_axis,
        "_cad_snap_features": cad_snap_features,
        "_import_report": {
            "source_application": source_application,
            "parts": len(parts),
            "joints": len(joints),
            "active_joints": active_joint_count,
            "rigid_group_candidates": rigid_group_candidate_count,
            "recovered_connections": recovered_connection_count,
            "cad_snap_parts": len(cad_snap_features),
            "cad_snap_features": sum(
                len(item["features"]) for item in cad_snap_features.values()
            ),
            "import_mode": (
                "inventor_safe"
                if is_inventor_source
                else (
                    "step_xde_position_only"
                    if is_position_only_source
                    else "standard"
                )
            ),
            "warnings": warnings,
            "has_errors": any(item["severity"] == "error" for item in warnings),
        },
    })
    return {
        "project_name": safe_name(project_name, "robot"),
        "tree": tree,
        "joints": joints,
        "inertial": inertial,
        "materials": materials,
        "colors": colors,
        "visual_transforms": visual_transforms,
        "parts": [asdict(part) for part in parts],
        "report": tree["_import_report"],
    }
