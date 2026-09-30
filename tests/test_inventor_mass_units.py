import unittest
from types import SimpleNamespace

from URDF_Exporter.standalone.adapters.inventor import _mass_properties
from URDF_Exporter.standalone.importers import _manifest_physical


class InventorMassUnitTests(unittest.TestCase):
    def test_inventor_com_uses_manifest_millimeters_then_imports_once(self):
        center_cm = SimpleNamespace(
            X=-11.9244988,
            Y=7.7089474,
            Z=92.1020752,
        )
        properties = SimpleNamespace(
            Mass=0.004428522730492912,
            Volume=4.428522730492912,
            CenterOfMass=center_cm,
            XYZMomentsOfInertia=lambda: (0.01, 0.02, 0.03, 0, 0, 0),
        )
        document = SimpleNamespace(
            ComponentDefinition=SimpleNamespace(MassProperties=properties)
        )

        physical = _mass_properties(document)

        self.assertIsNotNone(physical)
        for actual, expected in zip(
            physical["center_of_mass"],
            (-119.244988, 77.089474, 921.020752),
        ):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertEqual(physical["center_of_mass_units"], "mm")

        imported = _manifest_physical({"physical": physical}, length_to_mm=1.0)
        for actual, expected in zip(
            imported["center_of_mass"],
            (-0.119244988, 0.077089474, 0.921020752),
        ):
            self.assertAlmostEqual(actual, expected, places=9)
        self.assertAlmostEqual(imported["inertia"][0], 0.01 * 1e-4)


if __name__ == "__main__":
    unittest.main()
