import unittest

from URDF_Exporter.standalone.physical_materials import (
    apply_material_overrides,
    ensure_material_editor_data,
)


class PhysicalMaterialTests(unittest.TestCase):
    def test_editor_metadata_uses_existing_mass_and_density_for_volume(self):
        state = {
            "tree": {"name": "base_link", "components": ["part"], "children": []},
            "inertial": {
                "part": {
                    "mass": 2.0,
                    "density": 1000.0,
                    "inertia": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0],
                }
            },
        }

        tree = ensure_material_editor_data(state)

        self.assertIn("steel", tree["_physical_materials"])
        self.assertGreaterEqual(len(tree["_physical_materials"]), 60)
        self.assertEqual(tree["_physical_materials"]["titanium_grade_5"]["density"], 4430.0)
        self.assertEqual(
            tree["_physical_materials"]["pla"]["category"],
            "3D 프린팅 · 필라멘트",
        )
        self.assertIn("abs_like_resin", tree["_physical_materials"])
        self.assertIn("pa12_powder", tree["_physical_materials"])
        self.assertIn("metal_print_inconel_718", tree["_physical_materials"])
        self.assertAlmostEqual(tree["_component_physical"]["part"]["volume_m3"], 0.002)

    def test_density_override_rescales_mass_and_inertia(self):
        inertial = {
            "part": {
                "mass": 2.0,
                "density": 1000.0,
                "volume_m3": 0.002,
                "center_of_mass": [0.1, 0.0, 0.0],
                "inertia": [1.0, 2.0, 3.0, 0.1, 0.2, 0.3],
            }
        }
        visual_materials = {"part": {"material": "old"}}
        colors = {}
        tree = {
            "_physical_materials": {
                "custom": {
                    "name": "Custom",
                    "density": 2500.0,
                    "rgba": "0.1 0.2 0.3 1",
                }
            },
            "_component_material_assignments": {"part": "custom"},
            "_component_physical": {"part": {"mass": 2.0, "volume_m3": 0.002}},
        }

        warnings = apply_material_overrides(inertial, visual_materials, colors, tree)

        self.assertEqual(warnings, [])
        self.assertAlmostEqual(inertial["part"]["mass"], 5.0)
        self.assertEqual(inertial["part"]["center_of_mass"], [0.1, 0.0, 0.0])
        for actual, expected in zip(
            inertial["part"]["inertia"],
            [2.5, 5.0, 7.5, 0.25, 0.5, 0.75],
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(visual_materials["part"]["material"], "petasos_custom")
        self.assertEqual(colors["petasos_custom"], "0.100 0.200 0.300 1.000")

    def test_missing_volume_does_not_corrupt_original_physics(self):
        inertial = {
            "part": {
                "mass": 2.0,
                "center_of_mass": [0.0, 0.0, 0.0],
                "inertia": [1.0] * 6,
            }
        }
        tree = {
            "_physical_materials": {"custom": {"density": 2500.0}},
            "_component_material_assignments": {"part": "custom"},
        }

        warnings = apply_material_overrides(inertial, {}, {}, tree)

        self.assertEqual(inertial["part"]["mass"], 2.0)
        self.assertEqual(inertial["part"]["inertia"], [1.0] * 6)
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
