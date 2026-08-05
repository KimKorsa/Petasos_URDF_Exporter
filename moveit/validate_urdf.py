from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree


MOVABLE_TYPES = {"revolute", "continuous", "prismatic"}
POSITION_LIMIT_TYPES = {"revolute", "prismatic"}
_REAL_LITERAL = re.compile(
    r"[-+]?(?:(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+)"
)


def _finite(value: str | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _explicit_real(value: str | None) -> bool:
    return bool(value and _REAL_LITERAL.fullmatch(value))


def validate_urdf_for_moveit(
    path: Path,
    require_ros2_control: bool = True,
) -> dict:
    path = Path(path)
    root = ElementTree.parse(path).getroot()
    errors: list[str] = []
    warnings: list[str] = []

    link_elements = root.findall("link")
    joint_elements = root.findall("joint")
    link_names = [element.get("name") for element in link_elements]
    joint_names = [element.get("name") for element in joint_elements]
    if None in link_names or len(link_names) != len(set(link_names)):
        errors.append("link names must be present and unique")
    if None in joint_names or len(joint_names) != len(set(joint_names)):
        errors.append("joint names must be present and unique")

    links = set(name for name in link_names if name)
    child_parents: dict[str, str] = {}
    adjacency = {name: [] for name in links}
    movable: dict[str, dict] = {}

    for element in joint_elements:
        name = element.get("name") or "<unnamed>"
        joint_type = element.get("type")
        parent_node = element.find("parent")
        child_node = element.find("child")
        parent = parent_node.get("link") if parent_node is not None else None
        child = child_node.get("link") if child_node is not None else None
        if parent not in links or child not in links:
            errors.append(f"{name}: parent/child link is missing")
            continue
        if parent == child:
            errors.append(f"{name}: parent and child cannot be the same link")
            continue
        if child in child_parents:
            errors.append(
                f"{child}: multiple parent joints ({child_parents[child]}, {name})"
            )
        child_parents[child] = name
        adjacency[parent].append(child)

        if joint_type not in MOVABLE_TYPES:
            continue
        axis = element.find("axis")
        axis_values = (
            [_finite(value) for value in axis.get("xyz", "").split()]
            if axis is not None
            else []
        )
        if (
            len(axis_values) != 3
            or any(value is None for value in axis_values)
            or math.sqrt(sum(value * value for value in axis_values)) <= 1e-9
        ):
            errors.append(f"{name}: movable joint axis is invalid")

        limit = element.find("limit")
        if limit is None:
            errors.append(f"{name}: movable joint limit element is missing")
            continue
        effort = _finite(limit.get("effort"))
        velocity = _finite(limit.get("velocity"))
        if effort is None or effort <= 0.0:
            errors.append(f"{name}: effort limit must be positive and finite")
        if velocity is None or velocity <= 0.0:
            errors.append(f"{name}: velocity limit must be positive and finite")
        if not _explicit_real(limit.get("effort")):
            errors.append(f"{name}: effort must be serialized as a real number")
        if not _explicit_real(limit.get("velocity")):
            errors.append(f"{name}: velocity must be serialized as a real number")

        lower = upper = None
        if joint_type in POSITION_LIMIT_TYPES:
            lower = _finite(limit.get("lower"))
            upper = _finite(limit.get("upper"))
            if lower is None or upper is None or lower >= upper:
                errors.append(f"{name}: lower limit must be smaller than upper")
            if not _explicit_real(limit.get("lower")):
                errors.append(f"{name}: lower limit must be serialized as a real number")
            if not _explicit_real(limit.get("upper")):
                errors.append(f"{name}: upper limit must be serialized as a real number")
        movable[name] = {
            "type": joint_type,
            "lower": lower,
            "upper": upper,
        }

    roots = sorted(links - set(child_parents))
    if len(roots) != 1:
        errors.append(
            "URDF must have exactly one root link; found "
            + (", ".join(roots) if roots else "none")
        )
    elif links:
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(link: str) -> None:
            if link in visiting:
                errors.append(f"kinematic cycle detected at {link}")
                return
            if link in visited:
                return
            visiting.add(link)
            for child_link in adjacency.get(link, []):
                visit(child_link)
            visiting.remove(link)
            visited.add(link)

        visit(roots[0])
        disconnected = sorted(links - visited)
        if disconnected:
            errors.append(
                "links disconnected from root: " + ", ".join(disconnected)
            )

    controls = root.findall("ros2_control")
    control = controls[0] if controls else None
    if movable and len(controls) > 1:
        errors.append(
            f"exactly one ros2_control block is required; found {len(controls)}"
        )
    if movable and control is None:
        message = "ros2_control is missing for movable joints"
        if require_ros2_control:
            errors.append(message)
        else:
            warnings.append(
                message
                + "; MoveIt Setup Assistant must provide the external FakeSystem"
            )
    control_joints = {}
    if control is not None:
        for element in control.findall("joint"):
            name = element.get("name")
            if not name:
                continue
            if name in control_joints:
                errors.append(f"{name}: duplicate ros2_control joint")
            control_joints[name] = element
    missing_control = sorted(set(movable) - set(control_joints))
    if missing_control and control is not None:
        errors.append(
            "movable joints missing from ros2_control: "
            + ", ".join(missing_control)
        )

    initial_positions = {}
    for name, data in movable.items():
        control_joint = control_joints.get(name)
        if control_joint is None:
            continue
        command_names = {
            element.get("name")
            for element in control_joint.findall("command_interface")
            if element.get("name")
        }
        state_names = {
            element.get("name")
            for element in control_joint.findall("state_interface")
            if element.get("name")
        }
        if command_names != {"position"}:
            errors.append(
                f"{name}: command interfaces must be exactly [position], "
                f"found {sorted(command_names)}"
            )
        position_state = control_joint.find("state_interface[@name='position']")
        velocity_state = control_joint.find("state_interface[@name='velocity']")
        if state_names != {"position", "velocity"}:
            errors.append(
                f"{name}: state interfaces must be exactly [position, velocity], "
                f"found {sorted(state_names)}"
            )
        if position_state is None or velocity_state is None:
            continue
        initial_node = position_state.find("param[@name='initial_value']")
        initial_text = initial_node.text.strip() if initial_node is not None and initial_node.text else None
        initial = _finite(initial_text)
        if initial is None:
            errors.append(f"{name}: finite ros2_control initial_value is required")
            continue
        if not _explicit_real(initial_text):
            errors.append(f"{name}: initial_value must be serialized as a real number")
        if data["type"] in POSITION_LIMIT_TYPES and not (
            data["lower"] <= initial <= data["upper"]
        ):
            errors.append(
                f"{name}: initial_value {initial} is outside "
                f"[{data['lower']}, {data['upper']}]"
            )
        initial_positions[name] = initial

    if not movable:
        warnings.append("robot has no movable joints; MoveIt cannot plan motion")

    return {
        "path": str(path),
        "robot": root.get("name"),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "root_link": roots[0] if len(roots) == 1 else None,
        "movable_joint_count": len(movable),
        "initial_positions": initial_positions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("urdf", type=Path)
    parser.add_argument(
        "--external-control",
        action="store_true",
        help="Allow a kinematics-only URDF when MoveIt supplies FakeSystem",
    )
    args = parser.parse_args()
    result = validate_urdf_for_moveit(
        args.urdf,
        require_ros2_control=not args.external_control,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
