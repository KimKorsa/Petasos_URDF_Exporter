import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from URDF_Exporter.core import Write
from URDF_Exporter.standalone.exporter import _controller_groups, validate_mimic_control
from moveit.generate_smoke_config import generate_smoke_config


def joints():
    return {
        "joint_7": {
            "type": "prismatic", "parent": "palm", "child": "left_finger",
            "axis": [1, 0, 0], "lower_limit": 0.0, "upper_limit": 0.01,
            "velocity_limit": 1.0, "effort_limit": 10.0,
            "command_interface": "position", "state_interfaces": ["position", "velocity"],
        },
        "joint_8": {
            "type": "prismatic", "parent": "palm", "child": "right_finger",
            "axis": [-1, 0, 0], "lower_limit": -0.008, "upper_limit": 0.002,
            "velocity_limit": 1.0, "effort_limit": 10.0,
            "command_interface": "position", "state_interfaces": ["position", "velocity"],
            "mimic_joint": "joint_7", "mimic_multiplier": -1.0,
            "mimic_offset": 0.002,
        },
    }


class MimicControlExportTests(unittest.TestCase):
    def test_default_group_excludes_follower_and_validates_endpoint_map(self):
        data = joints()
        groups = _controller_groups(data)
        self.assertEqual(groups[0]["joints"], ["joint_7"])
        codes = {item["code"] for item in validate_mimic_control(data, groups)}
        self.assertNotIn("mimic_limit_conflict", codes)
        self.assertIn("mimic_offset_unsupported", codes)
        data["joint_8"]["mimic_offset"] = 0.0
        data["joint_8"]["lower_limit"] = -0.01
        data["joint_8"]["upper_limit"] = 0.0
        self.assertEqual(validate_mimic_control(data, groups), [])

    def test_explicit_follower_control_is_rejected(self):
        data = joints()
        tree = {"_controllers": [{"name": "gripper", "joints": ["joint_7", "joint_8"]}]}
        with self.assertRaisesRegex(ValueError, "joint_8.*mimic"):
            _controller_groups(data, tree)

    def test_missing_driver_cycle_and_incompatible_limits_are_reported(self):
        data = joints()
        data["joint_8"]["upper_limit"] = 0.001
        errors = validate_mimic_control(data, [])
        self.assertIn("mimic_limit_conflict", {item["code"] for item in errors})
        data["joint_8"]["mimic_joint"] = "missing"
        self.assertIn("mimic_missing_driver", {item["code"] for item in validate_mimic_control(data, [])})
        data["joint_8"]["mimic_joint"] = "joint_7"
        data["joint_7"]["mimic_joint"] = "joint_8"
        self.assertIn("mimic_cycle", {item["code"] for item in validate_mimic_control(data, [])})

    def test_nonzero_offset_cannot_be_silently_sent_to_humble_hardware(self):
        data = joints()
        self.assertIn("mimic_offset_unsupported", {
            item["code"] for item in validate_mimic_control(data, _controller_groups(data))
        })

    def test_transmission_and_moveit_config_keep_only_driver_commanded(self):
        data = joints()
        data["joint_8"]["mimic_offset"] = 0.0
        data["joint_8"]["lower_limit"] = -0.01
        data["joint_8"]["upper_limit"] = 0.0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "urdf").mkdir()
            Write.write_transmissions_xacro(data, "robot", str(root))
            trans = ET.parse(root / "urdf" / "robot.trans").getroot()
            control = trans.find("ros2_control")
            follower = next(item for item in control.findall("joint") if item.get("name") == "joint_8")
            params = {item.get("name"): item.text for item in follower.findall("param")}
            self.assertEqual(params["mimic"], "joint_7")
            self.assertEqual(params["multiplier"], "-1.0")
            # Humble's GazeboSystem declares a follower command interface in its
            # documented mimic example, but no controller may claim that joint.
            self.assertEqual(follower.find("command_interface").get("name"), "position")
            self.assertTrue(follower.findall("state_interface"))

            description = root / "robot_description"
            description.mkdir()
            urdf = root / "robot.urdf"
            urdf.write_text('''<robot name="robot">
              <link name="palm"/><link name="left_finger"/><link name="right_finger"/>
              <joint name="joint_7" type="prismatic"><parent link="palm"/><child link="left_finger"/>
                <limit lower="0" upper="0.01" velocity="1" effort="10"/></joint>
              <joint name="joint_8" type="prismatic"><parent link="palm"/><child link="right_finger"/>
                <limit lower="-0.01" upper="0" velocity="1" effort="10"/>
                <mimic joint="joint_7" multiplier="-1" offset="0"/></joint>
              </robot>''', encoding="utf-8")
            output = root / "robot_moveit_config"
            generate_smoke_config(description, urdf, output, data, _controller_groups(data))
            srdf = ET.parse(output / "config" / "robot.srdf").getroot()
            self.assertEqual([item.get("name") for item in srdf.find("group").findall("joint")], ["joint_7"])
            for path in ("moveit_controllers.yaml", "ros2_controllers.yaml"):
                content = (output / "config" / path).read_text(encoding="utf-8")
                self.assertIn("joint_7", content)
                self.assertNotIn("joint_8", content)


if __name__ == "__main__":
    unittest.main()
