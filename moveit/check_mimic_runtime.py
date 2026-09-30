"""Headless ROS 2 Humble mimic smoke test; run after sourcing /opt/ros/humble.

Uses a fresh ROS domain and a tiny GenericSystem robot, never the user's live
robot/controller process. Exits nonzero when a follower fails the real state
relationship; static XML checks alone are not considered a runtime pass.
Humble GenericSystem supports mimic multipliers but not URDF mimic offsets, so
this smoke covers the user's zero-offset gripper case only. Nonzero offsets
need a Gazebo runtime check rather than an assumed mock pass.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


URDF = """<robot name="petasos_mimic_smoke">
  <link name="palm"/><link name="left"/><link name="right"/>
  <joint name="joint_7" type="prismatic"><parent link="palm"/><child link="left"/>
    <axis xyz="1 0 0"/><limit lower="0" upper="0.01" effort="10" velocity="1"/></joint>
  <joint name="joint_8" type="prismatic"><parent link="palm"/><child link="right"/>
    <axis xyz="-1 0 0"/><limit lower="-0.01" upper="0" effort="10" velocity="1"/>
    <mimic joint="joint_7" multiplier="-1" offset="0"/></joint>
  <ros2_control name="PetasosMimicSmoke" type="system">
    <hardware><plugin>mock_components/GenericSystem</plugin></hardware>
    <joint name="joint_7"><command_interface name="position"/>
      <state_interface name="position"/><state_interface name="velocity"/></joint>
    <joint name="joint_8"><param name="mimic">joint_7</param>
      <param name="multiplier">-1</param><command_interface name="position"/>
      <state_interface name="position"/><state_interface name="velocity"/></joint>
  </ros2_control>
</robot>"""


def main() -> int:
    try:
        import rclpy
        from sensor_msgs.msg import JointState
        from std_msgs.msg import Float64MultiArray
    except ImportError as error:
        print(f"UNVERIFIED: ROS 2 Python runtime is unavailable: {error}", file=sys.stderr)
        return 2

    domain = str(100 + os.getpid() % 100)
    env = dict(os.environ, ROS_DOMAIN_ID=domain)
    processes = []
    with tempfile.TemporaryDirectory(prefix="petasos-mimic-smoke-") as temp:
        params = Path(temp) / "controllers.yaml"
        params.write_text("""controller_manager:
  ros__parameters:
    update_rate: 100
    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster
    driver:
      type: forward_command_controller/ForwardCommandController
driver:
  ros__parameters:
    joints: [joint_7]
    interface_name: position
""", encoding="utf-8")
        log_path = Path(temp) / "ros.log"
        try:
            with log_path.open("w+", encoding="utf-8") as log:
                processes.append(subprocess.Popen(
                    ["ros2", "run", "controller_manager", "ros2_control_node",
                     "--ros-args", "-p", f"robot_description:={URDF}",
                     "--params-file", str(params)],
                    env=env, stdout=log, stderr=subprocess.STDOUT,
                ))
                for controller in ("joint_state_broadcaster", "driver"):
                    result = subprocess.run(
                        ["ros2", "run", "controller_manager", "spawner", controller,
                         "--controller-manager", "/controller_manager",
                         "--controller-manager-timeout", "20"],
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, timeout=30,
                    )
                    if result.returncode:
                        log.flush()
                        print(result.stdout, file=sys.stderr)
                        print(log_path.read_text(encoding="utf-8"), file=sys.stderr)
                        return 1
                previous_domain = os.environ.get("ROS_DOMAIN_ID")
                os.environ["ROS_DOMAIN_ID"] = domain
                try:
                    rclpy.init()
                    node = rclpy.create_node("petasos_mimic_verifier")
                    readings = []
                    node.create_subscription(JointState, "/joint_states", readings.append, 10)
                    publisher = node.create_publisher(Float64MultiArray, "/driver/commands", 10)
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        message = Float64MultiArray(data=[0.006])
                        publisher.publish(message)
                        rclpy.spin_once(node, timeout_sec=0.15)
                        if readings:
                            latest = readings[-1]
                            values = dict(zip(latest.name, latest.position))
                            if abs(values.get("joint_7", -1) - 0.006) < 0.0001:
                                observed = values.get("joint_8")
                                expected = -0.006
                                if observed is not None and abs(observed - expected) < 0.0001:
                                    print(f"PASS: joint_7={values['joint_7']}, joint_8={observed}, expected={expected}")
                                    return 0
                                print(f"FAIL: joint_8={observed}, expected={expected}", file=sys.stderr)
                                return 1
                    print("FAIL: no commanded joint state received", file=sys.stderr)
                    return 1
                finally:
                    node.destroy_node()
                    rclpy.shutdown()
                    if previous_domain is None:
                        os.environ.pop("ROS_DOMAIN_ID", None)
                    else:
                        os.environ["ROS_DOMAIN_ID"] = previous_domain
        finally:
            for process in reversed(processes):
                process.terminate()
            for process in reversed(processes):
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
