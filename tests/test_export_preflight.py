import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            with patch('URDF_Exporter.standalone.export_preflight.TrimeshFCLBackend', side_effect=ImportError), \
                 patch('URDF_Exporter.standalone.collision_diagnostics.TrimeshFCLBackend', side_effect=ImportError):
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

    def test_primitive_visual_blocks_com_outside_its_transformed_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory), com=(0.5, 0, 0))
            urdf = description / 'urdf' / 'robot.urdf'
            xml = urdf.read_text(encoding='utf-8').replace(
                '<visual><geometry><mesh filename="package://robot_description/meshes/a.stl"/></geometry></visual>',
                '<visual><origin xyz="0.1 0 0"/><geometry><box size="0.02 0.02 0.02"/></geometry></visual>')
            urdf.write_text(xml, encoding='utf-8')
            report = inspect_candidate(description, backend=AlwaysContact())
            issues = [item for item in report['diagnostics'] if item['code'] == 'com_outside_visual']
            self.assertEqual([item['targets'] for item in issues], [['a']])
            self.assertEqual(report['status'], 'error')

    def test_nested_visual_mesh_is_checked_instead_of_a_same_named_mesh(self):
        with tempfile.TemporaryDirectory() as directory:
            description = fixture(Path(directory), com=(0.5, 0, 0))
            nested = description / 'meshes' / 'nested'
            nested.mkdir()
            (description / 'meshes' / 'a.stl').rename(nested / 'a.stl')
            trimesh.creation.box(extents=[2, 2, 2]).export(description / 'meshes' / 'a.stl')
            urdf = description / 'urdf' / 'robot.urdf'
            urdf.write_text(urdf.read_text(encoding='utf-8').replace(
                'meshes/a.stl', 'meshes/nested/a.stl'), encoding='utf-8')
            report = inspect_candidate(description, backend=AlwaysContact())
            self.assertTrue(any(item['code'] == 'com_outside_visual' and item['targets'] == ['a']
                                for item in report['diagnostics']))

    def test_invalid_com_is_blocking_even_without_visual_geometry(self):
        for value in ('nan 0 0', '0', 'bad 0 0'):
            with self.subTest(com=value), tempfile.TemporaryDirectory() as directory:
                description = fixture(Path(directory))
                urdf = description / 'urdf' / 'robot.urdf'
                from xml.etree import ElementTree as ET
                robot = ET.parse(urdf)
                link = robot.getroot().find("link[@name='a']")
                link.remove(link.find('visual'))
                link.find('inertial/origin').set('xyz', value)
                robot.write(urdf, encoding='utf-8')
                report = inspect_candidate(description, backend=AlwaysContact())
                self.assertTrue(any(item['code'] == 'invalid_com' and item['targets'] == ['a']
                                    and item['severity'] == 'error' for item in report['diagnostics']))
                self.assertEqual(report['status'], 'error')

    def test_invalid_visual_geometry_produces_named_blocking_diagnostic(self):
        from xml.etree import ElementTree as ET
        for shape in ('<sphere/>', '<cylinder radius="1"/>', '<mesh filename="missing.stl"/>'):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as directory:
                description = fixture(Path(directory))
                urdf = description / 'urdf' / 'robot.urdf'
                robot = ET.parse(urdf)
                visual = robot.getroot().find("link[@name='a']/visual")
                visual.remove(visual.find('geometry'))
                visual.append(ET.fromstring(f'<geometry>{shape}</geometry>'))
                robot.write(urdf, encoding='utf-8')
                report = inspect_candidate(description, backend=AlwaysContact())
                self.assertTrue(any(item['code'] == 'visual_geometry_invalid' and item['targets'] == ['a']
                                    and item['severity'] == 'error' for item in report['diagnostics']))
                self.assertEqual(report['status'], 'error')


if __name__ == "__main__":
    unittest.main()
