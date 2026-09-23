from __future__ import annotations

import argparse
import itertools
import shutil
from pathlib import Path
from xml.etree import ElementTree


MOVABLE_TYPES = {"revolute", "continuous", "prismatic"}


def _real(value: float) -> str:
    text = format(float(value), ".15g")
    return text if any(mark in text for mark in ".eE") else text + ".0"


def _joint_data(urdf_path: Path) -> list[dict]:
    root = ElementTree.parse(urdf_path).getroot()
    joints = []
    for element in root.findall("joint"):
        joint_type = element.get("type", "fixed")
        if joint_type not in MOVABLE_TYPES:
            continue
        limit = element.find("limit")
        lower = float(limit.get("lower", "-3.141592653589793")) if limit is not None else -3.141592653589793
        upper = float(limit.get("upper", "3.141592653589793")) if limit is not None else 3.141592653589793
        initial = 0.0 if lower <= 0.0 <= upper else (lower + upper) / 2.0
        joints.append(
            {
                "name": element.get("name"),
                "type": joint_type,
                "parent": element.find("parent").get("link"),
                "child": element.find("child").get("link"),
                "lower": lower,
                "upper": upper,
                "initial": initial,
            }
        )
    if not joints:
        raise ValueError("MoveIt 시험에 사용할 가동 관절이 없습니다.")
    return joints


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def generate_smoke_config(
    description_package: Path,
    urdf_path: Path,
    output_dir: Path,
    joint_overrides: dict | None = None,
    controller_groups: list[dict] | None = None,
) -> dict:
    description_package = Path(description_package).resolve()
    urdf_path = Path(urdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    package_name = description_package.name
    robot_name = package_name.removesuffix("_description")
    moveit_package = f"{robot_name}_moveit_config"
    if output_dir.name != moveit_package:
        raise ValueError(
            f"출력 폴더 이름은 {moveit_package}이어야 합니다: {output_dir}"
        )
    joints = _joint_data(urdf_path)
    joint_overrides = joint_overrides or {}
    for joint in joints:
        override = joint_overrides.get(joint["name"], {})
        try:
            initial = float(override.get("initial_position", joint["initial"]))
        except (TypeError, ValueError):
            initial = joint["initial"]
        if joint["type"] != "continuous" and not joint["lower"] <= initial <= joint["upper"]:
            initial = (joint["lower"] + joint["upper"]) / 2.0
        joint["initial"] = initial
    robot_root = ElementTree.parse(urdf_path).getroot()
    all_links = [
        element.get("name")
        for element in robot_root.findall("link")
        if element.get("name")
    ]
    links = [name for name in all_links if name != "world"]
    child_links = {
        element.find("child").get("link")
        for element in robot_root.findall("joint")
        if element.find("child") is not None
    }
    roots = [name for name in all_links if name not in child_links]
    fixed_frame = roots[0] if len(roots) == 1 else (
        "world" if "world" in all_links else "base_link"
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "config").mkdir(parents=True)
    (output_dir / "launch").mkdir()

    _write(
        output_dir / "package.xml",
        f"""
<?xml version="1.0"?>
<package format="3">
  <name>{moveit_package}</name>
  <version>0.1.0</version>
  <description>Petasos A2 MoveIt smoke-test configuration for {robot_name}</description>
  <maintainer email="contact@petasos.dev">Petasos</maintainer>
  <license>MIT</license>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <exec_depend>{package_name}</exec_depend>
  <exec_depend>moveit_configs_utils</exec_depend>
  <exec_depend>moveit_ros_move_group</exec_depend>
  <exec_depend>moveit_planners_ompl</exec_depend>
  <exec_depend>moveit_ros_visualization</exec_depend>
  <exec_depend>moveit_simple_controller_manager</exec_depend>
  <exec_depend>controller_manager</exec_depend>
  <exec_depend>joint_trajectory_controller</exec_depend>
  <exec_depend>joint_state_broadcaster</exec_depend>
  <exec_depend>robot_state_publisher</exec_depend>
  <exec_depend>xacro</exec_depend>
  <export><build_type>ament_cmake</build_type></export>
</package>
""",
    )
    _write(
        output_dir / "CMakeLists.txt",
        f"""
cmake_minimum_required(VERSION 3.22)
project({moveit_package})
find_package(ament_cmake REQUIRED)
install(DIRECTORY config launch DESTINATION share/${{PROJECT_NAME}})
install(FILES .setup_assistant DESTINATION share/${{PROJECT_NAME}})
ament_package()
""",
    )
    _write(
        output_dir / ".setup_assistant",
        f"""
moveit_setup_assistant_config:
  urdf:
    package: {package_name}
    relative_path: urdf/{robot_name}.xacro
  srdf:
    relative_path: config/{robot_name}.srdf
  package_settings:
    author_name: Petasos
    author_email: contact@petasos.dev
    generated_timestamp: 0
""",
    )

    group_joints = "\n".join(
        f'    <joint name="{joint["name"]}"/>' for joint in joints
    )
    home_joints = "\n".join(
        f'    <joint name="{joint["name"]}" value="{_real(joint["initial"])}"/>'
        for joint in joints
    )
    adjacent = {
        tuple(sorted((joint["parent"], joint["child"])))
        for joint in joints
        if "world" not in (joint["parent"], joint["child"])
    }
    disabled_collisions = "\n".join(
        f'  <disable_collisions link1="{left}" link2="{right}" reason="Adjacent"/>'
        for left, right in sorted(adjacent)
    )
    _write(
        output_dir / "config" / f"{robot_name}.srdf",
        f"""
<?xml version="1.0" encoding="UTF-8"?>
<robot name="{robot_name}">
  <group name="arm">
{group_joints}
  </group>
  <group_state group="arm" name="home">
{home_joints}
  </group_state>
{disabled_collisions}
</robot>
""",
    )
    _write(
        output_dir / "config" / "kinematics.yaml",
        """
arm:
  kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  kinematics_solver_search_resolution: 0.005
  kinematics_solver_timeout: 0.1
""",
    )
    _write(
        output_dir / "config" / "sensors_3d.yaml",
        """
sensors: []
""",
    )

    limit_blocks = []
    for joint in joints:
        override = joint_overrides.get(joint["name"], {})
        max_velocity = float(override.get("velocity_limit", 1.0))
        max_acceleration = float(override.get("max_acceleration", 1.0))
        limit_blocks.extend(
            [
                f'  {joint["name"]}:',
                "    has_velocity_limits: true",
                f"    max_velocity: {_real(max_velocity)}",
                "    has_acceleration_limits: true",
                f"    max_acceleration: {_real(max_acceleration)}",
            ]
        )
        if override.get("max_deceleration") is not None:
            limit_blocks.append(
                f'    max_deceleration: {_real(float(override["max_deceleration"]))}'
            )
        if override.get("max_jerk") is not None:
            limit_blocks.append(f'    max_jerk: {_real(float(override["max_jerk"]))}')
    _write(
        output_dir / "config" / "joint_limits.yaml",
        "joint_limits:\n" + "\n".join(limit_blocks),
    )
    _write(
        output_dir / "config" / "ompl_planning.yaml",
        """
planning_plugin: ompl_interface/OMPLPlanner
request_adapters: >-
  default_planner_request_adapters/AddTimeOptimalParameterization
  default_planner_request_adapters/ResolveConstraintFrames
  default_planner_request_adapters/FixWorkspaceBounds
  default_planner_request_adapters/FixStartStateBounds
  default_planner_request_adapters/FixStartStateCollision
  default_planner_request_adapters/FixStartStatePathConstraints
start_state_max_bounds_error: 0.1
planner_configs:
  RRTConnectkConfigDefault:
    type: geometric::RRTConnect
    range: 0.0
arm:
  planner_configs:
    - RRTConnectkConfigDefault
""",
    )

    joint_name_set = {joint["name"] for joint in joints}
    groups = []
    claimed = set()
    for raw in controller_groups or []:
        group_joints = [
            name for name in raw.get("joints") or []
            if name in joint_name_set and name not in claimed
        ]
        if not group_joints:
            continue
        claimed.update(group_joints)
        groups.append({"name": raw["name"], "joints": group_joints})
    unassigned = [joint["name"] for joint in joints if joint["name"] not in claimed]
    if unassigned:
        used_names = {group["name"] for group in groups}
        groups.append({
            "name": "arm_controller" if "arm_controller" not in used_names else "unassigned_controller",
            "joints": unassigned,
        })
    if not groups and joints:
        groups = [{"name": "arm_controller", "joints": [joint["name"] for joint in joints]}]

    moveit_controller_names = "\n".join(f"    - {group['name']}" for group in groups)
    moveit_controller_blocks = []
    ros_manager_blocks = []
    ros_controller_blocks = []
    for group_index, group in enumerate(groups):
        group_joint_lines = "\n".join(f"      - {name}" for name in group["joints"])
        moveit_controller_blocks.extend([
            f"  {group['name']}:",
            "    action_ns: follow_joint_trajectory",
            "    type: FollowJointTrajectory",
            f"    default: {'true' if group_index == 0 else 'false'}",
            "    joints:",
            group_joint_lines,
        ])
        ros_manager_blocks.extend([
            f"    {group['name']}:",
            "      type: joint_trajectory_controller/JointTrajectoryController",
        ])
        command_interfaces = None
        state_interfaces = None
        for name in group["joints"]:
            override = joint_overrides.get(name, {})
            command = override.get("command_interface", "position")
            joint_commands = {command}
            joint_states = set(override.get("state_interfaces") or ["position"])
            command_interfaces = joint_commands if command_interfaces is None else command_interfaces & joint_commands
            state_interfaces = joint_states if state_interfaces is None else state_interfaces & joint_states
        command_interfaces = [value for value in ("position", "velocity", "effort") if value in command_interfaces]
        state_interfaces = [value for value in ("position", "velocity") if value in state_interfaces]
        if not command_interfaces or "position" not in state_interfaces:
            raise ValueError(
                f"MoveIt controller '{group['name']}' has no common trajectory "
                "command interface and position state across its joints; split the controller group"
            )
        ros_controller_blocks.extend([
            "",
            f"{group['name']}:",
            "  ros__parameters:",
            "    command_interfaces:",
            *[f"      - {value}" for value in command_interfaces],
            "    state_interfaces:",
            *[f"      - {value}" for value in state_interfaces],
            "    joints:",
            *[f"      - {name}" for name in group["joints"]],
        ])
    _write(
        output_dir / "config" / "moveit_controllers.yaml",
        f"""
trajectory_execution:
  allowed_execution_duration_scaling: 1.2
  allowed_goal_duration_margin: 0.5
  allowed_start_tolerance: 0.05
  trajectory_duration_monitoring: true

moveit_controller_manager: moveit_simple_controller_manager/MoveItSimpleControllerManager

moveit_simple_controller_manager:
  controller_names:
{moveit_controller_names}
{chr(10).join(moveit_controller_blocks)}
""",
    )
    _write(
        output_dir / "config" / "ros2_controllers.yaml",
        f"""
controller_manager:
  ros__parameters:
    update_rate: 100
{chr(10).join(ros_manager_blocks)}
    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster
{chr(10).join(ros_controller_blocks)}
""",
    )
    _write(
        output_dir / "config" / "initial_positions.yaml",
        "initial_positions:\n"
        + "\n".join(
            f'  {joint["name"]}: {_real(joint["initial"])}' for joint in joints
        ),
    )
    _write(
        output_dir / "config" / "moveit.rviz",
        f"""
Panels:
  - Class: rviz_common/Displays
    Name: Displays
Visualization Manager:
  Displays:
    - Alpha: 0.5
      Cell Size: 0.1
      Class: rviz_default_plugins/Grid
      Enabled: true
      Name: Grid
      Plane: XY
      Plane Cell Count: 30
      Reference Frame: <Fixed Frame>
      Value: true
    - Class: moveit_rviz_plugin/MotionPlanning
      Enabled: true
      Move Group Namespace: ""
      Name: MotionPlanning
      Planning Scene Topic: /monitored_planning_scene
      Robot Description: robot_description
      Planning Request:
        Planning Group: arm
      Value: true
  Enabled: true
  Global Options:
    Background Color: 48; 48; 48
    Fixed Frame: {fixed_frame}
    Frame Rate: 30
  Name: root
  Tools:
    - Class: rviz_default_plugins/Interact
    - Class: rviz_default_plugins/MoveCamera
    - Class: rviz_default_plugins/Select
    - Class: rviz_default_plugins/FocusCamera
  Value: true
  Views:
    Current:
      Class: rviz_default_plugins/Orbit
      Distance: 1.5
      Focal Point:
        X: 0.0
        Y: 0.0
        Z: 0.3
      Pitch: 0.6
      Target Frame: <Fixed Frame>
      Value: Orbit (rviz)
      Yaw: 5.5
Window Geometry:
  Height: 900
  Width: 1500
""",
    )

    launch_generators = {
        "demo.launch.py": "generate_demo_launch",
        "rsp.launch.py": "generate_rsp_launch",
        "move_group.launch.py": "generate_move_group_launch",
        "moveit_rviz.launch.py": "generate_moveit_rviz_launch",
        "spawn_controllers.launch.py": "generate_spawn_controllers_launch",
        "static_virtual_joint_tfs.launch.py": "generate_static_virtual_joint_tfs_launch",
        "warehouse_db.launch.py": "generate_warehouse_db_launch",
    }
    for filename, generator in launch_generators.items():
        _write(
            output_dir / "launch" / filename,
            f"""
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import {generator}


def generate_launch_description():
    moveit_config = (
        MoveItConfigsBuilder(
            "{robot_name}",
            package_name="{moveit_package}",
        )
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )
    return {generator}(moveit_config)
""",
        )

    return {
        "robot_name": robot_name,
        "package_name": moveit_package,
        "joints": joints,
        "links": links,
        "output_dir": str(output_dir),
        "warning": "Smoke-test config disables only adjacent-link collisions.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("description_package", type=Path)
    parser.add_argument("urdf_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = generate_smoke_config(
        args.description_package,
        args.urdf_path,
        args.output_dir,
    )
    print(
        f'{result["package_name"]}: {len(result["joints"])} movable joints, '
        f'{len(result["links"])} links'
    )
    for joint in result["joints"]:
        print(
            f'{joint["name"]}: initial={_real(joint["initial"])} '
            f'limits=[{_real(joint["lower"])}, {_real(joint["upper"])}]'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
