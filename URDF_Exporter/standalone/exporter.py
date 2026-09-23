from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
from glob import glob
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import trimesh

from URDF_Exporter.core import Structure, Write
from URDF_Exporter.standalone.physical_materials import apply_material_overrides
from moveit.generate_smoke_config import generate_smoke_config


_COLLISION_SIMPLIFY_THRESHOLD = 5000
_COLLISION_TARGET_MAX_FACES = 5000
_COLLISION_TARGET_MIN_FACES = 1000


def _remove_generated_workspace(path: str) -> None:
    workspace = Path(path)
    if not workspace.is_dir():
        return
    try:
        shutil.rmtree(workspace)
        return
    except OSError:
        if os.name != "nt":
            raise

    runtime = workspace / ".petasos_runtime"
    windows_path = runtime.resolve(strict=False).as_posix()
    if not (
        re.match(r"^[A-Za-z]:/", windows_path)
        and runtime.parent == workspace
    ):
        raise OSError(f"안전하게 정리할 수 없는 페타소스 캐시 경로입니다: {runtime}")
    wsl_path = f"/mnt/{windows_path[0].lower()}/{windows_path[3:]}"
    subprocess.run(
        [
            "wsl.exe",
            "-d",
            "Ubuntu-22.04",
            "--",
            "rm",
            "-rf",
            "--",
            wsl_path,
        ],
        check=False,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    shutil.rmtree(workspace)


def _write_moveit_seed_urdf(
    struct: Structure.RobotStructure,
    robot_name: str,
    path: str,
    fix_to_world: bool,
    root_joint_mode: str | None = None,
) -> None:
    robot = ElementTree.Element("robot", {"name": robot_name})
    link_names = list(struct.inertial)
    child_links = {
        info.get("child")
        for info in struct.joints.values()
        if info.get("child")
    }
    root_links = [name for name in link_names if name not in child_links]
    root_link = root_links[0] if root_links else (link_names[0] if link_names else None)
    if root_joint_mode not in {"world", "base_footprint", "none"}:
        root_joint_mode = "world" if fix_to_world else "none"
    if root_joint_mode == "world":
        ElementTree.SubElement(robot, "link", {"name": "world"})
    elif root_joint_mode == "base_footprint":
        ElementTree.SubElement(robot, "link", {"name": "base_footprint"})
    for link_name in link_names:
        ElementTree.SubElement(robot, "link", {"name": link_name})
    if root_joint_mode != "none" and root_link:
        root_joint = ElementTree.SubElement(
            robot,
            "joint",
            {
                "name": (
                    "world_joint"
                    if root_joint_mode == "world"
                    else "base_footprint_joint"
                ),
                "type": "fixed",
            },
        )
        ElementTree.SubElement(
            root_joint,
            "parent",
            {
                "link": (
                    "world" if root_joint_mode == "world" else "base_footprint"
                )
            },
        )
        ElementTree.SubElement(root_joint, "child", {"link": root_link})

    for name, info in struct.joints.items():
        joint_type = info.get("type", "fixed")
        joint = ElementTree.SubElement(
            robot,
            "joint",
            {"name": name, "type": joint_type},
        )
        ElementTree.SubElement(joint, "parent", {"link": info["parent"]})
        ElementTree.SubElement(joint, "child", {"link": info["child"]})
        ElementTree.SubElement(
            joint,
            "origin",
            {
                "xyz": " ".join(str(float(value)) for value in info.get("xyz", [0, 0, 0])),
                "rpy": " ".join(str(float(value)) for value in info.get("rpy", [0, 0, 0])),
            },
        )
        if joint_type in {"revolute", "continuous", "prismatic"}:
            axis = info.get("axis") or [0.0, 0.0, 1.0]
            ElementTree.SubElement(
                joint,
                "axis",
                {"xyz": " ".join(str(float(value)) for value in axis)},
            )
            limit = {
                "effort": str(float(info.get("effort_limit", 100.0))),
                "velocity": str(float(info.get("velocity_limit", 1.0))),
            }
            if joint_type in {"revolute", "prismatic"}:
                limit["lower"] = str(float(info["lower_limit"]))
                limit["upper"] = str(float(info["upper_limit"]))
            ElementTree.SubElement(joint, "limit", limit)
        dynamics = {}
        if info.get("damping") is not None:
            dynamics["damping"] = str(float(info["damping"]))
        if info.get("friction") is not None:
            dynamics["friction"] = str(float(info["friction"]))
        if dynamics:
            ElementTree.SubElement(joint, "dynamics", dynamics)
        if info.get("mimic_joint"):
            ElementTree.SubElement(
                joint,
                "mimic",
                {
                    "joint": str(info["mimic_joint"]),
                    "multiplier": str(float(info.get("mimic_multiplier", 1.0))),
                    "offset": str(float(info.get("mimic_offset", 0.0))),
                },
            )

    ElementTree.ElementTree(robot).write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )


def _write_portable_moveit_helpers(
    bundle_dir: str,
    description_package: str,
    moveit_package: str,
    robot_name: str,
) -> None:
    bundle = Path(bundle_dir)
    tools_dir = bundle / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[2]
    for filename in ("validate_urdf.py", "validate_moveit_config.py"):
        shutil.copy2(project_root / "moveit" / filename, tools_dir / filename)

    validation_body = f"""#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
validation_urdf="$(mktemp --suffix=.urdf)"
trap 'rm -f "$validation_urdf"' EXIT
xacro src/{description_package}/urdf/{robot_name}.xacro > "$validation_urdf"
python3 tools/validate_urdf.py "$validation_urdf"
"""
    (bundle / "validate_moveit.sh").write_text(
        validation_body
        + f"python3 tools/validate_moveit_config.py src/{moveit_package} "
        '--urdf "$validation_urdf"\n'
        + 'echo "Petasos 검사 통과"\n',
        encoding="utf-8",
        newline="\n",
    )
    (bundle / "normalize_moveit.sh").write_text(
        validation_body
        + 'backup_root=".petasos_backups"\n'
        + 'mkdir -p "$backup_root"\n'
        + f'cp -a src/{moveit_package}/config '
        + '"$backup_root/config_$(date +%Y%m%d_%H%M%S_%N)"\n'
        + f"python3 tools/validate_moveit_config.py src/{moveit_package} "
        + '--urdf "$validation_urdf" --fix\n'
        + f"python3 tools/validate_moveit_config.py src/{moveit_package} "
        + '--urdf "$validation_urdf"\n'
        + 'echo "Petasos Humble 정규화 및 검사 통과"\n',
        encoding="utf-8",
        newline="\n",
    )

    build_body = f"""cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
export LIBGL_ALWAYS_SOFTWARE=1
export OGRE_RTT_MODE=Copy
runtime_root="$PWD/.petasos_runtime"
colcon --log-base "$runtime_root/log" build \
  --build-base "$runtime_root/build" \
  --install-base "$runtime_root/install" \
  --packages-up-to {description_package} {moveit_package}
source "$runtime_root/install/setup.bash"
"""
    (bundle / "open_moveit_assistant.sh").write_text(
        "#!/usr/bin/env bash\nset -e\n"
        + build_body
        + f"ros2 run moveit_setup_assistant moveit_setup_assistant "
        f"-c src/{moveit_package}\n"
        + "bash ./normalize_moveit.sh\n"
        + "rm -rf .petasos_runtime\n",
        encoding="utf-8",
        newline="\n",
    )
    (bundle / "run_moveit_demo.sh").write_text(
        "#!/usr/bin/env bash\nset -e\n"
        + "cd \"$(dirname \"$0\")\"\n"
        + "cleanup_runtime() { rm -rf .petasos_runtime; }\n"
        + "trap cleanup_runtime EXIT\n"
        + "bash ./normalize_moveit.sh\n"
        + build_body
        + f"ros2 launch {moveit_package} demo.launch.py\n",
        encoding="utf-8",
        newline="\n",
    )
    (bundle / "README_MOVEIT_KO.txt").write_text(
        "Petasos ROS 2 Humble MoveIt 번들\n\n"
        "1. 이 ros_ws의 src 폴더에 description과 moveit_config가 함께 있습니다.\n"
        "2. WSL Ubuntu 22.04에서 이 폴더를 열고 chmod +x *.sh 를 실행합니다.\n"
        "3. ./open_moveit_assistant.sh 로 같은 moveit_config를 직접 편집합니다.\n"
        "4. Assistant를 닫으면 같은 폴더를 백업·정규화·재검사합니다.\n"
        "5. ./run_moveit_demo.sh 로 .petasos_runtime에서 빌드·실행합니다.\n"
        "6. Ubuntu로 옮긴 뒤에는 ros_ws에서 일반 colcon build를 실행합니다.\n\n"
        "페타소스 검사 캐시는 .petasos_runtime에 격리되어 기본 build/install/log를 오염시키지 않습니다.\n"
        "원본 description Xacro는 수정하지 않습니다.\n",
        encoding="utf-8",
        newline="\n",
    )


def _finite_vector(value, length: int) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    try:
        vector = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return vector if all(math.isfinite(item) for item in vector) else None


def _root_orientation_rpy(up_axis: str, custom_rpy=None) -> list[float]:
    custom = _finite_vector(custom_rpy, 3)
    if custom is not None:
        return custom
    axis = str(up_axis or "z").lower()
    if axis == "y":
        return [1.5707963267948966, 0.0, 0.0]
    if axis == "x":
        return [0.0, -1.5707963267948966, 0.0]
    return [0.0, 0.0, 0.0]


def _root_origin_xyz(custom_xyz=None) -> list[float]:
    return _finite_vector(custom_xyz, 3) or [0.0, 0.0, 0.0]


def _matrix_from_xyz_rpy(xyz: list[float], rpy: list[float]) -> list[float]:
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, xyz[0],
        sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, xyz[1],
        -sp, cp * sr, cp * cr, xyz[2],
        0.0, 0.0, 0.0, 1.0,
    ]


def _matrix_multiply(left: list[float], right: list[float]) -> list[float]:
    return [
        sum(left[row * 4 + k] * right[k * 4 + column] for k in range(4))
        for row in range(4)
        for column in range(4)
    ]


def _rigid_matrix_inverse(matrix: list[float]) -> list[float]:
    rotation_transpose = [
        matrix[0], matrix[4], matrix[8],
        matrix[1], matrix[5], matrix[9],
        matrix[2], matrix[6], matrix[10],
    ]
    translation = [matrix[3], matrix[7], matrix[11]]
    inverse_translation = [
        -sum(rotation_transpose[row * 3 + column] * translation[column] for column in range(3))
        for row in range(3)
    ]
    return [
        rotation_transpose[0], rotation_transpose[1], rotation_transpose[2], inverse_translation[0],
        rotation_transpose[3], rotation_transpose[4], rotation_transpose[5], inverse_translation[1],
        rotation_transpose[6], rotation_transpose[7], rotation_transpose[8], inverse_translation[2],
        0.0, 0.0, 0.0, 1.0,
    ]


def _base_footprint_joint_pose(
    root_xyz: list[float],
    root_rpy: list[float],
    edited_tree: dict,
) -> tuple[list[float], list[float]]:
    frame = edited_tree.get("_base_footprint_frame") or {}
    footprint_xyz = _finite_vector(frame.get("world_xyz"), 3) or [0.0, 0.0, 0.0]
    footprint_rpy = None
    if frame.get("orientation_manual"):
        footprint_rpy = _finite_vector(frame.get("rpy"), 3)
    if footprint_rpy is None and frame.get("orientation_manual"):
        try:
            footprint_yaw = float(frame.get("yaw") or 0.0)
        except (TypeError, ValueError):
            footprint_yaw = 0.0
        if not math.isfinite(footprint_yaw):
            footprint_yaw = 0.0
        footprint_rpy = [0.0, 0.0, footprint_yaw]
    if footprint_rpy is None:
        # base_footprint is the ground-plane projection of base_link: keep the
        # root yaw while removing roll, pitch and height.
        footprint_rpy = [0.0, 0.0, float(root_rpy[2])]
    world_from_footprint = _matrix_from_xyz_rpy(
        footprint_xyz,
        footprint_rpy,
    )
    world_from_root = _matrix_from_xyz_rpy(root_xyz, root_rpy)
    footprint_from_root = _matrix_multiply(
        _rigid_matrix_inverse(world_from_footprint),
        world_from_root,
    )
    return _matrix_xyz_rpy(footprint_from_root)


def _matrix_from_quaternion_xyz(
    quaternion: list[float],
    xyz: list[float],
) -> list[float]:
    x, y, z, w = quaternion
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 1e-12:
        raise ValueError("Quaternion has zero length")
    x, y, z, w = x / length, y / length, z / length, w / length
    return [
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), xyz[0],
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), xyz[1],
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), xyz[2],
        0.0, 0.0, 0.0, 1.0,
    ]


def _matrix_xyz_rpy(matrix: list[float]) -> tuple[list[float], list[float]]:
    pitch = math.atan2(
        -matrix[8],
        math.sqrt(matrix[0] * matrix[0] + matrix[4] * matrix[4]),
    )
    if abs(abs(pitch) - math.pi / 2.0) < 1e-9:
        roll = math.atan2(-matrix[6], matrix[5])
        yaw = 0.0
    else:
        roll = math.atan2(matrix[9], matrix[10])
        yaw = math.atan2(matrix[4], matrix[0])
    def clean(value: float) -> float:
        rounded = round(value, 12)
        return 0.0 if abs(rounded) < 1e-12 else rounded

    return (
        [clean(matrix[3]), clean(matrix[7]), clean(matrix[11])],
        [clean(roll), clean(pitch), clean(yaw)],
    )


def _root_correction_matrix(state: dict, edited_tree: dict) -> list[float]:
    preview_quaternion = _finite_vector(
        edited_tree.get("_preview_root_quaternion"),
        4,
    )
    preview_position = _finite_vector(
        edited_tree.get("_preview_root_position"),
        3,
    )
    if preview_quaternion is not None:
        units_per_meter = float(
            edited_tree.get("_preview_units_per_meter")
            or state.get("tree", {}).get("_preview_units_per_meter")
            or 1000.0
        )
        if not math.isfinite(units_per_meter) or units_per_meter <= 0:
            units_per_meter = 1000.0
        preview_xyz_m = [
            value / units_per_meter
            for value in (preview_position or [0.0, 0.0, 0.0])
        ]
        preview_matrix = _matrix_from_quaternion_xyz(
            preview_quaternion,
            preview_xyz_m,
        )
        # The Three.js viewer is Y-up. ROS/RViz is Z-up.
        ros_frame = _matrix_from_xyz_rpy(
            [0.0, 0.0, 0.0],
            [math.pi / 2.0, 0.0, 0.0],
        )
        return _matrix_multiply(ros_frame, preview_matrix)

    return _matrix_from_xyz_rpy(
        _root_origin_xyz(edited_tree.get("_preview_root_xyz")),
        _root_orientation_rpy(
            edited_tree.get("_preview_up_axis", "z"),
            edited_tree.get("_preview_root_rpy"),
        ),
    )


def _root_link_pose(state: dict, edited_tree: dict) -> tuple[list[float], list[float]]:
    """Return the complete ROS world -> exported root-link transform.

    The viewer's saved root transform places the CAD assembly on the selected
    ground face. The exported root link, however, is located at its first
    component frame rather than at the CAD assembly origin. Both transforms
    must therefore be composed or RViz loses the root component's original
    position and rotation.
    """
    root_correction = _root_correction_matrix(state, edited_tree)

    components = edited_tree.get("components")
    root_component = components[0] if isinstance(components, list) and components else None
    component_matrix = None
    if root_component:
        component_matrix = _finite_vector(
            state.get("visual_transforms", {}).get(root_component),
            16,
        )
    if component_matrix is None:
        component_matrix = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

    return _matrix_xyz_rpy(_matrix_multiply(root_correction, component_matrix))


def _validate_joint_limits(joints: dict) -> None:
    """Reject positional joint ranges that cannot be represented by URDF."""
    invalid = []
    for name, joint in joints.items():
        if joint.get("type") not in {"revolute", "prismatic"}:
            continue
        lower = _finite_vector([joint.get("lower_limit")], 1)
        upper = _finite_vector([joint.get("upper_limit")], 1)
        if lower is None or upper is None or lower[0] >= upper[0]:
            invalid.append(
                f"{name} (lower={joint.get('lower_limit')}, "
                f"upper={joint.get('upper_limit')})"
            )
    if invalid:
        raise ValueError(
            "URDF joint limit error: lower must be smaller than upper: "
            + ", ".join(invalid)
        )


def _positive_joint_value(joint: dict, keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        if key not in joint:
            continue
        try:
            value = float(joint[key])
        except (TypeError, ValueError):
            break
        if math.isfinite(value) and value > 0.0:
            return value
        break
    return float(default)


def _optional_nonnegative_joint_value(joint: dict, key: str) -> float | None:
    if key not in joint or joint.get(key) in (None, ""):
        return None
    try:
        value = float(joint[key])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0.0 else None


def _prepare_moveit_readiness(joints: dict, links: dict) -> dict:
    """Validate and complete the control data needed by MoveIt/ros2_control."""
    _validate_joint_limits(joints)
    link_names = set(links)
    errors = []
    controlled_joints = []
    child_parents: dict[str, str] = {}
    adjacency = {name: [] for name in link_names}

    for name, joint in joints.items():
        joint_type = joint.get("type")
        parent = joint.get("parent")
        child = joint.get("child")
        if parent not in link_names or child not in link_names:
            errors.append(
                f"{name}: parent/child link is missing ({parent} -> {child})"
            )
            continue
        if parent == child:
            errors.append(f"{name}: parent and child are the same link ({parent})")
            continue
        if child in child_parents:
            errors.append(
                f"{child}: more than one parent joint "
                f"({child_parents[child]}, {name})"
            )
        child_parents[child] = name
        adjacency[parent].append(child)

        if joint_type not in {"revolute", "continuous", "prismatic"}:
            continue
        axis = _finite_vector(joint.get("axis"), 3)
        if axis is None or math.sqrt(sum(value * value for value in axis)) <= 1e-9:
            errors.append(f"{name}: movable joint axis must be a non-zero finite vector")
            continue

        joint["effort_limit"] = _positive_joint_value(
            joint,
            ("effort_limit", "effort"),
            100.0,
        )
        joint["velocity_limit"] = _positive_joint_value(
            joint,
            ("velocity_limit", "max_velocity", "velocity"),
            1.0,
        )
        joint["max_acceleration"] = _positive_joint_value(
            joint,
            ("max_acceleration", "acceleration_limit"),
            1.0,
        )
        joint["max_deceleration"] = _optional_nonnegative_joint_value(
            joint, "max_deceleration"
        )
        joint["max_jerk"] = _optional_nonnegative_joint_value(joint, "max_jerk")
        command_interface = str(joint.get("command_interface") or "position")
        if command_interface not in {"position", "velocity", "effort"}:
            command_interface = "position"
        state_interfaces = joint.get("state_interfaces") or ["position"]
        state_interfaces = [
            value for value in ("position", "velocity", "effort")
            if value in state_interfaces
        ]
        joint["command_interface"] = command_interface
        joint["state_interfaces"] = state_interfaces or ["position"]

        try:
            initial = float(joint.get("initial_position", 0.0))
        except (TypeError, ValueError):
            initial = 0.0
        if not math.isfinite(initial):
            initial = 0.0
        if joint_type in {"revolute", "prismatic"}:
            lower = float(joint["lower_limit"])
            upper = float(joint["upper_limit"])
            if not lower <= initial <= upper:
                initial = (lower + upper) / 2.0
        joint["initial_position"] = initial
        controlled_joints.append(
            {
                "name": name,
                "type": joint_type,
                "initial_position": initial,
                "velocity_limit": joint["velocity_limit"],
                "effort_limit": joint["effort_limit"],
                "max_acceleration": joint["max_acceleration"],
                "max_deceleration": joint["max_deceleration"],
                "max_jerk": joint["max_jerk"],
                "command_interface": joint["command_interface"],
                "state_interfaces": joint["state_interfaces"],
            }
        )

    roots = sorted(link_names - set(child_parents))
    if len(roots) != 1:
        errors.append(
            "robot must have exactly one kinematic root; found "
            + (", ".join(roots) if roots else "none")
        )
    elif link_names:
        visited = set()
        visiting = set()

        def visit(link: str) -> None:
            if link in visiting:
                errors.append(f"kinematic cycle detected at link {link}")
                return
            if link in visited:
                return
            visiting.add(link)
            for child_link in adjacency.get(link, []):
                visit(child_link)
            visiting.remove(link)
            visited.add(link)

        visit(roots[0])
        disconnected = sorted(link_names - visited)
        if disconnected:
            errors.append(
                "links disconnected from the kinematic root: "
                + ", ".join(disconnected)
            )

    if errors:
        raise ValueError("MoveIt readiness error: " + "; ".join(errors))
    return {
        "status": "ready",
        "root_link": roots[0],
        "controlled_joint_count": len(controlled_joints),
        "controlled_joints": controlled_joints,
        "defaults": {
            "velocity_limit": 1.0,
            "effort_limit": 100.0,
            "max_acceleration": 1.0,
        },
    }


def _write_ros_package_files(
    package_name: str,
    robot_name: str,
    save_dir: str,
    fixed_frame: str = "world",
    controller_groups: list[dict] | None = None,
) -> None:
    if fixed_frame not in {"world", "base_footprint", "base_link"}:
        raise ValueError(f"Unsupported RViz fixed frame: {fixed_frame}")
    os.makedirs(os.path.join(save_dir, "resource"), exist_ok=True)
    os.makedirs(os.path.join(save_dir, "launch"), exist_ok=True)
    os.makedirs(os.path.join(save_dir, "config"), exist_ok=True)
    os.makedirs(os.path.join(save_dir, package_name), exist_ok=True)

    with open(os.path.join(save_dir, package_name, "__init__.py"), "w", encoding="utf-8"):
        pass
    with open(os.path.join(save_dir, "resource", package_name), "w", encoding="utf-8"):
        pass
    with open(os.path.join(save_dir, "setup.cfg"), "w", encoding="utf-8") as stream:
        stream.write(
            f"[develop]\nscript_dir=$base/lib/{package_name}\n"
            f"[install]\ninstall_scripts=$base/lib/{package_name}\n"
        )
    with open(os.path.join(save_dir, "setup.py"), "w", encoding="utf-8") as stream:
        stream.write(
            f"""from setuptools import setup
from glob import glob
import os

package_name = "{package_name}"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
        (os.path.join("share", package_name, "urdf"), glob("urdf/*")),
        (os.path.join("share", package_name, "meshes"), glob("meshes/*.stl")),
        (os.path.join("share", package_name, "analysis"), glob("analysis/*.json")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Petasos",
    maintainer_email="contact@petasos.dev",
    description="CAD-neutral ROS 2 robot description generated by Petasos",
    license="MIT",
)
"""
        )
    controller_dependencies = {
        str(group.get("type", "")).split("/", 1)[0]
        for group in (controller_groups or [])
        if "/" in str(group.get("type", ""))
    }
    controller_dependencies.add("joint_state_broadcaster")
    dependency_lines = "\n".join(
        f"  <exec_depend>{dependency}</exec_depend>"
        for dependency in sorted(controller_dependencies)
    )
    with open(os.path.join(save_dir, "package.xml"), "w", encoding="utf-8") as stream:
        stream.write(
            f"""<?xml version="1.0"?>
<package format="3">
  <name>{package_name}</name>
  <version>0.1.0</version>
  <description>Petasos robot description for {robot_name}</description>
  <maintainer email="contact@petasos.dev">Petasos</maintainer>
  <license>MIT</license>
  <buildtool_depend>ament_python</buildtool_depend>
  <exec_depend>robot_state_publisher</exec_depend>
  <exec_depend>joint_state_publisher</exec_depend>
  <exec_depend>joint_state_publisher_gui</exec_depend>
  <exec_depend>xacro</exec_depend>
  <exec_depend>rviz2</exec_depend>
  <exec_depend>ros2_control</exec_depend>
  <exec_depend>ros2_controllers</exec_depend>
  <exec_depend>ament_index_python</exec_depend>
  <exec_depend>launch</exec_depend>
  <exec_depend>launch_ros</exec_depend>
  <exec_depend>gazebo_ros</exec_depend>
  <exec_depend>gazebo_ros2_control</exec_depend>
  <exec_depend>controller_manager</exec_depend>
{dependency_lines}
  <export>
    <build_type>ament_python</build_type>
    <gazebo_ros gazebo_model_path="${{prefix}}/.."/>
  </export>
</package>
"""
        )
    with open(os.path.join(save_dir, "launch", "display.launch.py"), "w", encoding="utf-8") as stream:
        stream.write(
            f"""from launch_ros.actions import Node
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition
import xacro
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    share_dir = get_package_share_directory("{package_name}")

    xacro_file = os.path.join(share_dir, "urdf", "{robot_name}.xacro")
    robot_description_config = xacro.process_file(xacro_file)
    robot_urdf = robot_description_config.toxml()

    rviz_config_file = os.path.join(share_dir, "config", "display.rviz")

    gui_arg = DeclareLaunchArgument(
        name="gui",
        default_value="True"
    )

    show_gui = LaunchConfiguration("gui")

    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[
            {{"robot_description": robot_urdf}}
        ]
    )

    joint_state_publisher_node = Node(
        condition=UnlessCondition(show_gui),
        package="joint_state_publisher",
        executable="joint_state_publisher",
        name="joint_state_publisher"
    )

    joint_state_publisher_gui_node = Node(
        condition=IfCondition(show_gui),
        package="joint_state_publisher_gui",
        executable="joint_state_publisher_gui",
        name="joint_state_publisher_gui"
    )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config_file],
        output="screen"
    )

    return LaunchDescription([
        SetEnvironmentVariable(name="LIBGL_ALWAYS_SOFTWARE", value="1"),
        SetEnvironmentVariable(name="OGRE_RTT_MODE", value="Copy"),
        gui_arg,
        robot_state_publisher_node,
        joint_state_publisher_node,
        joint_state_publisher_gui_node,
        rviz_node
    ])
"""
        )
    with open(os.path.join(save_dir, "config", "display.rviz"), "w", encoding="utf-8") as stream:
        stream.write(
            f"""Panels:
  - Class: rviz_common/Displays
    Name: Displays
  - Class: rviz_common/Views
    Name: Views
Visualization Manager:
  Displays:
    - Alpha: 0.5
      Cell Size: 0.1
      Class: rviz_default_plugins/Grid
      Color: 160; 160; 164
      Enabled: true
      Name: Grid
      Plane: XY
      Plane Cell Count: 20
      Reference Frame: <Fixed Frame>
      Value: true
    - Alpha: 1
      Class: rviz_default_plugins/RobotModel
      Description Source: Topic
      Description Topic:
        Depth: 5
        Durability Policy: Volatile
        History Policy: Keep Last
        Reliability Policy: Reliable
        Value: /robot_description
      Enabled: true
      Name: RobotModel
      Update Interval: 0
      Value: true
      Visual Enabled: true
    - Class: rviz_default_plugins/TF
      Enabled: true
      Frame Timeout: 15
      Marker Scale: 0.15
      Name: TF
      Show Arrows: true
      Show Axes: true
      Show Names: false
      Value: true
  Global Options:
    Background Color: 48; 48; 48
    Fixed Frame: {fixed_frame}
    Frame Rate: 30
  Name: root
  Tools:
    - Class: rviz_default_plugins/Interact
      Hide Inactive Objects: true
    - Class: rviz_default_plugins/MoveCamera
    - Class: rviz_default_plugins/Select
    - Class: rviz_default_plugins/FocusCamera
    - Class: rviz_default_plugins/Measure
      Line color: 128; 128; 0
    - Class: rviz_default_plugins/SetInitialPose
      Topic:
        Value: /initialpose
    - Class: rviz_default_plugins/SetGoal
      Topic:
        Value: /goal_pose
    - Class: rviz_default_plugins/PublishPoint
      Single click: true
      Topic:
        Value: /clicked_point
  Transformation:
    Current:
      Class: rviz_default_plugins/TF
  Value: true
  Views:
    Current:
      Class: rviz_default_plugins/Orbit
      Distance: 0.85
      Focal Point:
        X: 0
        Y: 0
        Z: 0
      Focal Shape Fixed Size: true
      Focal Shape Size: 0.05
      Invert Z Axis: false
      Near Clip Distance: 0.01
      Pitch: 0.61
      Target Frame: <Fixed Frame>
      Value: Orbit (rviz)
      Yaw: 0.51
    Saved: ~
"""
        )


def _write_analysis(
    state: dict,
    struct: Structure.RobotStructure,
    save_dir: str,
    moveit_readiness: dict,
) -> None:
    analysis_dir = os.path.join(save_dir, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    payload = {
        "robot": state["project_name"],
        "source_parts": state.get("parts", []),
        "links": struct.inertial,
        "joints": struct.joints,
        "import_report": state.get("report", {}),
    }
    with open(os.path.join(analysis_dir, "assembly.json"), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    with open(
        os.path.join(analysis_dir, "moveit_readiness.json"),
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(moveit_readiness, stream, ensure_ascii=False, indent=2)


def _controller_groups(joints_dict: dict, edited_tree: dict | None = None) -> list[dict]:
    supported_types = {
        "joint_trajectory_controller/JointTrajectoryController",
        "position_controllers/JointGroupPositionController",
        "velocity_controllers/JointGroupVelocityController",
        "effort_controllers/JointGroupEffortController",
        "diff_drive_controller/DiffDriveController",
        "forward_command_controller/ForwardCommandController",
        "position_controllers/GripperActionController",
        "effort_controllers/GripperActionController",
        "pid_controller/PidController",
        "joint_state_broadcaster/JointStateBroadcaster",
    }
    movable = [
        name for name, info in joints_dict.items()
        if info.get("type") != "fixed"
    ]
    movable_set = set(movable)
    claimed: set[str] = set()
    # Gazebo support always creates this broadcaster, so a user controller must
    # not overwrite the manager entry with the same YAML key.
    used_names: set[str] = {"joint_state_broadcaster"}
    groups: list[dict] = []
    for index, raw in enumerate((edited_tree or {}).get("_controllers") or [], 1):
        raw_name = str(raw.get("name") or f"controller_{index}")
        name = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in raw_name
        ).strip("_") or f"controller_{index}"
        base_name = name
        suffix = 2
        while name in used_names:
            name = f"{base_name}_{suffix}"
            suffix += 1
        joints = [
            joint for joint in raw.get("joints") or []
            if joint in movable_set and joint not in claimed
        ]
        if not joints:
            continue
        used_names.add(name)
        claimed.update(joints)
        controller_type = str(
            raw.get("type") or "joint_trajectory_controller/JointTrajectoryController"
        )
        if controller_type not in supported_types:
            controller_type = "joint_trajectory_controller/JointTrajectoryController"
        settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
        groups.append({
            "name": name,
            "type": controller_type,
            "joints": joints,
            "settings": copy.deepcopy(settings),
            "color": str(raw.get("color") or ""),
        })
    unassigned = [joint for joint in movable if joint not in claimed]
    if unassigned:
        fallback = "arm_controller" if "arm_controller" not in used_names else "unassigned_controller"
        groups.append({
            "name": fallback,
            "type": "joint_trajectory_controller/JointTrajectoryController",
            "joints": unassigned,
            "settings": {},
        })
    return groups


def _apply_diff_drive_cad_wheel_radius(
    groups: list[dict],
    joints_dict: dict,
    collision_meshes: dict[str, str],
    mesh_dir: str,
) -> None:
    """Fill unconfirmed DiffDrive radius from wheel-link CAD meshes."""
    for group in groups:
        if group.get("type") != "diff_drive_controller/DiffDriveController":
            continue
        settings = group.setdefault("settings", {})
        if settings.get("wheel_radius_manual"):
            continue
        radii = []
        for joint_name in group.get("joints") or []:
            info = joints_dict.get(joint_name, {})
            filename = collision_meshes.get(str(info.get("child") or ""))
            if not filename:
                continue
            path = os.path.join(mesh_dir, filename)
            if not os.path.isfile(path):
                continue
            axis = np.asarray(info.get("axis") or [0.0, 0.0, 1.0], dtype=float)
            norm = float(np.linalg.norm(axis))
            if not math.isfinite(norm) or norm <= 1e-9:
                continue
            axis /= norm
            vertices = np.asarray(_as_mesh(trimesh.load_mesh(path, file_type="stl")).vertices, dtype=float)
            if not len(vertices):
                continue
            axial = np.outer(vertices @ axis, axis)
            radius_mm = float(np.max(np.linalg.norm(vertices - axial, axis=1)))
            if math.isfinite(radius_mm) and radius_mm > 1e-6:
                radii.append(radius_mm / 1000.0)
        if radii:
            settings["wheel_radius"] = float(np.median(radii))
            settings["wheel_radius_source"] = "cad_collision_mesh"


def _normalize_diff_drive_wheel_axes(
    groups: list[dict],
    joints_dict: dict,
) -> list[str]:
    """Make positive wheel velocity point every axle in one parent-frame direction."""
    flipped: list[str] = []
    for group in groups:
        if group.get("type") != "diff_drive_controller/DiffDriveController":
            continue
        axes = []
        for name in group.get("joints") or []:
            info = joints_dict.get(name, {})
            axis = np.asarray(info.get("axis") or [0.0, 0.0, 1.0], dtype=float)
            norm = float(np.linalg.norm(axis))
            if not math.isfinite(norm) or norm <= 1e-9:
                continue
            axis /= norm
            rpy = [float(value) for value in (info.get("rpy") or [0.0, 0.0, 0.0])]
            rotation = np.asarray(
                _matrix_from_xyz_rpy([0.0, 0.0, 0.0], rpy), dtype=float
            ).reshape((4, 4))[:3, :3]
            axes.append((name, axis, rotation @ axis))
        if not axes:
            continue
        reference = axes[0][2]
        # REP-103 assumes +X forward and +Z up. Prefer the axle sign whose
        # bottom-point tangential velocity is +X, then align every wheel to it.
        forward_score = float(np.dot(np.cross(reference, [0.0, 0.0, -1.0]), [1.0, 0.0, 0.0]))
        if forward_score < -1e-9:
            reference = -reference
        for name, local_axis, parent_axis in axes:
            if float(np.dot(reference, parent_axis)) < 0.0:
                joints_dict[name]["axis"] = (-local_axis).tolist()
                flipped.append(name)
    return flipped


def _prepare_diff_drive_joint_interfaces(
    groups: list[dict],
    joints_dict: dict,
) -> None:
    """Expose wheel position telemetry while retaining velocity feedback."""
    for group in groups:
        if group.get("type") != "diff_drive_controller/DiffDriveController":
            continue
        group.setdefault("settings", {}).setdefault("position_feedback", False)
        for name in group.get("joints") or []:
            info = joints_dict.get(name)
            if not info:
                continue
            info["command_interface"] = "velocity"
            info["state_interfaces"] = ["position", "velocity"]


def _write_gazebo_support(
    joints_dict: dict,
    package_name: str,
    robot_name: str,
    save_dir: str,
    controller_groups: list[dict] | None = None,
    base_frame_id: str = "base_link",
) -> None:
    """Write Gazebo Classic launch and ros2_control controller configuration."""
    def safe_float(value, default: float) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return default
        return result if math.isfinite(result) else default

    def joint_y(name: str) -> float | None:
        xyz = joints_dict.get(name, {}).get("xyz")
        if not isinstance(xyz, (list, tuple)) or len(xyz) < 2:
            return None
        try:
            value = float(xyz[1])
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    def automatic_wheel_sides(names: list[str]) -> tuple[list[str], list[str]]:
        positioned = [(name, joint_y(name)) for name in names]
        if len(positioned) >= 2 and all(value is not None for _, value in positioned):
            positioned.sort(key=lambda item: item[1])
            split = max(1, len(positioned) // 2)
            # ROS REP-103: +Y is left. Higher Y therefore belongs to LEFT.
            return (
                [name for name, _ in positioned[split:]],
                [name for name, _ in positioned[:split]],
            )
        split = max(1, (len(names) + 1) // 2)
        return names[:split], names[split:]

    def automatic_wheel_separation(left: list[str], right: list[str]) -> float | None:
        left_y = [joint_y(name) for name in left]
        right_y = [joint_y(name) for name in right]
        if not left_y or not right_y or any(value is None for value in left_y + right_y):
            return None
        separation = abs(
            sum(left_y) / len(left_y) - sum(right_y) / len(right_y)
        )
        return separation if separation > 1e-9 else None

    def wheel_axis_in_parent(name: str) -> np.ndarray:
        info = joints_dict[name]
        axis = np.asarray(info.get("axis") or [0.0, 0.0, 1.0], dtype=float)
        rpy = [float(value) for value in (info.get("rpy") or [0.0, 0.0, 0.0])]
        rotation = np.asarray(_matrix_from_xyz_rpy([0.0, 0.0, 0.0], rpy), dtype=float).reshape((4, 4))[:3, :3]
        transformed = rotation @ axis
        norm = float(np.linalg.norm(transformed))
        if not math.isfinite(norm) or norm <= 1e-9:
            raise ValueError(f"DiffDrive wheel joint '{name}' has an invalid axis")
        return transformed / norm

    movable_joints = [
        name
        for name, info in joints_dict.items()
        if info.get("type") != "fixed"
    ]
    groups = controller_groups or (
        [{
            "name": "arm_controller",
            "type": "joint_trajectory_controller/JointTrajectoryController",
            "joints": movable_joints,
            "settings": {},
        }]
        if movable_joints else []
    )
    config_dir = os.path.join(save_dir, "config")
    launch_dir = os.path.join(save_dir, "launch")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(launch_dir, exist_ok=True)

    controller_lines = [
        "controller_manager:",
        "  ros__parameters:",
        "    update_rate: 100",
        "    joint_state_broadcaster:",
        "      type: joint_state_broadcaster/JointStateBroadcaster",
    ]
    if groups:
        for group in groups:
            controller_lines.extend([
                f"    {group['name']}:",
                f"      type: {group.get('type', 'joint_trajectory_controller/JointTrajectoryController')}",
            ])
        for group in groups:
            group_joints = group["joints"]
            controller_type = group.get(
                "type", "joint_trajectory_controller/JointTrajectoryController"
            )
            settings = group.get("settings") or {}
            command_interfaces = []
            state_interfaces = []
            for name in group_joints:
                info = joints_dict[name]
                command = info.get("command_interface", "position")
                if command not in command_interfaces:
                    command_interfaces.append(command)
                for state in info.get("state_interfaces") or ["position"]:
                    if state not in state_interfaces:
                        state_interfaces.append(state)
            controller_lines.extend([
                "",
                f"{group['name']}:",
                "  ros__parameters:",
            ])
            if controller_type == "diff_drive_controller/DiffDriveController":
                if settings.get("wheel_sides_manual"):
                    left = [name for name in settings.get("left_wheel_names") or [] if name in group_joints]
                    right = [name for name in settings.get("right_wheel_names") or [] if name in group_joints]
                else:
                    left, right = automatic_wheel_sides(group_joints)
                if not left or not right:
                    raise ValueError(
                        f"DiffDrive controller '{group['name']}' needs at least one LEFT and one RIGHT wheel joint"
                    )
                if settings.get("wheel_separation_manual"):
                    wheel_separation = safe_float(settings.get("wheel_separation"), 0.0)
                else:
                    wheel_separation = automatic_wheel_separation(left, right) or 0.0
                wheel_radius = safe_float(settings.get("wheel_radius"), 0.0)
                if wheel_separation <= 0:
                    raise ValueError(
                        f"DiffDrive controller '{group['name']}' wheel separation could not be derived; enter a positive measured value"
                    )
                radius_confirmed = bool(
                    settings.get("wheel_radius_manual")
                    or settings.get("wheel_radius_source") == "cad_collision_mesh"
                )
                if wheel_radius <= 0 or not radius_confirmed:
                    raise ValueError(
                        f"DiffDrive controller '{group['name']}' needs a confirmed positive measured wheel radius"
                    )
                wheel_axes = [wheel_axis_in_parent(name) for name in left + right]
                reference_axis = wheel_axes[0]
                opposed = [
                    name for name, axis in zip(left + right, wheel_axes)
                    if float(np.dot(reference_axis, axis)) < -0.5
                ]
                if opposed:
                    raise ValueError(
                        f"DiffDrive wheel axes point in opposite parent-frame directions: {', '.join(opposed)}; flip those joint axes so one positive velocity drives every wheel forward"
                    )
                wheel_states = {
                    name: set(joints_dict[name].get("state_interfaces") or ["position"])
                    for name in left + right
                }
                has_position = all("position" in values for values in wheel_states.values())
                has_velocity = all("velocity" in values for values in wheel_states.values())
                requested_position_feedback = bool(settings.get("position_feedback", False))
                if requested_position_feedback and has_position:
                    position_feedback = True
                elif has_velocity:
                    position_feedback = False
                else:
                    raise ValueError(
                        f"DiffDrive controller '{group['name']}' wheel joints must all expose the same position or velocity state interface"
                    )
                controller_lines.extend([
                    "    left_wheel_names: [" + ", ".join(f'\"{name}\"' for name in left) + "]",
                    "    right_wheel_names: [" + ", ".join(f'\"{name}\"' for name in right) + "]",
                    f"    wheel_separation: {round(wheel_separation, 6)}",
                    f"    wheel_radius: {round(wheel_radius, 6)}",
                    f"    position_feedback: {str(position_feedback).lower()}",
                    "    open_loop: false",
                    "    enable_odom_tf: true",
                    f"    base_frame_id: {base_frame_id}",
                    "    odom_frame_id: odom",
                ])
            elif controller_type in {
                "position_controllers/GripperActionController",
                "effort_controllers/GripperActionController",
            }:
                joint = settings.get("joint") if settings.get("joint") in group_joints else group_joints[0]
                controller_lines.extend([
                    f"    joint: {joint}",
                    f"    goal_tolerance: {safe_float(settings.get('goal_tolerance'), 0.01)}",
                    f"    max_effort: {safe_float(settings.get('max_effort'), 0.0)}",
                ])
            elif controller_type == "pid_controller/PidController":
                command_interface = str(settings.get("command_interface") or "position")
                reference_interface = str(settings.get("reference_and_state_interface") or "position")
                controller_lines.append("    dof_names:")
                controller_lines.extend(f"      - {name}" for name in group_joints)
                controller_lines.extend([
                    f"    command_interface: {command_interface}",
                    "    reference_and_state_interfaces:",
                    f"      - {reference_interface}",
                ])
                for name in group_joints:
                    controller_lines.extend([
                        f"    gains.{name}:",
                        f"      p: {safe_float(settings.get('p'), 1.0)}",
                        f"      i: {safe_float(settings.get('i'), 0.0)}",
                        f"      d: {safe_float(settings.get('d'), 0.0)}",
                    ])
            elif controller_type == "joint_state_broadcaster/JointStateBroadcaster":
                controller_lines.append("    joints:")
                controller_lines.extend(f"      - {name}" for name in group_joints)
                controller_lines.extend([
                    "    interfaces:",
                    "      - position",
                    "      - velocity",
                    "      - effort",
                ])
            else:
                controller_lines.append("    joints:")
                controller_lines.extend(f"      - {name}" for name in group_joints)
                if controller_type == "joint_trajectory_controller/JointTrajectoryController":
                    controller_lines.append("    command_interfaces:")
                    controller_lines.extend(f"      - {value}" for value in command_interfaces)
                    controller_lines.append("    state_interfaces:")
                    controller_lines.extend(f"      - {value}" for value in state_interfaces)
                    controller_lines.extend([
                        "    state_publish_rate: 50.0",
                        "    action_monitor_rate: 20.0",
                        "    allow_partial_joints_goal: false",
                    ])
                elif controller_type == "forward_command_controller/ForwardCommandController":
                    interface_name = str(settings.get("command_interface") or "position")
                    controller_lines.append(f"    interface_name: {interface_name}")
    Path(config_dir, "gazebo_controllers.yaml").write_text(
        "\n".join(controller_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    spawner_nodes = "\n".join(
        f'''    controller_spawner_{index} = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["{group['name']}", "--controller-manager", "/controller_manager"],
        output="screen",
    )'''
        for index, group in enumerate(groups, 1)
    )
    spawner_actions = "[joint_state_broadcaster_spawner" + "".join(
        f", controller_spawner_{index}" for index in range(1, len(groups) + 1)
    ) + "]"
    Path(launch_dir, "gazebo.launch.py").write_text(
        f"""import os

import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler, SetEnvironmentVariable
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():
    description_share = get_package_share_directory("{package_name}")
    gazebo_share = get_package_share_directory("gazebo_ros")
    xacro_file = os.path.join(description_share, "urdf", "{robot_name}.xacro")
    robot_description = xacro.process_file(
        xacro_file,
        mappings={{"use_gazebo": "true"}},
    ).toxml()

    gazebo_model_path = SetEnvironmentVariable(
        name="GAZEBO_MODEL_PATH",
        value=[
            os.path.dirname(description_share),
            os.pathsep,
            EnvironmentVariable("GAZEBO_MODEL_PATH", default_value=""),
        ],
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_share, "launch", "gazebo.launch.py")
        )
    )
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[
            {{"use_sim_time": True, "robot_description": robot_description}}
        ],
        output="screen",
    )
    spawn_robot = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        arguments=[
            "-topic", "robot_description",
            "-entity", "{robot_name}",
        ],
        output="screen",
    )
    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager", "/controller_manager",
        ],
        output="screen",
    )
{spawner_nodes}
    start_controllers = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_robot,
            on_exit={spawner_actions},
        )
    )

    return LaunchDescription([
        gazebo_model_path,
        gazebo,
        robot_state_publisher,
        spawn_robot,
        start_controllers,
    ])
""",
        encoding="utf-8",
        newline="\n",
    )


def _collision_filename(link_name: str) -> str:
    safe_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in link_name
    ).strip("._")
    return f"{safe_name or 'link'}_collision.stl"


def _visual_filename(link_name: str) -> str:
    safe_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in link_name
    ).strip("._")
    return f"{safe_name or 'link'}_visual.stl"


def _as_mesh(loaded) -> trimesh.Trimesh:
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geometry.copy()
            for geometry in loaded.geometry.values()
            if isinstance(geometry, trimesh.Trimesh)
        ]
        if not meshes:
            raise ValueError("STL scene contains no triangle mesh")
        return trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError("Unsupported STL geometry")
    return loaded


def _is_binary_stl(path: str) -> bool:
    """Return True only when the STL has a valid binary facet table."""

    file_size = os.path.getsize(path)
    if file_size < 84:
        return False
    with open(path, "rb") as stream:
        stream.seek(80)
        facet_count_bytes = stream.read(4)
    if len(facet_count_bytes) != 4:
        return False
    facet_count = struct.unpack("<I", facet_count_bytes)[0]
    return file_size == 84 + (facet_count * 50)


def _copy_mesh_as_binary_stl(source_path: str, target_path: str) -> None:
    """Copy an STL while guaranteeing the binary form required by RViz."""

    if _is_binary_stl(source_path):
        shutil.copy2(source_path, target_path)
        return

    mesh = _as_mesh(trimesh.load_mesh(source_path, file_type="stl"))
    mesh.export(target_path, file_type="stl")
    if not _is_binary_stl(target_path):
        raise ValueError(
            f"RViz-compatible binary STL conversion failed: {os.path.basename(source_path)}"
        )


def _simplify_collision_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    face_count = len(mesh.faces)
    if face_count <= _COLLISION_SIMPLIFY_THRESHOLD:
        return mesh
    target = max(
        _COLLISION_TARGET_MIN_FACES,
        min(_COLLISION_TARGET_MAX_FACES, int(face_count * 0.2)),
    )
    try:
        simplified = mesh.simplify_quadric_decimation(face_count=target)
        if isinstance(simplified, trimesh.Trimesh) and len(simplified.faces):
            return simplified
    except Exception:
        # Combining still removes per-part collision overhead even when the
        # optional decimation backend rejects a particular CAD mesh.
        pass
    return mesh


def _write_grouped_collision_meshes(
    additional_visuals: dict,
    source_mesh_dir: str,
    output_mesh_dir: str,
) -> dict[str, str]:
    collision_meshes = {}
    for link_name, visual_parts in additional_visuals.items():
        transformed_parts = []
        for visual_info in visual_parts:
            component_name = visual_info[0]
            xyz = visual_info[2] if len(visual_info) > 2 else [0, 0, 0]
            rpy = visual_info[3] if len(visual_info) > 3 else [0, 0, 0]
            source_path = os.path.join(source_mesh_dir, component_name + ".stl")
            if not os.path.isfile(source_path):
                transformed_parts = []
                break

            mesh = _as_mesh(trimesh.load_mesh(source_path, file_type="stl"))
            transform = np.asarray(
                _matrix_from_xyz_rpy(
                    [float(value) * 1000.0 for value in xyz],
                    [float(value) for value in rpy],
                ),
                dtype=float,
            ).reshape((4, 4))
            mesh.apply_transform(transform)
            transformed_parts.append(mesh)

        if not transformed_parts:
            continue

        combined = trimesh.util.concatenate(transformed_parts)
        combined.remove_unreferenced_vertices()
        combined = _simplify_collision_mesh(combined)
        filename = _collision_filename(link_name)
        combined.export(os.path.join(output_mesh_dir, filename), file_type="stl")
        collision_meshes[link_name] = filename
    return collision_meshes


def _write_grouped_visual_meshes(
    additional_visuals: dict,
    material_dict: dict,
    source_mesh_dir: str,
    output_mesh_dir: str,
) -> dict[str, list[tuple]]:
    """Bake link parts into one full-detail visual STL without decimation."""
    grouped_visuals: dict[str, list[tuple]] = {}
    for link_name, visual_parts in additional_visuals.items():
        transformed_parts = []
        for visual_info in visual_parts:
            component_name = visual_info[0]
            xyz = visual_info[2] if len(visual_info) > 2 else [0, 0, 0]
            rpy = visual_info[3] if len(visual_info) > 3 else [0, 0, 0]
            source_path = os.path.join(source_mesh_dir, component_name + ".stl")
            if not os.path.isfile(source_path):
                transformed_parts = []
                break
            mesh = _as_mesh(trimesh.load_mesh(source_path, file_type="stl"))
            transform = np.asarray(
                _matrix_from_xyz_rpy(
                    [float(value) * 1000.0 for value in xyz],
                    [float(value) for value in rpy],
                ),
                dtype=float,
            ).reshape((4, 4))
            mesh.apply_transform(transform)
            transformed_parts.append(mesh)
        if not transformed_parts:
            continue
        # Concatenation changes only storage; every source face and thin CAD
        # feature is retained exactly for the rendered appearance.
        combined = trimesh.util.concatenate(transformed_parts)
        combined.remove_unreferenced_vertices()
        filename = _visual_filename(link_name)
        combined.export(os.path.join(output_mesh_dir, filename), file_type="stl")
        material = (material_dict.get(link_name) or {}).get("material", "silver_default")
        grouped_visuals[link_name] = [
            (os.path.splitext(filename)[0], material, [0, 0, 0], [0, 0, 0])
        ]
    return grouped_visuals


def export_project(
    state: dict,
    edited_tree: dict,
    fix_to_world: bool,
    project_dir: str,
    include_moveit: bool = False,
    output_root: str | None = None,
    root_joint_mode: str | None = None,
) -> dict:
    robot_name = state["project_name"].lower()
    if root_joint_mode not in {"world", "base_footprint", "none"}:
        root_joint_mode = "world" if fix_to_world else "none"
    package_name = robot_name + "_description"
    moveit_package = robot_name + "_moveit_config"
    export_root = output_root or os.path.join(project_dir, "export")
    bundle_dir = None
    if include_moveit:
        bundle_dir = os.path.join(
            export_root,
            "ros_ws",
        )
        if os.path.isdir(bundle_dir):
            _remove_generated_workspace(bundle_dir)
        source_dir = os.path.join(bundle_dir, "src")
        save_dir = os.path.join(source_dir, package_name)
    else:
        save_dir = os.path.join(export_root, package_name)
        if os.path.isdir(save_dir):
            shutil.rmtree(save_dir)
    os.makedirs(save_dir, exist_ok=True)

    component_inertial = copy.deepcopy(state["inertial"])
    component_materials = copy.deepcopy(state["materials"])
    export_colors = copy.deepcopy(state.get("colors", {}))
    material_warnings = apply_material_overrides(
        component_inertial,
        component_materials,
        export_colors,
        edited_tree,
    )
    if material_warnings:
        raise ValueError("물리 재질 적용 실패: " + " / ".join(material_warnings))
    struct = Structure.RobotStructure(
        copy.deepcopy(state["joints"]),
        component_inertial,
        component_materials,
        copy.deepcopy(state.get("visual_transforms", {})),
    )
    struct.apply_tree_data(copy.deepcopy(edited_tree))
    struct.standardize_names()
    controller_groups = _controller_groups(struct.joints, edited_tree)
    _prepare_diff_drive_joint_interfaces(controller_groups, struct.joints)
    normalized_diff_drive_axes = _normalize_diff_drive_wheel_axes(
        controller_groups,
        struct.joints,
    )
    moveit_readiness = _prepare_moveit_readiness(
        struct.joints,
        struct.inertial,
    )

    meshes_dir = os.path.join(save_dir, "meshes")
    os.makedirs(meshes_dir, exist_ok=True)
    source_mesh_dir = os.path.join(project_dir, "meshes")
    grouped_visuals = _write_grouped_visual_meshes(
        struct.additional_visuals,
        struct.materials,
        source_mesh_dir,
        meshes_dir,
    )
    collision_meshes = _write_grouped_collision_meshes(
        struct.additional_visuals,
        source_mesh_dir,
        meshes_dir,
    )
    # Keep the original part meshes only for the exceptional link that could
    # not be baked (for example, a missing source STL). Normal exports contain
    # only one visual and one simplified collision STL per link.
    for link_name, visual_parts in struct.additional_visuals.items():
        if link_name in grouped_visuals:
            continue
        for visual_info in visual_parts:
            component_name = visual_info[0]
            source_path = os.path.join(source_mesh_dir, component_name + ".stl")
            if os.path.isfile(source_path):
                _copy_mesh_as_binary_stl(
                    source_path,
                    os.path.join(meshes_dir, component_name + ".stl"),
                )
    _apply_diff_drive_cad_wheel_radius(
        controller_groups,
        struct.joints,
        collision_meshes,
        meshes_dir,
    )

    links_xyz: dict = {}
    root_origin_xyz, root_orientation_rpy = _root_link_pose(state, edited_tree)
    if root_joint_mode == "base_footprint":
        root_origin_xyz, root_orientation_rpy = _base_footprint_joint_pose(
            root_origin_xyz,
            root_orientation_rpy,
            edited_tree,
        )
    Write.write_urdf(
        struct.joints,
        links_xyz,
        struct.inertial,
        struct.materials,
        package_name,
        robot_name,
        save_dir,
        True,
        {
            link_name: grouped_visuals.get(link_name, visual_parts)
            for link_name, visual_parts in struct.additional_visuals.items()
        },
        fix_to_world,
        root_orientation_rpy,
        root_origin_xyz,
        collision_meshes,
        root_joint_mode,
    )
    Write.write_materials_xacro(export_colors, robot_name, save_dir)
    Write.write_transmissions_xacro(struct.joints, robot_name, save_dir)
    Write.write_gazebo_xacro(
        struct.joints,
        links_xyz,
        struct.inertial,
        package_name,
        robot_name,
        save_dir,
    )
    _write_ros_package_files(
        package_name,
        robot_name,
        save_dir,
        {
            "world": "world",
            "base_footprint": "base_footprint",
            "none": "base_link",
        }[root_joint_mode],
        controller_groups,
    )
    _write_gazebo_support(
        struct.joints,
        package_name,
        robot_name,
        save_dir,
        controller_groups,
        "base_footprint" if root_joint_mode == "base_footprint" else "base_link",
    )
    _write_analysis(state, struct, save_dir, moveit_readiness)
    if normalized_diff_drive_axes:
        axis_report = Path(save_dir, "analysis", "diff_drive_axis_normalization.json")
        axis_report.write_text(
            json.dumps(
                {
                    "normalized": True,
                    "flipped_joint_axes": normalized_diff_drive_axes,
                    "reason": "Aligned positive wheel velocity for REP-103 +X forward",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
            newline="\n",
        )

    moveit_dir = None
    if include_moveit and moveit_readiness["controlled_joint_count"]:
        assert bundle_dir is not None
        moveit_dir = os.path.join(bundle_dir, "src", moveit_package)
        with tempfile.TemporaryDirectory() as temporary_dir:
            seed_urdf = os.path.join(temporary_dir, f"{robot_name}.urdf")
            _write_moveit_seed_urdf(
                struct,
                robot_name,
                seed_urdf,
                fix_to_world,
                root_joint_mode,
            )
            generate_smoke_config(
                Path(save_dir),
                Path(seed_urdf),
                Path(moveit_dir),
                struct.joints,
                controller_groups,
            )
        _write_portable_moveit_helpers(
            bundle_dir,
            package_name,
            moveit_package,
            robot_name,
        )
    elif include_moveit:
        assert bundle_dir is not None
        Path(bundle_dir, "README_MOVEIT_KO.txt").write_text(
            "가동 관절이 없어 MoveIt 설정 패키지는 생성하지 않았습니다.\n",
            encoding="utf-8",
            newline="\n",
        )

    return {
        "save_dir": save_dir,
        "bundle_dir": bundle_dir,
        "moveit_dir": moveit_dir,
        "include_moveit": include_moveit,
        "archive_path": None,
        "package_name": package_name,
        "robot_name": robot_name,
        "link_count": len(struct.inertial),
        "joint_count": len(struct.joints),
        "moveit_readiness": moveit_readiness,
        "material_warnings": material_warnings,
    }
