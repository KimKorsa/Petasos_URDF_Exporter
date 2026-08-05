from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Inventor native assemblies and foreign assembly formats handled by Inventor
# translators/AnyCAD. Referenced part formats are accepted as upload dependencies.
INVENTOR_NATIVE_ASSEMBLY_EXTENSIONS = {
    ".iam",
    ".sldasm",
    ".catproduct",
    ".asm",
    ".jt",
    ".3dxml",
}
INVENTOR_OPTIONAL_ASSEMBLY_EXTENSIONS = {
    ".step",
    ".stp",
    ".prt",
    ".x_t",
    ".x_b",
    ".sat",
    ".sab",
}
INVENTOR_ASSEMBLY_EXTENSIONS = (
    INVENTOR_NATIVE_ASSEMBLY_EXTENSIONS | INVENTOR_OPTIONAL_ASSEMBLY_EXTENSIONS
)
INVENTOR_DEPENDENCY_EXTENSIONS = {
    ".ipt",
    ".sldprt",
    ".catpart",
    ".prt",
    ".par",
    ".psm",
    ".x_t",
    ".x_b",
    ".sat",
    ".sab",
}

STL_TRANSLATOR_ID = "{533E9A98-FC3B-11D4-8E7E-0010B541CD80}"
STEP_TRANSLATOR_ID = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"
K_FILE_BROWSE_IO_MECHANISM = 13059
JOINT_TYPES = {
    102401: "fixed",       # kRigidJointType
    102402: "revolute",    # kRotationalJointType
    102403: "prismatic",   # kSlideJointType
    102404: "continuous",  # kCylindricalJointType (rotation retained)
    102405: "fixed",       # kPlanarJointType: not representable by one URDF joint
    102406: "fixed",       # kBallJointType: not representable by one URDF joint
}


class InventorAdapterError(RuntimeError):
    pass


def _safe_name(value: str, fallback: str = "part") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    if not cleaned:
        cleaned = fallback
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


def _collection_items(collection) -> list[Any]:
    try:
        count = int(collection.Count)
    except Exception:
        return []
    result = []
    for index in range(1, count + 1):
        try:
            result.append(collection.Item(index))
        except Exception:
            continue
    return result


def _reference_status(document) -> tuple[list[str], list[str]]:
    references: list[str] = []
    missing: list[str] = []
    try:
        descriptors = _collection_items(document.File.ReferencedFileDescriptors)
    except Exception:
        descriptors = []
    for descriptor in descriptors:
        try:
            full_name = str(descriptor.FullFileName)
        except Exception:
            full_name = ""
        name = Path(full_name).name or full_name or "알 수 없는 참조"
        references.append(name)
        try:
            if bool(descriptor.ReferenceMissing):
                missing.append(name)
        except Exception:
            pass
    return references, missing


def _inventor_error_text(exc: Exception) -> str:
    try:
        excepinfo = getattr(exc, "excepinfo", None)
        if excepinfo:
            description = excepinfo[2]
            if description:
                return str(description)
    except Exception:
        pass
    text = str(exc)
    if "-2147467259" in text:
        return "Inventor가 요청을 완료하지 못했습니다"
    return text


def matrix_values(matrix) -> list[list[float]]:
    """Return an Inventor Matrix as a conventional row-major 4x4 matrix."""
    try:
        raw = list(matrix.GetMatrixData())
        if len(raw) == 16:
            return [
                [float(raw[row * 4 + column]) for column in range(4)]
                for row in range(4)
            ]
    except Exception:
        pass
    try:
        return [
            [float(matrix.Cell(row, column)) for column in range(1, 5)]
            for row in range(1, 5)
        ]
    except Exception as exc:
        raise InventorAdapterError("Inventor 부품 배치 행렬을 읽지 못했습니다.") from exc


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matrix_inverse_rigid(matrix: list[list[float]]) -> list[list[float]]:
    rotation_t = [[matrix[column][row] for column in range(3)] for row in range(3)]
    translation = [matrix[row][3] for row in range(3)]
    inverse_translation = [
        -sum(rotation_t[row][column] * translation[column] for column in range(3))
        for row in range(3)
    ]
    return [
        rotation_t[0] + [inverse_translation[0]],
        rotation_t[1] + [inverse_translation[1]],
        rotation_t[2] + [inverse_translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(left[row][inner] * right[inner][column] for inner in range(4))
            for column in range(4)
        ]
        for row in range(4)
    ]


def _matrix_rpy(matrix: list[list[float]]) -> list[float]:
    pitch = math.atan2(
        -matrix[2][0],
        math.sqrt(matrix[0][0] ** 2 + matrix[1][0] ** 2),
    )
    if abs(math.cos(pitch)) > 1e-9:
        roll = math.atan2(matrix[2][1], matrix[2][2])
        yaw = math.atan2(matrix[1][0], matrix[0][0])
    else:
        roll = math.atan2(-matrix[1][2], matrix[1][1])
        yaw = 0.0
    return [roll, pitch, yaw]


def matrix_transform(matrix: list[list[float]], length_scale: float = 10.0) -> dict[str, list[float]]:
    """Convert Inventor database centimeters into manifest millimeters."""
    return {
        "position": [matrix[row][3] * length_scale for row in range(3)],
        "rotation": _matrix_rpy(matrix),
    }


def relative_transform(
    parent: list[list[float]],
    child: list[list[float]],
    length_scale: float = 10.0,
) -> dict[str, list[float]]:
    return matrix_transform(
        _matrix_multiply(_matrix_inverse_rigid(parent), child),
        length_scale,
    )


def _occurrence_name(occurrence) -> str:
    try:
        return str(occurrence.Name)
    except Exception:
        return "component"


def _occurrence_suppressed(occurrence) -> bool:
    try:
        return bool(occurrence.Suppressed)
    except Exception:
        return False


def _occurrence_grounded(occurrence) -> bool:
    try:
        return bool(occurrence.Grounded)
    except Exception:
        return False


def _occurrence_document(occurrence):
    try:
        return occurrence.Definition.Document
    except Exception:
        return None


def _appearance_name(occurrence) -> str:
    try:
        return _safe_name(str(occurrence.Appearance.DisplayName), "silver_default")
    except Exception:
        return "silver_default"


def _mass_properties(part_document) -> dict[str, Any] | None:
    try:
        props = part_document.ComponentDefinition.MassProperties
        mass = float(props.Mass)
        center = props.CenterOfMass
        center_m = [float(center.X) / 100.0, float(center.Y) / 100.0, float(center.Z) / 100.0]
        moments = list(props.XYZMomentsOfInertia())
        if len(moments) != 6 or mass <= 0:
            return None
        # Inventor database units are kg and cm; inertia therefore uses kg*cm^2.
        inertia = [float(value) * 1e-4 for value in moments]
        # Inventor order: Ixx, Iyy, Izz, Ixy, Iyz, Ixz.
        inertia = [inertia[0], inertia[1], inertia[2], inertia[3], inertia[5], inertia[4]]
        return {
            "mass": mass,
            "center_of_mass": center_m,
            "inertia": inertia,
            "provenance": "inventor_mass_properties",
            "confidence": 1.0,
        }
    except Exception:
        return None


def _export_stl(app, part_document, target: Path) -> None:
    try:
        translator = app.ApplicationAddIns.ItemById(STL_TRANSLATOR_ID)
        context = app.TransientObjects.CreateTranslationContext()
        context.Type = K_FILE_BROWSE_IO_MECHANISM
        options = app.TransientObjects.CreateNameValueMap()
        data = app.TransientObjects.CreateDataMedium()
        data.FileName = str(target)
        translator.SaveCopyAs(part_document, context, options, data)
    except Exception as exc:
        raise InventorAdapterError(
            f"Inventor가 {target.name} 메시를 내보내지 못했습니다: {exc}"
        ) from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise InventorAdapterError(f"Inventor STL 결과가 생성되지 않았습니다: {target.name}")


def _export_step(app, part_document, target: Path) -> None:
    """Preserve exact CAD topology for OpenCascade snapping."""

    try:
        translator = app.ApplicationAddIns.ItemById(STEP_TRANSLATOR_ID)
        context = app.TransientObjects.CreateTranslationContext()
        context.Type = K_FILE_BROWSE_IO_MECHANISM
        options = app.TransientObjects.CreateNameValueMap()
        data = app.TransientObjects.CreateDataMedium()
        data.FileName = str(target)
        translator.SaveCopyAs(part_document, context, options, data)
    except Exception as exc:
        raise InventorAdapterError(
            f"Inventor가 {target.name} CAD 형상을 내보내지 못했습니다: {exc}"
        ) from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise InventorAdapterError(
            f"Inventor STEP 결과가 생성되지 않았습니다: {target.name}"
        )


@dataclass
class _Node:
    name: str
    occurrence: Any
    representative: str
    transform: list[list[float]]
    grounded: bool


class _AssemblyExtractor:
    def __init__(self, app, output_dir: Path):
        self.app = app
        self.output_dir = output_dir
        self.parts: list[dict[str, Any]] = []
        self.joints: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.used_part_names: set[str] = set()
        self.used_joint_names: set[str] = set()
        self.part_transforms: dict[str, list[list[float]]] = {}

    def _attach_cad_geometry(
        self,
        part: dict[str, Any],
        part_document,
        part_id: str,
        display_name: str,
    ) -> None:
        cad_target = self.output_dir / f"{part_id}.step"
        try:
            _export_step(self.app, part_document, cad_target)
            part["cad_geometry"] = cad_target.name
            part["snap_source"] = "opencascade"
        except InventorAdapterError as exc:
            self.warnings.append({
                "severity": "warning",
                "code": "inventor_cad_snap_fallback",
                "message": (
                    f"{display_name}: 정확한 CAD 스냅 형상을 보존하지 못해 "
                    f"메쉬 추정으로 대체합니다. ({exc})"
                ),
            })

    def add_document_part(self, document, display_name: str) -> str:
        part_id = _unique_name(_safe_name(display_name), self.used_part_names)
        target = self.output_dir / f"{part_id}.stl"
        _export_stl(self.app, document, target)
        self.part_transforms[part_id] = _identity_matrix()
        part: dict[str, Any] = {
            "id": part_id,
            "name": display_name,
            "geometry": target.name,
            "transform": matrix_transform(_identity_matrix()),
            "material": "silver_default",
            "source_document": str(getattr(document, "FullFileName", "")),
        }
        physical = _mass_properties(document)
        if physical:
            part["physical"] = physical
        self._attach_cad_geometry(part, document, part_id, display_name)
        self.parts.append(part)
        return part_id

    def _add_part(self, occurrence, path: tuple[str, ...]) -> str:
        display_name = "_".join(path)
        part_id = _unique_name(_safe_name(display_name), self.used_part_names)
        target = self.output_dir / f"{part_id}.stl"
        part_document = _occurrence_document(occurrence)
        if part_document is None:
            raise InventorAdapterError(f"{display_name}: 참조 부품 문서를 읽지 못했습니다.")
        _export_stl(self.app, part_document, target)
        transform_matrix = matrix_values(occurrence.Transformation)
        self.part_transforms[part_id] = transform_matrix
        part = {
            "id": part_id,
            "name": display_name,
            "geometry": target.name,
            "transform": matrix_transform(transform_matrix),
            "material": _appearance_name(occurrence),
            "source_document": str(getattr(part_document, "FullFileName", "")),
        }
        physical = _mass_properties(part_document)
        if physical:
            part["physical"] = physical
        else:
            self.warnings.append({
                "severity": "warning",
                "code": "inventor_physical_fallback",
                "message": f"{display_name}: Inventor 물성을 읽지 못해 메시에서 추정합니다.",
            })
        self._attach_cad_geometry(part, part_document, part_id, display_name)
        self.parts.append(part)
        return part_id

    def _joint_end_name(self, joint, which: str) -> str | None:
        for prefix in ("AffectedOccurrence", "Occurrence"):
            try:
                occurrence = getattr(joint, f"{prefix}{which}")
                if occurrence is not None:
                    return _occurrence_name(occurrence)
            except Exception:
                continue
        return None

    def _joint_spec(self, joint) -> dict[str, Any]:
        try:
            definition = joint.Definition
            raw_type = int(definition.JointType)
        except Exception:
            definition = None
            raw_type = 102401
        joint_type = JOINT_TYPES.get(raw_type, "fixed")
        limits: dict[str, float] = {}
        if definition is not None and raw_type == 102402:
            try:
                if bool(definition.HasAngularPositionLimits):
                    limits = {
                        "lower": float(definition.AngularPositionStartLimit),
                        "upper": float(definition.AngularPositionEndLimit),
                    }
                else:
                    joint_type = "continuous"
            except Exception:
                joint_type = "continuous"
        elif definition is not None and raw_type == 102403:
            try:
                lower = float(definition.LinearPositionStartLimit) if bool(
                    definition.HasLinearPositionStartLimit
                ) else 0.0
                upper = float(definition.LinearPositionEndLimit) if bool(
                    definition.HasLinearPositionEndLimit
                ) else 0.0
                limits = {"lower": lower * 10.0, "upper": upper * 10.0}
            except Exception:
                limits = {"lower": 0.0, "upper": 0.0}
        if raw_type in {102404, 102405, 102406}:
            self.warnings.append({
                "severity": "warning",
                "code": "inventor_joint_reduced",
                "message": (
                    f"{getattr(joint, 'Name', 'joint')}: Inventor의 다자유도 조인트를 "
                    f"URDF 단일 조인트({joint_type})로 축약했습니다."
                ),
            })
        return {"type": joint_type, "limits": limits, "axis": [0.0, 0.0, 1.0]}

    def _add_joint(
        self,
        name: str,
        parent: str,
        child: str,
        joint_type: str,
        limits: dict[str, float] | None = None,
        provenance: str = "inventor_assembly_joint",
    ) -> None:
        transform = relative_transform(
            self.part_transforms.get(parent, _identity_matrix()),
            self.part_transforms.get(child, _identity_matrix()),
        )
        spec: dict[str, Any] = {
            "name": _unique_name(_safe_name(name, "joint"), self.used_joint_names),
            "parent": parent,
            "child": child,
            "type": joint_type,
            "origin": {
                "xyz": transform["position"],
                "rpy": transform["rotation"],
            },
            "axis": [0.0, 0.0, 1.0],
            "provenance": provenance,
        }
        if limits:
            spec["limits"] = limits
        self.joints.append(spec)

    def _connect_level(self, definition, nodes: list[_Node], path: tuple[str, ...]) -> str:
        if not nodes:
            raise InventorAdapterError("빈 하위 조립품을 발견했습니다.")
        by_name = {node.name.casefold(): node for node in nodes}
        explicit_edges: list[tuple[_Node, _Node, Any]] = []
        try:
            raw_joints = _collection_items(definition.Joints)
        except Exception:
            raw_joints = []
        for joint in raw_joints:
            one_name = self._joint_end_name(joint, "One")
            two_name = self._joint_end_name(joint, "Two")
            one = by_name.get((one_name or "").casefold())
            two = by_name.get((two_name or "").casefold())
            if one and two and one is not two:
                explicit_edges.append((one, two, joint))

        root = next((node for node in nodes if node.grounded), nodes[0])
        visited = {root.representative}
        pending = list(explicit_edges)
        while pending:
            progressed = False
            for edge in list(pending):
                one, two, joint = edge
                one_seen = one.representative in visited
                two_seen = two.representative in visited
                if one_seen == two_seen:
                    continue
                parent, child = (one, two) if one_seen else (two, one)
                info = self._joint_spec(joint)
                provenance = (
                    "inventor_fixed_group_candidate"
                    if info["type"] == "fixed"
                    else "inventor_assembly_joint"
                )
                self._add_joint(
                    str(getattr(joint, "Name", "inventor_joint")),
                    parent.representative,
                    child.representative,
                    info["type"],
                    info["limits"],
                    provenance=provenance,
                )
                visited.add(child.representative)
                pending.remove(edge)
                progressed = True
            if not progressed:
                break

        for node in nodes:
            if node.representative in visited:
                continue
            self._add_joint(
                "_".join(path + (f"fixed_{node.name}",)),
                root.representative,
                node.representative,
                "fixed",
                provenance="inventor_recovered_constraint",
            )
            visited.add(node.representative)
        if pending:
            self.warnings.append({
                "severity": "warning",
                "code": "inventor_joint_cycle",
                "message": (
                    f"{'/'.join(path) or 'root'}: URDF 트리를 만들기 위해 "
                    f"중복·순환 조인트 {len(pending)}개를 제외했습니다."
                ),
            })
        return root.representative

    def walk(self, definition, occurrences, path: tuple[str, ...] = ()) -> str | None:
        nodes: list[_Node] = []
        for occurrence in _collection_items(occurrences):
            if _occurrence_suppressed(occurrence):
                continue
            occurrence_name = _occurrence_name(occurrence)
            occurrence_path = path + (occurrence_name,)
            try:
                sub_occurrences = occurrence.SubOccurrences
                sub_items = _collection_items(sub_occurrences)
            except Exception:
                sub_occurrences = None
                sub_items = []
            if sub_items:
                representative = self.walk(
                    getattr(occurrence, "Definition", definition),
                    sub_occurrences,
                    occurrence_path,
                )
            else:
                try:
                    representative = self._add_part(occurrence, occurrence_path)
                except InventorAdapterError as exc:
                    self.warnings.append({
                        "severity": "error",
                        "code": "inventor_unresolved_occurrence",
                        "message": f"{'/'.join(occurrence_path)}: {exc}",
                    })
                    continue
            if representative is None:
                continue
            nodes.append(_Node(
                name=occurrence_name,
                occurrence=occurrence,
                representative=representative,
                transform=self.part_transforms[representative],
                grounded=_occurrence_grounded(occurrence),
            ))
        if not nodes:
            return None
        return self._connect_level(definition, nodes, path)


def _convert_open_document(
    app,
    document,
    output_dir: Path,
    project_name: str,
    source_name: str,
    adapter_name: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = "참조 파일 확인"
    try:
        references, missing_references = _reference_status(document)
        stage = "조립 구조 읽기"
        definition = document.ComponentDefinition
        extractor = _AssemblyExtractor(app, output_dir)
        for missing_name in missing_references:
            extractor.warnings.append({
                "severity": "error",
                "code": "inventor_missing_reference",
                "message": f"{missing_name}: IAM이 참조하는 부품 파일을 찾지 못했습니다.",
            })
        occurrences = getattr(definition, "Occurrences", None)
        if occurrences is not None and _collection_items(occurrences):
            extractor.walk(definition, occurrences)
        else:
            extractor.add_document_part(document, Path(source_name).stem)
        if not extractor.parts:
            missing_text = ", ".join(missing_references[:8])
            if len(missing_references) > 8:
                missing_text += f" 외 {len(missing_references) - 8}개"
            if missing_text:
                raise InventorAdapterError(
                    "IAM의 참조 부품을 찾지 못했습니다: "
                    f"{missing_text}. Inventor에서 원본 조립품을 연 뒤 "
                    "'현재 열린 Inventor 조립품 가져오기'를 사용하거나 Pack and Go "
                    "결과 폴더를 선택하세요."
                )
            reference_hint = (
                f" IAM에 기록된 참조는 {len(references)}개입니다."
                if references else ""
            )
            raise InventorAdapterError(
                "Inventor 조립품에서 내보낼 수 있는 부품 형상을 찾지 못했습니다."
                f"{reference_hint}"
            )
        stage = "결과 기록"
        try:
            version = str(app.SoftwareVersion.DisplayVersion)
        except Exception:
            version = ""
        manifest = {
            "format": "petasos-assembly",
            "version": "1.0",
            "source": {
                "application": "Autodesk Inventor",
                "version": version,
                "document": source_name,
                "adapter": adapter_name,
            },
            "assembly": {
                "name": _safe_name(project_name, "robot"),
                "units": "mm",
                "angle_units": "rad",
                "up_axis": "y",
                "handedness": "right",
            },
            "parts": extractor.parts,
            "joints": extractor.joints,
            "warnings": extractor.warnings,
        }
        manifest_path = output_dir / "inventor-import.petasos.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path
    except InventorAdapterError:
        raise
    except Exception as exc:
        raise InventorAdapterError(
            f"Inventor {stage} 단계에서 {Path(source_name).name} 처리에 실패했습니다: "
            f"{_inventor_error_text(exc)}"
        ) from exc


def _require_windows_com():
    if os.name != "nt":
        raise InventorAdapterError(
            "Inventor 직접 변환은 Autodesk Inventor가 설치된 Windows에서 지원됩니다."
        )
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise InventorAdapterError(
            "Inventor 직접 변환에는 pywin32와 Autodesk Inventor가 필요합니다."
        ) from exc
    return pythoncom, win32com.client


def convert_with_inventor(
    assembly_path: Path,
    output_dir: Path,
    project_name: str,
) -> Path:
    pythoncom, win32_client = _require_windows_com()
    pythoncom.CoInitialize()
    app = None
    document = None
    stage = "Inventor 시작"
    try:
        app = win32_client.DispatchEx("Inventor.Application")
        app.Visible = False
        try:
            app.SilentOperation = True
        except Exception:
            pass
        stage = "조립품 열기"
        options = app.TransientObjects.CreateNameValueMap()
        try:
            options.Add("SkipAllUnresolvedFiles", True)
            options.Add("ExpressModeBehavior", "OpenFull")
        except Exception:
            pass
        document = app.Documents.OpenWithOptions(
            str(assembly_path.resolve()),
            options,
            False,
        )
        return _convert_open_document(
            app,
            document,
            output_dir,
            project_name,
            str(assembly_path.resolve()),
            "petasos-inventor-path",
        )
    except InventorAdapterError:
        raise
    except Exception as exc:
        raise InventorAdapterError(
            f"Inventor {stage} 단계에서 {assembly_path.name} 처리에 실패했습니다: "
            f"{_inventor_error_text(exc)}"
        ) from exc
    finally:
        if document is not None:
            try:
                document.Close(True)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def _document_is_assembly(document) -> bool:
    try:
        if int(document.DocumentType) == 12291:
            return True
    except Exception:
        pass
    try:
        filename = str(document.FullFileName or document.DisplayName)
    except Exception:
        filename = ""
    return Path(filename).suffix.lower() == ".iam"


def _document_label(document) -> str:
    try:
        return Path(str(document.FullFileName or document.DisplayName)).name
    except Exception:
        return "이름 없는 문서"


def _select_open_assembly_document(app):
    try:
        active_document = app.ActiveDocument
    except Exception:
        active_document = None
    if active_document is not None and _document_is_assembly(active_document):
        return active_document

    referring_assemblies = []
    if active_document is not None:
        try:
            referring_assemblies = [
                document
                for document in _collection_items(active_document.ReferencingDocuments)
                if _document_is_assembly(document)
            ]
        except Exception:
            referring_assemblies = []
    if len(referring_assemblies) == 1:
        return referring_assemblies[0]

    try:
        open_assemblies = [
            document
            for document in _collection_items(app.Documents)
            if _document_is_assembly(document)
        ]
    except Exception:
        open_assemblies = []
    if len(open_assemblies) == 1:
        return open_assemblies[0]
    if len(open_assemblies) > 1:
        names = ", ".join(_document_label(document) for document in open_assemblies[:5])
        raise InventorAdapterError(
            "Inventor에 조립품이 여러 개 열려 있습니다. 가져올 IAM 창을 한 번 클릭한 뒤 "
            f"다시 시도하세요: {names}"
        )
    if active_document is None:
        raise InventorAdapterError(
            "Inventor에 열린 문서가 없습니다. IAM 조립품을 먼저 여세요."
        )
    raise InventorAdapterError(
        f"열린 Inventor에서 조립품을 찾지 못했습니다. 현재 문서: "
        f"{_document_label(active_document)}"
    )


def convert_active_inventor(output_dir: Path, project_name: str) -> Path:
    pythoncom, win32_client = _require_windows_com()
    pythoncom.CoInitialize()
    try:
        try:
            app = win32_client.GetActiveObject("Inventor.Application")
        except Exception as exc:
            raise InventorAdapterError(
                "실행 중인 Inventor를 찾지 못했습니다. Inventor에서 IAM 조립품을 "
                "먼저 연 뒤 다시 시도하세요."
            ) from exc
        try:
            document = _select_open_assembly_document(app)
        except InventorAdapterError:
            raise
        except Exception as exc:
            raise InventorAdapterError(
                "Inventor에 열린 문서가 없습니다. IAM 조립품을 먼저 여세요."
            ) from exc
        try:
            document_type = int(document.DocumentType)
        except Exception:
            document_type = 0
        try:
            source_name = str(document.FullFileName or document.DisplayName)
        except Exception:
            source_name = "active_assembly.iam"
        if document_type != 12291 and Path(source_name).suffix.lower() != ".iam":
            raise InventorAdapterError(
                f"현재 Inventor 문서는 조립품이 아닙니다: {Path(source_name).name}"
            )
        return _convert_open_document(
            app,
            document,
            output_dir,
            project_name,
            source_name,
            "petasos-inventor-active",
        )
    finally:
        pythoncom.CoUninitialize()
