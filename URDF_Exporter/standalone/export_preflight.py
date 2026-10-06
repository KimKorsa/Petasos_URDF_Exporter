"""Read-only checks on the *generated* robot package before publication."""

from __future__ import annotations

import json
import math
import weakref
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import trimesh


class TrimeshFCLBackend:
    """Exact mesh narrowphase when python-fcl is installed."""

    def __init__(self):
        import fcl  # noqa: F401 - CollisionManager needs this optional package
        self._managers = OrderedDict()

    def _manager(self, mesh, transform, side):
        # Match the previous add_object(A)/in_collision_single(B) precision.
        transform = np.asarray(transform, dtype=np.float32 if side == 0 else np.float64)
        if transform.shape != (4, 4):
            raise ValueError("transform must be (4,4)!")
        key = (id(mesh), side)
        checksum = hash(mesh)
        cached = self._managers.get(key)
        if cached is not None and cached[0]() is mesh and cached[1] == checksum:
            manager = cached[2]
            manager.set_transform("mesh", transform)
            self._managers.move_to_end(key)
            return manager
        manager = trimesh.collision.CollisionManager()
        manager.add_object("mesh", mesh, transform)
        if side == 1:
            # add_object casts to float32; restore B's original precision.
            manager.set_transform("mesh", transform)
        self._managers[key] = (weakref.ref(mesh), checksum, manager)
        self._managers.move_to_end(key)
        while len(self._managers) > 64:
            self._managers.popitem(last=False)
        return manager

    def contacts(self, mesh_a, mesh_b, transform_a, transform_b):
        # Separate sides also handle one shared mesh used at two different poses.
        first = self._manager(mesh_a, transform_a, 0)
        second = self._manager(mesh_b, transform_b, 1)
        return bool(first.in_collision_other(second))


def _diagnostic(code, severity, targets, observed, expected, action):
    return dict(code=code, severity=severity, targets=list(targets),
                observed=observed, expected=expected, action=action)


def _geometry(element, description, mesh_cache):
    from .collision_diagnostics import geometry
    key = ElementTree.tostring(element)
    if key not in mesh_cache:
        mesh_cache[key] = geometry(element, description, mesh_cache)
    return mesh_cache[key]


def _corners(bounds):
    low, high = bounds
    return np.asarray([[x, y, z] for x in (low[0], high[0])
                       for y in (low[1], high[1]) for z in (low[2], high[2])])


def _transformed_bounds(mesh, matrix):
    vertices = trimesh.transform_points(_corners(mesh.bounds), matrix)
    return np.asarray([vertices.min(axis=0), vertices.max(axis=0)])


def inspect_candidate(description_dir: Path, moveit_dir: Path | None = None, backend=None) -> dict:
    """Inspect robot data without changing it; persist only the diagnostic report."""
    description = Path(description_dir)
    robot_name = description.name.removesuffix("_description")
    urdf_files = sorted((description / "urdf").glob("*.urdf"))
    if urdf_files:
        robot = ElementTree.parse(urdf_files[0]).getroot()
    else:
        import xacro
        xacro_files = sorted((description / "urdf").glob("*.xacro"))
        if not xacro_files:
            raise ValueError(f"No URDF or Xacro found in {description / 'urdf'}")
        main_xacro = description / "urdf" / f"{robot_name}.xacro"
        robot = ElementTree.fromstring(xacro.process_file(str(
            main_xacro if main_xacro.is_file() else xacro_files[0]
        )).toxml())
    diagnostics = []
    if backend is None:
        try:
            backend = TrimeshFCLBackend()
        except ImportError:
            pass
    mesh_cache = {}
    adjacency = {
        frozenset((joint.find("parent").get("link"), joint.find("child").get("link")))
        for joint in robot.findall("joint") if joint.get("type") == "fixed"
        and joint.find("parent") is not None and joint.find("child") is not None
    }
    for link in robot.findall("link"):
        name = link.get("name")
        visual_bounds = []
        visual_faces = 0
        for visual in link.findall("visual"):
            try:
                geometry = _geometry(visual, description, mesh_cache)
            except (OSError, TypeError, ValueError) as error:
                diagnostics.append(_diagnostic("visual_geometry_invalid", "error", [name], str(error),
                                               "valid visual geometry and mesh path",
                                               "Correct the visual dimensions or restore the missing mesh."))
                continue
            if geometry:
                visual_bounds.append(_transformed_bounds(*geometry))
                visual_faces += len(geometry[0].faces)
        inertial = link.find("inertial")
        if inertial is not None:
            mass_element = inertial.find("mass")
            try:
                mass = float(mass_element.get("value", "nan")) if mass_element is not None else math.nan
            except (TypeError, ValueError):
                mass = math.nan
            if not math.isfinite(mass) or mass <= 0:
                diagnostics.append(_diagnostic("invalid_mass", "error", [name], mass,
                                               "finite mass > 0 kg", "Correct the CAD mass or assigned material density."))
            origin = inertial.find("origin")
            com_text = origin.get("xyz") if origin is not None else None
            try:
                from .urdf_analysis import vector
                com = vector(com_text)
            except (TypeError, ValueError):
                com = None
                diagnostics.append(_diagnostic("invalid_com", "error", [name], com_text,
                                               "three finite COM coordinates in meters",
                                               "Correct the CAD center-of-mass coordinates."))
            if visual_bounds and com is not None:
                bounds = np.asarray([np.min([item[0] for item in visual_bounds], axis=0),
                                     np.max([item[1] for item in visual_bounds], axis=0)])
                if not np.all(np.isfinite(com)) or np.any(com < bounds[0] - 1e-4) or np.any(com > bounds[1] + 1e-4):
                    diagnostics.append(_diagnostic("com_outside_visual", "error", [name], com.tolist(),
                                                   bounds.tolist(), "Recheck CAD COM units and link assembly transform."))
            inertia_element = inertial.find("inertia")
            try:
                values = {key: float(inertia_element.get(key, "nan"))
                          for key in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")}
                tensor = np.asarray([[values["ixx"], values["ixy"], values["ixz"]],
                                     [values["ixy"], values["iyy"], values["iyz"]],
                                     [values["ixz"], values["iyz"], values["izz"]]])
                eigenvalues = np.linalg.eigvalsh(tensor)
            except (AttributeError, TypeError, ValueError, np.linalg.LinAlgError):
                eigenvalues = np.asarray([math.nan])
            if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues <= 0):
                diagnostics.append(_diagnostic("invalid_inertia", "error", [name], eigenvalues.tolist(),
                                               "positive-definite inertia tensor", "Recalculate link inertia from CAD geometry and mass."))
        collision_faces = 0
        for collision_element in link.findall("collision"):
            try:
                geometry = _geometry(collision_element, description, mesh_cache)
            except (OSError, TypeError, ValueError):
                # The independent collision report below names invalid geometry.
                continue
            if geometry:
                mesh, _local = geometry
                collision_faces += len(mesh.faces)
        if visual_faces and collision_faces and collision_faces < visual_faces:
            diagnostics.append(_diagnostic("collision_decimation", "info", [name],
                                           round(collision_faces / visual_faces, 4),
                                           "collision/visual face ratio; shape reviewed",
                                           "Check that simplified collision geometry keeps the intended contact surfaces."))
    from .collision_diagnostics import diagnose_collision_meshes
    semantic = None
    if moveit_dir:
        srdfs = sorted((Path(moveit_dir) / 'config').glob('*.srdf'))
        if srdfs:
            semantic = ElementTree.parse(srdfs[0]).getroot()
    collision_report = diagnose_collision_meshes(robot, description, semantic, backend, mesh_cache=mesh_cache)
    generation_path = description / 'meshes' / 'collision_mesh_generation.json'
    generation = json.loads(generation_path.read_text(encoding='utf-8')) if generation_path.is_file() else {}
    for name, result in generation.items():
        if result.get('status') == 'fallback' and result.get('reason') != 'source_topology_invalid':
            diagnostics.append(_diagnostic('collision_simplification_fallback', 'info', [name],
                                           result.get('reason'), 'validated collision geometry',
                                           '단순화 결과 대신 원본 충돌 메시를 사용했습니다.'))
    checked_pairs = 0
    for mesh in collision_report['meshes']:
        if mesh['status'] == 'error':
            diagnostics.append(_diagnostic('collision_mesh_invalid', 'error', [mesh['link']], mesh['message'],
                                           '유효한 충돌 형상', '누락된 mesh 또는 형상 데이터를 수정하세요.'))
        elif not mesh['watertight'] or not mesh['winding_consistent']:
            observed = (f"boundary_edges={mesh['boundary_edges']}, "
                        f"nonmanifold_edges={mesh['nonmanifold_edges']}, "
                        f"winding_consistent={mesh['winding_consistent']}")
            # Welding a grouped mesh can join coincident contact surfaces from
            # otherwise valid parts. Topology alone is not a contact verdict or
            # evidence that the source CAD is damaged.
            if generation.get(mesh['link'], {}).get('status') == 'simplified':
                diagnostics.append(_diagnostic('collision_simplification_damage', 'warning',
                    [mesh['link']], observed, 'validated simplified collision geometry',
                    '단순화된 충돌 메시의 면 연결을 확인하거나 원본 메시로 다시 생성하세요.'))
            else:
                diagnostics.append(_diagnostic('collision_mesh_topology', 'info',
                    [mesh['link']], observed, '표면 연결 정보 · 접촉 여부는 별도 검사',
                    '합친 부품의 접합부에서도 나타날 수 있습니다. 실제 링크 간 접촉은 별도 충돌 검사 결과를 확인하세요.'))
    for pair in collision_report['pairs']:
        if pair['excluded_reason'] or frozenset(pair['links']) in adjacency:
            continue
        checked_pairs += 1
        if pair['exact_status'] == 'unverified':
            diagnostics.append(_diagnostic('collision_not_checked', 'not_checked', pair['links'], pair['message'],
                                           '정밀 충돌 판정', 'MoveIt 실제 충돌 검사로 이 링크 쌍을 확인하세요.'))
        elif pair['status'] == 'collision':
            diagnostics.append(_diagnostic('collision_contact', 'warning', pair['links'], '영점에서 mesh 접촉',
                                           '의도하지 않은 접촉 없음', '실제 접촉인지 충돌 형상 문제인지 확인하세요.'))
    analysis_dir = description / 'analysis'
    analysis_dir.mkdir(exist_ok=True)
    (analysis_dir / 'collision_diagnostics.json').write_text(
        json.dumps(collision_report, ensure_ascii=False, indent=2), encoding='utf-8')
    consistency_path = analysis_dir / 'export_consistency.json'
    if consistency_path.is_file():
        consistency = json.loads(consistency_path.read_text(encoding='utf-8'))
        for difference in consistency.get('differences', []):
            diagnostics.append(_diagnostic('export_value_mismatch', 'error', [difference['target']],
                difference.get('observed'), difference.get('expected'), difference['message']))
    assembly = description / "analysis" / "assembly.json"
    if assembly.is_file():
        data = json.loads(assembly.read_text(encoding="utf-8"))
        for part in data.get("source_parts", []):
            provenance = str((part.get("physical") or {}).get("provenance") or "")
            if "stl" in provenance.lower() or "fallback" in provenance.lower():
                diagnostics.append(_diagnostic("stl_physical_fallback", "warning", [part.get("name", "unknown")],
                                               provenance, "CAD or measured physical properties",
                                               "Confirm density, mass and COM before simulation."))
    status = "error" if any(item["severity"] == "error" for item in diagnostics) else (
        "warning" if any(item["severity"] in {"warning", "not_checked"} for item in diagnostics) else "ok"
    )
    return {"status": status, "diagnostics": diagnostics,
            "summary": {"links": len(robot.findall("link")), "candidate_collision_pairs": checked_pairs,
                        "errors": sum(item["severity"] == "error" for item in diagnostics),
                        "warnings": sum(item["severity"] == "warning" for item in diagnostics),
                        "not_checked": sum(item["severity"] == "not_checked" for item in diagnostics)}}
