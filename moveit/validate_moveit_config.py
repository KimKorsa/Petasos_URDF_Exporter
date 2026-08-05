from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree

try:
    from moveit.validate_urdf import validate_urdf_for_moveit
except ModuleNotFoundError:
    from validate_urdf import validate_urdf_for_moveit


FLOAT_PARAMETER_KEYS = {
    "default_velocity_scaling_factor",
    "default_acceleration_scaling_factor",
    "min_position",
    "max_position",
    "max_velocity",
    "max_acceleration",
    "max_deceleration",
    "max_jerk",
}

_NUMBER_LINE = re.compile(
    r"^(?P<prefix>\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*):\s*)"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?P<suffix>\s*(?:#.*)?)$"
)
_FLOAT_LITERAL = re.compile(
    r"[-+]?(?:(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+)"
)


def repair_yaml_reals(path: Path, fix: bool = False) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")

    original = path.read_text(encoding="utf-8")
    output_lines = []
    repaired = []
    invalid = []

    for line_number, line in enumerate(original.splitlines(), start=1):
        match = _NUMBER_LINE.match(line)
        if not match or match.group("key") not in FLOAT_PARAMETER_KEYS:
            output_lines.append(line)
            continue

        value = match.group("value")
        if _FLOAT_LITERAL.fullmatch(value):
            output_lines.append(line)
            continue

        if fix and re.fullmatch(r"[-+]?\d+", value):
            line = (
                match.group("prefix")
                + value
                + ".0"
                + match.group("suffix")
            )
            repaired.append({
                "line": line_number,
                "key": match.group("key"),
                "before": value,
                "after": value + ".0",
            })
        else:
            invalid.append({
                "line": line_number,
                "key": match.group("key"),
                "value": value,
            })
        output_lines.append(line)

    if fix and repaired:
        trailing_newline = "\n" if original.endswith(("\n", "\r")) else ""
        path.write_text(
            "\n".join(output_lines) + trailing_newline,
            encoding="utf-8",
        )

    return {
        "path": str(path),
        "valid": not invalid,
        "repaired": repaired,
        "invalid": invalid,
    }


def repair_joint_limits(path: Path, fix: bool = False) -> dict:
    return repair_yaml_reals(path, fix=fix)


def _joint_limit_names(path: Path) -> set[str]:
    names = set()
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.fullmatch(r"\s*joint_limits:\s*(?:#.*)?", line):
            in_section = True
            continue
        if not in_section or not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(?:#.*)?$", line)
        if match:
            names.add(match.group(1))
        elif not line.startswith((" ", "\t")):
            break
    return names


def _urdf_movable_joint_defaults(path: Path) -> dict[str, float]:
    defaults = {}
    root = ElementTree.parse(path).getroot()
    for joint in root.findall("joint"):
        if joint.get("type") not in {"revolute", "continuous", "prismatic"}:
            continue
        limit = joint.find("limit")
        velocity = 1.0
        if limit is not None:
            try:
                parsed = float(limit.get("velocity", "1.0"))
                if parsed > 0:
                    velocity = parsed
            except (TypeError, ValueError):
                pass
        defaults[joint.get("name")] = velocity
    return defaults


def _append_missing_joint_limits(
    path: Path,
    defaults: dict[str, float],
    missing: set[str],
) -> list[str]:
    if not missing:
        return []
    text = path.read_text(encoding="utf-8")
    if not re.search(r"(?m)^\s*joint_limits:\s*$", text):
        text = text.rstrip() + "\njoint_limits:\n"
    blocks = []
    for name in sorted(missing):
        blocks.append(
            f"  {name}:\n"
            "    has_velocity_limits: true\n"
            f"    max_velocity: {float(defaults[name])}\n"
            "    has_acceleration_limits: true\n"
            "    max_acceleration: 1.0\n"
        )
    path.write_text(text.rstrip() + "\n" + "".join(blocks), encoding="utf-8")
    return sorted(missing)


def _real(value: float) -> str:
    text = format(float(value), ".15g")
    return text if any(mark in text for mark in ".eE") else text + ".0"


def _urdf_initial_position_rules(path: Path) -> dict[str, dict[str, float]]:
    rules = {}
    root = ElementTree.parse(path).getroot()
    for joint in root.findall("joint"):
        joint_type = joint.get("type")
        if joint_type not in {"revolute", "continuous", "prismatic"}:
            continue
        lower = upper = None
        if joint_type in {"revolute", "prismatic"}:
            limit = joint.find("limit")
            if limit is None:
                continue
            try:
                lower = float(limit.get("lower"))
                upper = float(limit.get("upper"))
            except (TypeError, ValueError):
                continue
        safe = (
            0.0
            if joint_type == "continuous" or lower <= 0.0 <= upper
            else (lower + upper) / 2.0
        )
        rules[joint.get("name")] = {
            "lower": lower,
            "upper": upper,
            "safe": safe,
        }
    return rules


def repair_initial_positions(
    path: Path,
    rules: dict[str, dict[str, float]],
    fix: bool = False,
) -> dict:
    path = Path(path)
    if not path.is_file():
        return {
            "path": str(path),
            "valid": False,
            "invalid": ["initial_positions.yaml is missing"],
            "repaired": [],
        }

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    values: dict[str, tuple[int, str, float | None]] = {}
    in_section = False
    for index, line in enumerate(lines):
        if re.fullmatch(r"\s*initial_positions:\s*(?:#.*)?", line):
            in_section = True
            continue
        if not in_section or not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(
            r"^(?P<prefix>\s{2,})(?P<name>[A-Za-z_][A-Za-z0-9_]*):\s*"
            r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
            r"(?P<suffix>\s*(?:#.*)?)$",
            line,
        )
        if match:
            try:
                parsed = float(match.group("value"))
            except ValueError:
                parsed = None
            values[match.group("name")] = (index, match.group("prefix"), parsed)
        elif not line.startswith((" ", "\t")):
            break

    invalid = []
    repaired = []
    for name, rule in rules.items():
        found = values.get(name)
        value = found[2] if found else None
        inside = value is not None and (
            rule["lower"] is None
            or rule["lower"] <= value <= rule["upper"]
        )
        if not inside:
            invalid.append(name)
        needs_real = found is not None and not _FLOAT_LITERAL.fullmatch(
            re.search(
                r":\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)",
                lines[found[0]],
            ).group(1)
        )
        if fix and found is not None and (not inside or needs_real):
            replacement = value if inside else rule["safe"]
            lines[found[0]] = f"{found[1]}{name}: {_real(replacement)}"
            repaired.append(name)
        elif fix and found is None:
            repaired.append(name)

    if fix:
        missing = [name for name in rules if name not in values]
        if missing:
            if not any(
                re.fullmatch(r"\s*initial_positions:\s*(?:#.*)?", line)
                for line in lines
            ):
                lines.extend(["", "initial_positions:"])
            lines.extend(f"  {name}: {_real(rules[name]['safe'])}" for name in missing)
        if repaired:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return repair_initial_positions(path, rules, fix=False) | {
            "repaired": sorted(set(repaired))
        }

    return {
        "path": str(path),
        "valid": not invalid,
        "invalid": sorted(invalid),
        "repaired": [],
    }


def repair_moveit_controller_actions(path: Path, fix: bool = False) -> dict:
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    missing: list[tuple[int, str, str]] = []

    for index, line in enumerate(lines):
        match = re.match(
            r"^(?P<indent>\s*)type:\s*FollowJointTrajectory\s*(?:#.*)?$",
            line,
        )
        if not match:
            continue
        type_indent = len(match.group("indent").expandtabs(2))
        block_start = -1
        block_indent = -1
        block_name = "<controller>"
        for cursor in range(index - 1, -1, -1):
            stripped = lines[cursor].strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(lines[cursor]) - len(lines[cursor].lstrip())
            if indent < type_indent and stripped.endswith(":"):
                block_start = cursor
                block_indent = indent
                block_name = stripped[:-1]
                break
        block_end = len(lines)
        if block_start >= 0:
            for cursor in range(index + 1, len(lines)):
                stripped = lines[cursor].strip()
                if not stripped or stripped.startswith("#"):
                    continue
                indent = len(lines[cursor]) - len(lines[cursor].lstrip())
                if indent <= block_indent:
                    block_end = cursor
                    break
        if not any(
            re.match(r"^\s*action_ns:\s*follow_joint_trajectory\s*(?:#.*)?$", item)
            for item in lines[block_start + 1:block_end]
        ):
            missing.append((index, match.group("indent"), block_name))

    if fix and missing:
        for index, indent, _ in reversed(missing):
            lines.insert(index, f"{indent}action_ns: follow_joint_trajectory")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return repair_moveit_controller_actions(path, fix=False) | {
            "repaired": [name for _, _, name in missing]
        }
    return {
        "path": str(path),
        "valid": not missing,
        "missing_action_ns": [name for _, _, name in missing],
        "repaired": [],
    }


def repair_ros2_command_interfaces(path: Path, fix: bool = False) -> dict:
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    invalid = []
    replacements: list[tuple[int, int, str]] = []

    index = 0
    while index < len(lines):
        match = re.match(
            r"^(?P<indent>\s*)(?P<section>command|state)_interfaces:"
            r"\s*(?P<inline>.*)$",
            lines[index],
        )
        if not match:
            index += 1
            continue
        indent_text = match.group("indent")
        indent = len(indent_text.expandtabs(2))
        section = match.group("section")
        expected = (
            ["position"]
            if section == "command"
            else ["position", "velocity"]
        )
        inline = match.group("inline").strip()
        end = index + 1
        values = []
        if inline:
            values = [
                item.strip().strip("'\"")
                for item in inline.strip("[]").split(",")
                if item.strip()
            ]
        else:
            while end < len(lines):
                stripped = lines[end].strip()
                current_indent = len(lines[end]) - len(lines[end].lstrip())
                if stripped and not stripped.startswith("#") and current_indent <= indent:
                    break
                item = re.match(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)", lines[end])
                if item:
                    values.append(item.group(1))
                end += 1
        if values != expected:
            invalid.append({
                "line": index + 1,
                "section": f"{section}_interfaces",
                "interfaces": values,
            })
            replacements.append((index, end, indent_text, section, expected))
        index = max(end, index + 1)

    if fix and replacements:
        for start, end, indent_text, section, expected in reversed(replacements):
            lines[start:end] = [
                f"{indent_text}{section}_interfaces:",
                *(
                    f"{indent_text}  - {interface}"
                    for interface in expected
                ),
            ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return repair_ros2_command_interfaces(path, fix=False) | {
            "repaired": invalid
        }
    return {
        "path": str(path),
        "valid": not invalid,
        "invalid": invalid,
        "repaired": [],
    }


def validate_moveit_package(
    package_dir: Path,
    fix: bool = False,
    urdf_path: Path | None = None,
    external_control: bool = False,
) -> dict:
    package_dir = Path(package_dir)
    config_dir = package_dir / "config"
    required = [
        package_dir / "package.xml",
        package_dir / ".setup_assistant",
        config_dir / "joint_limits.yaml",
        config_dir / "kinematics.yaml",
        config_dir / "moveit_controllers.yaml",
        config_dir / "ros2_controllers.yaml",
        config_dir / "initial_positions.yaml",
        package_dir / "launch" / "demo.launch.py",
    ]
    srdf_files = sorted(config_dir.glob("*.srdf"))
    if not srdf_files:
        required.append(config_dir / "<robot>.srdf")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {
            "package": str(package_dir),
            "valid": False,
            "missing": missing,
            "joint_limits": None,
            "errors": ["MoveIt Assistant configuration is incomplete"],
        }

    errors = []
    repaired = []
    setup_assistant_text = (package_dir / ".setup_assistant").read_text(
        encoding="utf-8"
    )
    if not re.search(
        r"(?m)^\s{2}(?:package_settings|CONFIG):\s*$",
        setup_assistant_text,
    ):
        errors.append(
            ".setup_assistant has no package_settings metadata required by "
            "MoveIt Setup Assistant"
        )
    yaml_results = []
    for yaml_path in sorted(config_dir.glob("*.yaml")):
        result = repair_yaml_reals(yaml_path, fix=fix)
        yaml_results.append(result)
        repaired.extend(result["repaired"])

    urdf_result = None
    added_joint_limits = []
    if urdf_path is not None:
        urdf_path = Path(urdf_path)
        urdf_result = validate_urdf_for_moveit(
            urdf_path,
            require_ros2_control=not external_control,
        )
        if not urdf_result["valid"]:
            errors.extend(urdf_result["errors"])
        defaults = _urdf_movable_joint_defaults(urdf_path)
        existing = _joint_limit_names(config_dir / "joint_limits.yaml")
        missing_joints = set(defaults) - existing
        if fix:
            added_joint_limits = _append_missing_joint_limits(
                config_dir / "joint_limits.yaml",
                defaults,
                missing_joints,
            )
            missing_joints = set()
        if missing_joints:
            errors.append(
                "joint_limits.yaml is missing movable joints: "
                + ", ".join(sorted(missing_joints))
            )

    srdf_root = ElementTree.parse(srdf_files[0]).getroot()
    groups = [
        group
        for group in srdf_root.findall("group")
        if group.get("name") and list(group)
    ]
    if not groups:
        errors.append("SRDF has no non-empty planning group")

    action_result = repair_moveit_controller_actions(
        config_dir / "moveit_controllers.yaml",
        fix=fix,
    )
    command_result = repair_ros2_command_interfaces(
        config_dir / "ros2_controllers.yaml",
        fix=fix,
    )
    initial_result = None
    if urdf_path is not None:
        initial_result = repair_initial_positions(
            config_dir / "initial_positions.yaml",
            _urdf_initial_position_rules(urdf_path),
            fix=fix,
        )

    moveit_controllers = (config_dir / "moveit_controllers.yaml").read_text(
        encoding="utf-8"
    )
    ros2_controllers = (config_dir / "ros2_controllers.yaml").read_text(
        encoding="utf-8"
    )
    if "FollowJointTrajectory" not in moveit_controllers:
        errors.append("moveit_controllers.yaml has no FollowJointTrajectory controller")
    if "JointTrajectoryController" not in ros2_controllers:
        errors.append("ros2_controllers.yaml has no JointTrajectoryController")
    if "joint_state_broadcaster" not in ros2_controllers:
        errors.append("ros2_controllers.yaml has no joint_state_broadcaster")
    if not action_result["valid"]:
        errors.append(
            "MoveIt FollowJointTrajectory controller has no "
            "action_ns: follow_joint_trajectory"
        )
    if not command_result["valid"]:
        errors.append(
            "JointTrajectoryController interfaces must use position commands "
            "and position/velocity states"
        )
    if initial_result is not None and not initial_result["valid"]:
        errors.append(
            "initial_positions.yaml has joints outside their URDF limits: "
            + ", ".join(initial_result["invalid"])
        )

    limits = next(
        result
        for result in yaml_results
        if Path(result["path"]).name == "joint_limits.yaml"
    )
    if fix:
        checked = repair_joint_limits(
            config_dir / "joint_limits.yaml",
            fix=False,
        )
        limits = checked | {"repaired": repaired}
    if not limits["valid"]:
        errors.append("MoveIt YAML contains integer values where doubles are required")
    return {
        "package": str(package_dir),
        "valid": not errors,
        "missing": [],
        "joint_limits": limits,
        "yaml_files": yaml_results,
        "urdf": urdf_result,
        "planning_groups": [group.get("name") for group in groups],
        "added_joint_limits": added_joint_limits,
        "controller_actions": action_result,
        "command_interfaces": command_result,
        "initial_positions": initial_result,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--urdf", type=Path)
    parser.add_argument("--external-control", action="store_true")
    args = parser.parse_args()
    result = validate_moveit_package(
        args.package_dir,
        fix=args.fix,
        urdf_path=args.urdf,
        external_control=args.external_control,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
