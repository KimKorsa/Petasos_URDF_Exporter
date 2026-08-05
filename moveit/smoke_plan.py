from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree

import rclpy
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, MoveItErrorCodes
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState


class MoveItSmokePlanner(Node):
    def __init__(self) -> None:
        super().__init__("petasos_moveit_smoke_planner")
        self.client = ActionClient(self, MoveGroup, "/move_action")
        self.current_positions: dict[str, float] = {}
        self.create_subscription(
            JointState,
            "/joint_states",
            self._joint_state_callback,
            10,
        )

    def _joint_state_callback(self, message: JointState) -> None:
        self.current_positions.update(
            dict(zip(message.name, message.position))
        )

    def wait_for_joint_state(self) -> dict[str, float]:
        deadline = self.get_clock().now().nanoseconds + 10_000_000_000
        while (
            not self.current_positions
            and self.get_clock().now().nanoseconds < deadline
        ):
            rclpy.spin_once(self, timeout_sec=0.2)
        if not self.current_positions:
            raise RuntimeError("/joint_states를 10초 안에 받지 못했습니다.")
        return dict(self.current_positions)

    def execute(self, group: str, targets: dict[str, float]) -> dict:
        if not self.client.wait_for_server(timeout_sec=15.0):
            raise RuntimeError("/move_action 서버가 15초 안에 준비되지 않았습니다.")

        constraints = Constraints(name="petasos_smoke_goal")
        constraints.joint_constraints = [
            JointConstraint(
                joint_name=name,
                position=float(position),
                tolerance_above=0.001,
                tolerance_below=0.001,
                weight=1.0,
            )
            for name, position in targets.items()
        ]

        goal = MoveGroup.Goal()
        goal.request.group_name = group
        goal.request.goal_constraints = [constraints]
        goal.request.num_planning_attempts = 5
        goal.request.allowed_planning_time = 10.0
        goal.request.max_velocity_scaling_factor = 0.1
        goal.request.max_acceleration_scaling_factor = 0.1
        goal.planning_options.plan_only = False
        goal.planning_options.replan = False

        goal_future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, goal_future, timeout_sec=20.0)
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            raise RuntimeError("MoveGroup가 시험 목표를 거절했습니다.")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=60.0)
        wrapped = result_future.result()
        if wrapped is None:
            raise RuntimeError("MoveGroup 결과가 60초 안에 도착하지 않았습니다.")

        result = wrapped.result
        planned = result.planned_trajectory.joint_trajectory
        executed = result.executed_trajectory.joint_trajectory
        summary = {
            "status": int(wrapped.status),
            "error_code": int(result.error_code.val),
            "success": result.error_code.val == MoveItErrorCodes.SUCCESS,
            "planning_time": float(result.planning_time),
            "planned_joint_names": list(planned.joint_names),
            "planned_points": len(planned.points),
            "executed_points": len(executed.points),
            "target": targets,
        }
        if planned.points:
            summary["planned_final"] = list(planned.points[-1].positions)
        if executed.points:
            summary["executed_final"] = list(executed.points[-1].positions)
        actual = {
            name: self.current_positions.get(name)
            for name in targets
            if name in self.current_positions
        }
        summary["actual_final"] = actual
        if actual:
            summary["max_target_error"] = max(
                abs(actual[name] - targets[name]) for name in actual
            )
            summary["success"] = (
                summary["success"]
                and summary["max_target_error"] <= 0.01
            )
        return summary


def _first_srdf_group(srdf_path: Path) -> str:
    root = ElementTree.parse(srdf_path).getroot()
    group = root.find("group")
    if group is None or not group.get("name"):
        raise ValueError(f"SRDF에서 planning group을 찾지 못했습니다: {srdf_path}")
    return group.get("name")


def _automatic_targets(
    urdf_path: Path,
    current: dict[str, float],
) -> dict[str, float]:
    root = ElementTree.parse(urdf_path).getroot()
    targets: dict[str, float] = {}
    for joint in root.findall("joint"):
        name = joint.get("name")
        if name not in current or joint.get("type") not in {
            "revolute",
            "continuous",
            "prismatic",
        }:
            continue
        limit = joint.find("limit")
        if joint.get("type") == "continuous":
            lower, upper = -3.141592653589793, 3.141592653589793
        elif limit is not None:
            lower = float(limit.get("lower"))
            upper = float(limit.get("upper"))
        else:
            continue
        position = current[name]
        delta = min(0.2, max((upper - lower) * 0.08, 0.01))
        candidate = position + delta
        if candidate >= upper - 0.001:
            candidate = position - delta
        targets[name] = min(max(candidate, lower + 0.001), upper - 0.001)
    if not targets:
        raise ValueError("자동 움직임 시험에 사용할 가동 관절을 찾지 못했습니다.")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group")
    parser.add_argument("--srdf", type=Path)
    parser.add_argument("--urdf", type=Path)
    parser.add_argument("--targets")
    args = parser.parse_args()

    rclpy.init()
    node = MoveItSmokePlanner()
    try:
        group = args.group or (
            _first_srdf_group(args.srdf) if args.srdf else "arm"
        )
        if args.targets:
            targets = json.loads(args.targets)
        elif args.urdf:
            targets = _automatic_targets(
                args.urdf,
                node.wait_for_joint_state(),
            )
        else:
            targets = {
                "joint_1": 0.2,
                "joint_2": 0.3,
                "joint_3": -2.7,
                "joint_4": -0.2,
            }
        result = node.execute(group, targets)
        print("PETASOS_MOVEIT_SMOKE_RESULT=" + json.dumps(result, sort_keys=True))
        return 0 if result["success"] else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
