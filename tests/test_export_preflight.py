import json
import tempfile
import unittest
from pathlib import Path

import trimesh

from URDF_Exporter.standalone.export_preflight import inspect_candidate


def fixture(root, *, mass=1.0, com=(0, 0, 0), inertia=0.01, right_xyz="0 0 0"):
    description = root / "robot_description"
    (description / "urdf").mkdir(parents=True)
    (description / "meshes").mkdir()
    (description / "analysis").mkdir()
    trimesh.creation.box(extents=[0.02, 0.02, 0.02]).export(description / "meshes" / "a.stl")
    trimesh.creation.box(extents=[0.02, 0.02, 0.02]).export(description / "meshes" / "b.stl")
    (description / "urdf" / "robot.urdf").write_text(f'''<robot name="robot">
      <link name="base"/>
      <link name="a"><visual><geometry><mesh filename="package://robot_description/meshes/a.stl"/></geometry></visual>
        <collision><geometry><mesh filename="package://robot_description/meshes/a.stl"/></geometry></collision>
        <inertial><origin xyz="{' '.join(map(str, com))}"/><mass value="{mass}"/>
          <inertia ixx="{inertia}" ixy="0" ixz="0" iyy="{inertia}" iyz="0" izz="{inertia}"/></inertial></link>
      <link name="b"><visual><geometry><mesh filename="package://robot_description/meshes/b.stl"/></geometry></visual>
        <collision><geometry><mesh filename="package://robot_description/meshes/b.stl"/></geometry></collision>
        <inertial><mass value="1"/><inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/></inertial></link>
      <joint name="a_mount" type="fixed"><parent link="base"/><child link="a"/></joint>
      <joint name="b_mount" type="fixed"><parent link="base"/><child link="b"/>
        <origin xyz="{right_xyz}"/></joint>
      </robot>''', encoding="utf-8")
    return description


class AlwaysContact:
    def contacts(self, mesh_a, mesh_b, transform_a, transform_b):
        return True


class ExportPreflightTests(unittest.TestCase):
    def test_invalid_mass_com_and_inertia_are_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory), mass=-1, com=(0.5, 0, 0), inertia=-0.01)
            report = inspect_candidate(description, None)
            codes = {item["code"] for item in report["diagnostics"]}
            self.assertTrue({"invalid_mass", "com_outside_visual", "invalid_inertia"} <= codes)
            self.assertEqual(report["status"], "error")
            for item in report["diagnostics"]:
                self.assertTrue({"code", "severity", "targets", "observed", "expected", "action"} <= item.keys())

    def test_nonadjacent_overlap_is_named_and_missing_backend_is_not_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory))
            without_backend = inspect_candidate(description, None)
            unchecked = [item for item in without_backend["diagnostics"] if item["code"] == "collision_not_checked"]
            self.assertEqual(unchecked[0]["targets"], ["a", "b"])
            self.assertEqual(unchecked[0]["severity"], "not_checked")
            checked = inspect_candidate(description, None, AlwaysContact())
            contacts = [item for item in checked["diagnostics"] if item["code"] == "collision_contact"]
            self.assertEqual(contacts[0]["targets"], ["a", "b"])
            self.assertEqual(contacts[0]["severity"], "warning")

    def test_disjoint_pairs_and_fixed_adjacent_contacts_are_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory), right_xyz="0.5 0 0")
            report = inspect_candidate(description, None)
            self.assertFalse(any(item["code"].startswith("collision_") for item in report["diagnostics"]))
            self.assertEqual(report["status"], "ok")
            urdf = description / "urdf" / "robot.urdf"
            xml = urdf.read_text(encoding="utf-8")
            xml = xml.replace('<parent link="base"/><child link="b"/>',
                              '<parent link="a"/><child link="b"/>')
            xml = xml.replace('xyz="0.5 0 0"', 'xyz="0 0 0"')
            urdf.write_text(xml, encoding="utf-8")
            adjacent = inspect_candidate(description, None, AlwaysContact())
            self.assertFalse(any(item["code"].startswith("collision_") for item in adjacent["diagnostics"]))

    def test_stl_fallback_provenance_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory))
            (description / "analysis" / "assembly.json").write_text(json.dumps({
                "source_parts": [{"name": "finger", "physical": {"provenance": "stl_fallback"}}]
            }), encoding="utf-8")
            report = inspect_candidate(description, None)
            fallback = [item for item in report["diagnostics"] if item["code"] == "stl_physical_fallback"]
            self.assertEqual(fallback[0]["targets"], ["finger"])


if __name__ == "__main__":
    unittest.main()
