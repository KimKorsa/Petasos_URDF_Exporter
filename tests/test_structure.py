import math
import unittest

from URDF_Exporter.core.Structure import RobotStructure


class PreviewJointFrameExportTests(unittest.TestCase):
    def setUp(self):
        self.identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

    def three_matrix(self, row_major_metres, units_per_meter=1000.0):
        matrix = row_major_metres
        return [
            matrix[0], matrix[4], matrix[8], matrix[12],
            matrix[1], matrix[5], matrix[9], matrix[13],
            matrix[2], matrix[6], matrix[10], matrix[14],
            matrix[3] * units_per_meter,
            matrix[7] * units_per_meter,
            matrix[11] * units_per_meter,
            matrix[15],
        ]

    def make_structure(self):
        inertial = {
            name: {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            }
            for name in ("part_1", "part_2", "part_3", "part_4")
        }
        materials = {
            name: {"material": "silver_default"}
            for name in inertial
        }
        return RobotStructure(
            {},
            inertial,
            materials,
            {name: self.identity[:] for name in inertial},
        )

    def assert_matrix_almost_equal(self, actual, expected):
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=5)

    def test_three_nested_preview_frames_are_exported_parent_relative(self):
        struct = self.make_structure()
        joint_1_local = struct._matrix_from_xyz_rpy(
            [0.1, 0.0, 0.0],
            [0.0, 0.0, math.pi / 2.0],
        )
        joint_2_local = struct._matrix_from_xyz_rpy(
            [0.0, 0.2, 0.0],
            [math.pi / 2.0, 0.0, 0.0],
        )
        joint_3_local = struct._matrix_from_xyz_rpy(
            [0.0, 0.0, 0.3],
            [0.0, -math.pi / 3.0, 0.0],
        )
        joint_world_frames = [
            joint_1_local,
            struct._mat_mul(joint_1_local, joint_2_local),
            struct._mat_mul(
                struct._mat_mul(joint_1_local, joint_2_local),
                joint_3_local,
            ),
        ]

        def joint_node(index, child):
            return {
                "joint_name": f"picked_{index}",
                "joint_type": "revolute",
                "joint_info": {
                    "parent": "unused",
                    "child": "unused",
                    "type": "revolute",
                    # Deliberately stale: the exact preview frame must win.
                    "xyz": [9.0, 9.0, 9.0],
                    "rpy": [0.9, 0.9, 0.9],
                    "_manual_rpy": [0.8, 0.8, 0.8],
                    "axis": [0.0, 0.0, 1.0],
                    "lower_limit": -math.pi,
                    "upper_limit": math.pi,
                    "_preview_world_frame_matrix": self.three_matrix(
                        joint_world_frames[index - 1]
                    ),
                },
                "link_group": child,
            }

        link_4 = {"name": "link_4", "components": ["part_4"], "children": []}
        link_3 = {
            "name": "link_3",
            "components": ["part_3"],
            "children": [joint_node(3, link_4)],
        }
        link_2 = {
            "name": "link_2",
            "components": ["part_2"],
            "children": [joint_node(2, link_3)],
        }
        tree = {
            "name": "link_1",
            "components": ["part_1"],
            "children": [joint_node(1, link_2)],
            "_preview_units_per_meter": 1000.0,
        }

        struct.apply_tree_data(tree)

        for index, expected_local in enumerate(
            (joint_1_local, joint_2_local, joint_3_local),
            start=1,
        ):
            exported = struct.joints[f"picked_{index}"]
            actual_local = struct._matrix_from_xyz_rpy(
                exported["xyz"],
                exported["rpy"],
            )
            self.assert_matrix_almost_equal(actual_local, expected_local)
            self.assertNotEqual(exported["rpy"], [0.8, 0.8, 0.8])


if __name__ == "__main__":
    unittest.main()
