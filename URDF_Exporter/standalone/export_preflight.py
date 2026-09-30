"""Read-only checks on the *generated* robot package before publication."""

from __future__ import annotations

import json
import math
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import trimesh


class TrimeshFCLBackend:
    """Exact mesh narrowphase when python-fcl is installed."""

    def __init__(self):
        import fcl  # noqa: F401 - CollisionManager needs this optional package

    def contacts(self, mesh_a, mesh_b, transform_a, transform_b):
        manager = trimesh.collision.CollisionManager()
        manager.add_object("first", mesh_a, transform_a)
        return bool(manager.in_collision_single(mesh_b, transform_b))


def _diagnostic(code, severity, targets, observed, expected, action):
    return dict(code=code, severity=severity, targets=list(targets),
                observed=observed, expected=expected, action=action)


def _vector(value, default="0 0 0"):
    return np.asarray([float(item) for item in (value or default).split()], dtype=float)


def _origin(element):
    origin = element.find("origin")
    matrix = trimesh.transformations.euler_matrix(*_vector(origin.get("rpy") if origin is not None else None))
    matrix[:3, 3] = _vector(origin.get("xyz") if origin is not None else None)
    return matrix


def _geometry(element, description, mesh_cache):
    mesh_element = element.find("geometry/mesh")
    if mesh_element is None:
        return None
    filename = mesh_element.get("filename", "")
    mesh_path = description / "meshes" / Path(filename).name
    if not mesh_path.is_file():
        return None
    if mesh_path not in mesh_cache:
        loaded = trimesh.load_mesh(mesh_path, force="mesh", process=False)
        mesh_cache[mesh_path] = loaded
    mesh = mesh_cache[mesh_path]
    scale = _vector(mesh_element.get("scale"), "1 1 1")
    return mesh, _origin(element) @ np.diag([*scale, 1.0])


def _corners(bounds):
    low, high = bounds
    return np.asarray([[x, y, z] for x in (low[0], high[0])
                       for y in (low[1], high[1]) for z in (low[2], high[2])])


def _transformed_bounds(mesh, matrix):
    vertices = trimesh.transform_points(_corners(mesh.bounds), matrix)
    return np.asarray([vertices.min(axis=0), vertices.max(axis=0)])


def _link_poses(robot):
    poses = {}
    all_links = {link.get("name") for link in robot.findall("link")}
    joints = robot.findall("joint")
    children = {item.find("child").get("link") for item in joints if item.find("child") is not None}
    for root in all_links - children:
        poses[root] = np.eye(4)
    pending = list(joints)
    while pending:
        later = []
        changed = False
        for joint in pending:
            parent = joint.find("parent")
            child = joint.find("child")
            if parent is None or child is None or parent.get("link") not in poses:
                later.append(joint)
                continue
            transform = _origin(joint)
            if joint.get("type") in {"revolute", "continuous", "prismatic"}:
                axis_element = joint.find("axis")
                axis = _vector(axis_element.get("xyz") if axis_element is not None else "1 0 0")
                length = np.linalg.norm(axis)
                if length:
                    axis /= length
                    limit = joint.find("limit")
                    lower = float(limit.get("lower", "0")) if limit is not None else 0.0
                    upper = float(limit.get("upper", "0")) if limit is not None else 0.0
                    zero = 0.0 if joint.get("type") == "continuous" else min(max(0.0, lower), upper)
                    motion = np.eye(4)
                    if joint.get("type") == "prismatic":
                        motion[:3, 3] = axis * zero
                    else:
                        motion = trimesh.transformations.rotation_matrix(zero, axis)
                    transform = transform @ motion
            poses[child.get("link")] = poses[parent.get("link")] @ transform
            changed = True
        if not changed:
            break
        pending = later
    return poses


def inspect_candidate(description_dir: Path, moveit_dir: Path | None = None, backend=None) -> dict:
    """Return physical and collision diagnostics; never mutate the candidate."""
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
    collision = {}
    poses = _link_poses(robot)
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
            geometry = _geometry(visual, description, mesh_cache)
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
            com = _vector(origin.get("xyz") if origin is not None else None)
            if visual_bounds:
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
            geometry = _geometry(collision_element, description, mesh_cache)
            if geometry and name in poses:
                mesh, local = geometry
                collision_faces += len(mesh.faces)
                world = poses[name] @ local
                collision.setdefault(name, []).append((mesh, world, _transformed_bounds(mesh, world)))
        if visual_faces and collision_faces and collision_faces < visual_faces:
            diagnostics.append(_diagnostic("collision_decimation", "info", [name],
                                           round(collision_faces / visual_faces, 4),
                                           "collision/visual face ratio; shape reviewed",
                                           "Check that simplified collision geometry keeps the intended contact surfaces."))
    names = sorted(collision)
    checked_pairs = 0
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            if frozenset((first, second)) in adjacency:
                continue
            for mesh_a, transform_a, bounds_a in collision[first]:
                for mesh_b, transform_b, bounds_b in collision[second]:
                    if np.any(bounds_a[1] < bounds_b[0]) or np.any(bounds_b[1] < bounds_a[0]):
                        continue
                    checked_pairs += 1
                    targets = [first, second]
                    if backend is None:
                        diagnostics.append(_diagnostic("collision_not_checked", "not_checked", targets,
                                                       "AABB overlap; exact backend unavailable", "exact narrowphase result",
                                                       "Review this pair in MoveIt/Gazebo or enable an exact collision backend."))
                    elif backend.contacts(mesh_a, mesh_b, transform_a, transform_b):
                        diagnostics.append(_diagnostic("collision_contact", "warning", targets,
                                                       "mesh contact at start pose", "no unintended contact",
                                                       "Review intentional contacts or adjust the initial pose/collision geometry."))
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
