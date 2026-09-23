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

    def test_frontend_preview_component_transform_is_used_for_export(self):
        struct = self.make_structure()
        joint_world = struct._matrix_from_xyz_rpy(
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        )
        component_world = struct._matrix_from_xyz_rpy(
            [2.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        )
        tree = {
            "name": "link_1",
            "components": ["part_1"],
            "children": [{
                "joint_name": "joint_1",
                "joint_type": "revolute",
                "joint_info": {
                    "type": "revolute",
                    "axis": [0.0, 0.0, 1.0],
                    "lower_limit": -math.pi,
                    "upper_limit": math.pi,
                    "_preview_world_frame_matrix": self.three_matrix(joint_world),
                },
                "link_group": {
                    "name": "link_2",
                    "components": ["part_2"],
                    "children": [],
                },
            }],
            "_preview_units_per_meter": 1000.0,
            "_preview_transforms": {
                "part_1": self.three_matrix(self.identity),
                "part_2": self.three_matrix(component_world),
            },
        }

        struct.apply_tree_data(tree)

        visual = struct.additional_visuals["link_2"][0]
        self.assertEqual(visual[2], [1.0, 0.0, 0.0])


class CompositeRigidBodyTests(unittest.TestCase):
    def make_structure(self, inertial, transforms):
        materials = {
            name: {"material": "silver_default"}
            for name in inertial
        }
        return RobotStructure({}, inertial, materials, transforms)

    def apply_single_link(self, structure, component_names):
        structure.apply_tree_data({
            "name": "base_link",
            "components": component_names,
            "children": [],
        })
        return structure.inertial["base_link"]

    def test_parallel_axis_theorem_is_applied_to_separated_parts(self):
        identity_inertia = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0]
        inertial = {
            name: {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": identity_inertia,
            }
            for name in ("left", "right")
        }
        inertial["reference"] = {
            "mass": 0.0,
            "center_of_mass": [0.0, 0.0, 0.0],
            "inertia": [0.0] * 6,
        }
        helper = self.make_structure(inertial, {})
        transforms = {
            "reference": helper._identity_matrix(),
            "left": helper._matrix_from_xyz_rpy([-1.0, 0.0, 0.0], [0.0, 0.0, 0.0]),
            "right": helper._matrix_from_xyz_rpy([1.0, 0.0, 0.0], [0.0, 0.0, 0.0]),
        }
        structure = self.make_structure(inertial, transforms)

        physical = self.apply_single_link(structure, ["reference", "left", "right"])

        self.assertAlmostEqual(physical["mass"], 2.0)
        self.assertEqual(physical["center_of_mass"], [0.0, 0.0, 0.0])
        for actual, expected in zip(
            physical["inertia"],
            [2.0, 6.0, 8.0, 0.0, 0.0, 0.0],
        ):
            self.assertAlmostEqual(actual, expected)

    def test_component_inertia_is_rotated_into_link_frame(self):
        inertial = {
            "reference": {
                "mass": 0.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [0.0] * 6,
            },
            "rotated": {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0],
            },
        }
        helper = self.make_structure(inertial, {})
        transforms = {
            "reference": helper._identity_matrix(),
            "rotated": helper._matrix_from_xyz_rpy(
                [0.0, 0.0, 0.0],
                [0.0, 0.0, math.pi / 2.0],
            ),
        }
        structure = self.make_structure(inertial, transforms)

        physical = self.apply_single_link(structure, ["reference", "rotated"])

        for actual, expected in zip(
            physical["inertia"],
            [2.0, 1.0, 3.0, 0.0, 0.0, 0.0],
        ):
            self.assertAlmostEqual(actual, expected, places=10)

    def test_occurrence_pose_and_local_com_are_mass_weighted(self):
        inertial = {
            "light": {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [0.0] * 6,
            },
            "heavy": {
                "mass": 3.0,
                "center_of_mass": [0.5, 0.0, 0.0],
                "inertia": [0.0] * 6,
            },
        }
        helper = self.make_structure(inertial, {})
        transforms = {
            "light": helper._identity_matrix(),
            "heavy": helper._matrix_from_xyz_rpy(
                [1.5, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ),
        }
        structure = self.make_structure(inertial, transforms)

        physical = self.apply_single_link(structure, ["light", "heavy"])

        self.assertAlmostEqual(physical["mass"], 4.0)
        self.assertEqual(physical["center_of_mass"], [1.5, 0.0, 0.0])
        for actual, expected in zip(
            physical["inertia"],
            [0.0, 3.0, 3.0, 0.0, 0.0, 0.0],
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(physical["provenance"], "composite_rigid_body")
        self.assertEqual(physical["components"], ["light", "heavy"])


class DisabledLinkJointExportTests(unittest.TestCase):
    def make_structure(self):
        inertial = {
            name: {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            }
            for name in ("base", "link_1", "wheel_1")
        }
        materials = {
            name: {"material": "silver_default"}
            for name in inertial
        }
        identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        return RobotStructure(
            {},
            inertial,
            materials,
            {name: identity[:] for name in inertial},
        )

    def test_disabled_child_joint_and_link_are_skipped(self):
        struct = self.make_structure()
        tree_data = {
            "name": "base_link",
            "components": ["base"],
            "children": [
                {
                    "joint_name": "joint_1",
                    "joint_type": "revolute",
                    "joint_info": {"type": "revolute", "xyz": [0, 0, 1], "rpy": [0, 0, 0]},
                    "link_group": {
                        "name": "link_1",
                        "components": ["link_1"],
                        "children": [],
                    },
                },
                {
                    "joint_name": "joint_wheel",
                    "joint_type": "continuous",
                    "joint_info": {"type": "continuous", "xyz": [1, 0, 0], "rpy": [0, 0, 0]},
                    "disabled": True,
                    "link_group": {
                        "name": "wheel_link",
                        "components": ["wheel_1"],
                        "disabled": True,
                        "children": [],
                    },
                },
            ],
        }
        struct.apply_tree_data(tree_data)
        self.assertIn("joint_1", struct.joints)
        self.assertNotIn("joint_wheel", struct.joints)
        self.assertIn("base_link", struct.links)
        self.assertIn("link_1", struct.links)
        self.assertNotIn("wheel_link", struct.links)

    def test_cascading_disabled_subtree_is_skipped(self):
        struct = self.make_structure()
        identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        struct.inertial["wheel_2"] = {
            "mass": 0.5,
            "center_of_mass": [0.0, 0.0, 0.0],
            "inertia": [0.5, 0.5, 0.5, 0.0, 0.0, 0.0],
        }
        struct.materials["wheel_2"] = {"material": "silver_default"}
        struct.visual_transforms["wheel_2"] = identity[:]

        tree_data = {
            "name": "base_link",
            "components": ["base"],
            "children": [
                {
                    "joint_name": "joint_1",
                    "joint_type": "revolute",
                    "joint_info": {"type": "revolute", "xyz": [0, 0, 1], "rpy": [0, 0, 0]},
                    "link_group": {
                        "name": "link_1",
                        "components": ["link_1"],
                        "children": [],
                    },
                },
                {
                    "joint_name": "joint_wheel_1",
                    "joint_type": "continuous",
                    "joint_info": {"type": "continuous", "xyz": [1, 0, 0], "rpy": [0, 0, 0]},
                    "disabled": True,
                    "link_group": {
                        "name": "wheel_1_link",
                        "components": ["wheel_1"],
                        "disabled": True,
                        "children": [
                            {
                                "joint_name": "joint_wheel_2",
                                "joint_type": "fixed",
                                "joint_info": {"type": "fixed", "xyz": [0.1, 0, 0], "rpy": [0, 0, 0]},
                                "link_group": {
                                    "name": "wheel_2_link",
                                    "components": ["wheel_2"],
                                    "children": [],
                                },
                            }
                        ],
                    },
                },
            ],
        }
        struct.apply_tree_data(tree_data)
        self.assertIn("joint_1", struct.joints)
        self.assertIn("base_link", struct.links)
        self.assertIn("link_1", struct.links)
        self.assertNotIn("joint_wheel_1", struct.joints)
        self.assertNotIn("wheel_1_link", struct.links)
        self.assertNotIn("joint_wheel_2", struct.joints)
        self.assertNotIn("wheel_2_link", struct.links)


class JointZeroCalibrationUrdfTests(unittest.TestCase):
    def setUp(self):
        self.identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

    def three_matrix(self, row_major_metres, units_per_meter=1000.0):
        m = row_major_metres
        return [
            m[0], m[4], m[8], m[12],
            m[1], m[5], m[9], m[13],
            m[2], m[6], m[10], m[14],
            m[3] * units_per_meter,
            m[7] * units_per_meter,
            m[11] * units_per_meter,
            m[15],
        ]

    def test_joint_zero_calibration_urdf_origin_matches_visual_forward_kinematics(self):
        inertial = {
            name: {
                "mass": 1.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            }
            for name in ("part_base", "part_j3", "part_j4")
        }
        materials = {name: {"material": "silver_default"} for name in inertial}
        struct = RobotStructure({}, inertial, materials, {name: self.identity[:] for name in inertial})

        # Base at origin
        # Joint 3 at [0.1, 0.2, 0.3], rotated 164 deg (approx 2.8623 rad) around Z
        angle_j3 = 2.8623
        cos_j3, sin_j3 = math.cos(angle_j3), math.sin(angle_j3)
        j3_local = [
            cos_j3, -sin_j3, 0.0, 0.1,
            sin_j3,  cos_j3, 0.0, 0.2,
            0.0,     0.0,    1.0, 0.3,
            0.0,     0.0,    0.0, 1.0,
        ]

        # Neutral Joint 4 origin in world: [0.005974, 0.115596, 0.048952]
        j4_neutral_world = [
            1.0, 0.0, 0.0, 0.005974,
            0.0, 1.0, 0.0, 0.115596,
            0.0, 0.0, 1.0, 0.048952,
            0.0, 0.0, 0.0, 1.0,
        ]

        # Component 4 in world
        comp4_world = [
            1.0, 0.0, 0.0, 0.015969,
            0.0, 1.0, 0.0, 0.116572,
            0.0, 0.0, 1.0, -0.020721,
            0.0, 0.0, 0.0, 1.0,
        ]

        tree = {
            "name": "link_base",
            "components": ["part_base"],
            "children": [{
                "joint_name": "joint_3",
                "joint_type": "revolute",
                "joint_info": {
                    "type": "revolute",
                    "axis": [0.0, 0.0, 1.0],
                    "_preview_world_frame_matrix": self.three_matrix(j3_local),
                },
                "link_group": {
                    "name": "link_3",
                    "components": ["part_j3"],
                    "children": [{
                        "joint_name": "joint_4",
                        "joint_type": "revolute",
                        "joint_info": {
                            "type": "revolute",
                            "axis": [0.0, 0.0, 1.0],
                            "initial_position": 0,
                            "_preview_world_frame_matrix": self.three_matrix(j4_neutral_world),
                        },
                        "link_group": {
                            "name": "link_4",
                            "components": ["part_j4"],
                            "children": [],
                        },
                    }],
                },
            }],
            "_preview_units_per_meter": 1000.0,
            "_preview_transforms": {
                "part_base": self.three_matrix(self.identity),
                "part_j3": self.three_matrix(j3_local),
                "part_j4": self.three_matrix(comp4_world),
            },
        }

        struct.apply_tree_data(tree)

        # 1. Verify joint 4 origin is parent-relative
        exported_j4 = struct.joints["joint_4"]
        j4_local = struct._matrix_from_xyz_rpy(exported_j4["xyz"], exported_j4["rpy"])
        # Expected j4 local = j3_local^-1 * j4_neutral_world
        expected_j4_local = struct._relative_matrix(j3_local, j4_neutral_world)
        for act, exp in zip(j4_local, expected_j4_local):
            self.assertAlmostEqual(act, exp, places=5)

        # 2. Verify link_4 visual local matches: j4_neutral_world^-1 * comp4_world
        visual = struct.additional_visuals["link_4"][0]
        vis_local = struct._matrix_from_xyz_rpy(visual[2], visual[3])
        expected_vis_local = struct._relative_matrix(j4_neutral_world, comp4_world)
        for act, exp in zip(vis_local, expected_vis_local):
            self.assertAlmostEqual(act, exp, places=5)

        # 3. Verify Forward Kinematics in RViz produces the exact comp4_world
        fk_vis_world = struct._mat_mul(
            struct._mat_mul(j3_local, j4_local),
            vis_local,
        )
        for act, exp in zip(fk_vis_world, comp4_world):
            self.assertAlmostEqual(act, exp, places=5)


if __name__ == "__main__":
    unittest.main()
