import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch

import numpy as np
import trimesh


class CollisionDiagnosticsTests(unittest.TestCase):
    def test_mimic_chain_moves_child_and_rejects_cycle(self):
        from URDF_Exporter.standalone.urdf_analysis import zero_positions, world_transforms
        robot = ET.fromstring('''<robot><link name="base"/><link name="a"/><link name="b"/>
          <joint name="a" type="prismatic"><parent link="base"/><child link="a"/>
          <axis xyz="1 0 0"/><limit lower="-1" upper="1"/></joint>
          <joint name="b" type="prismatic"><parent link="a"/><child link="b"/>
          <axis xyz="0 1 0"/><limit lower="-1" upper="1"/><mimic joint="a" offset="0.2"/></joint></robot>''')
        self.assertEqual(zero_positions(robot), {'a': 0.0, 'b': 0.2})
        np.testing.assert_allclose(world_transforms(robot, zero_positions(robot))['b'][:3, 3], [0, .2, 0])
        ET.SubElement(robot.find("joint"), 'mimic', joint='b')
        with self.assertRaisesRegex(ValueError, '순환'):
            zero_positions(robot)

    def test_zero_outside_limits_not_clamped(self):
        from URDF_Exporter.standalone.urdf_analysis import zero_positions
        robot = ET.fromstring('<robot><joint name="bad" type="prismatic"><limit lower="1" upper="2"/></joint></robot>')
        with self.assertRaisesRegex(ValueError, 'bad'):
            zero_positions(robot)

    def test_mesh_scale_origin_and_acm_are_reported(self):
        from URDF_Exporter.standalone.collision_diagnostics import diagnose_collision_meshes
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / 'robot_description'
            (package / 'meshes').mkdir(parents=True)
            trimesh.creation.box(extents=[2, 2, 2]).export(package / 'meshes' / 'box.stl')
            robot = ET.fromstring('''<robot><link name="a"><collision><origin xyz="1 0 0"/>
              <geometry><mesh filename="package://robot_description/meshes/box.stl" scale="0.01 0.01 0.01"/></geometry></collision></link>
              <link name="b"><collision><geometry><box size="0.02 0.02 0.02"/></geometry></collision></link>
              <joint name="j" type="fixed"><parent link="a"/><child link="b"/><origin xyz="1 0 0"/></joint></robot>''')
            with patch('URDF_Exporter.standalone.collision_diagnostics.TrimeshFCLBackend', side_effect=ImportError):
                report = diagnose_collision_meshes(robot, package)
            self.assertEqual(report['pairs'][0]['status'], 'suspected_overlap')
            self.assertEqual(report['pairs'][0]['exact_status'], 'unverified')
            np.testing.assert_allclose(report['meshes'][0]['world_bounds'], [[.99, -.01, -.01], [1.01, .01, .01]])
            self.assertTrue(report['meshes'][0]['watertight'])
            srdf = ET.fromstring('<robot><disable_collisions link1="a" link2="b" reason="Adjacent"/></robot>')
            report = diagnose_collision_meshes(robot, package, srdf)
            self.assertEqual(report['pairs'][0]['excluded_reason'], 'Adjacent')

    def test_missing_mesh_is_error_not_clear(self):
        from URDF_Exporter.standalone.collision_diagnostics import diagnose_collision_meshes
        robot = ET.fromstring('<robot><link name="a"><collision><geometry><mesh filename="missing.stl"/></geometry></collision></link></robot>')
        report = diagnose_collision_meshes(robot, Path('.'))
        self.assertEqual(report['status'], 'error')
        self.assertEqual(report['meshes'][0]['status'], 'error')

    def test_missing_primitive_dimension_is_error_not_an_exception(self):
        from URDF_Exporter.standalone.collision_diagnostics import diagnose_collision_meshes
        for shape in ('<sphere/>', '<cylinder radius="1"/>'):
            with self.subTest(shape=shape):
                robot = ET.fromstring(f'<robot><link name="a"><collision><geometry>{shape}</geometry></collision></link></robot>')
                report = diagnose_collision_meshes(robot, Path('.'))
                self.assertEqual(report['status'], 'error')
                self.assertEqual(report['meshes'][0]['status'], 'error')

    def test_disjoint_bounds_have_no_suspected_pairs(self):
        from URDF_Exporter.standalone.collision_diagnostics import diagnose_collision_meshes
        robot = ET.fromstring('''<robot><link name="a"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
        <link name="b"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
        <joint name="j" type="fixed"><parent link="a"/><child link="b"/><origin xyz="3 0 0"/></joint></robot>''')
        self.assertEqual(diagnose_collision_meshes(robot, Path('.'))['pairs'], [])

    def test_preflight_exposes_missing_collision_mesh(self):
        from URDF_Exporter.standalone.export_preflight import inspect_candidate
        with tempfile.TemporaryDirectory() as temp:
            description = Path(temp) / 'r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'urdf/r.urdf').write_text('<robot><link name="base"><collision><geometry><mesh filename="absent.stl"/></geometry></collision></link></robot>')
            report = inspect_candidate(description)
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['diagnostics'][0]['targets'], ['base'])

    def test_joined_part_surfaces_are_information_not_collision_warning(self):
        from URDF_Exporter.standalone.export_preflight import inspect_candidate
        with tempfile.TemporaryDirectory() as temp:
            description = Path(temp) / 'r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'meshes').mkdir()
            first, second = trimesh.creation.box(), trimesh.creation.box()
            second.apply_translation([1, 0, 0])  # Two closed parts meet on one face.
            trimesh.util.concatenate([first, second]).export(description / 'meshes/joined.stl')
            (description / 'urdf/r.urdf').write_text('''<robot><link name="base"><collision>
                <geometry><mesh filename="package://r_description/meshes/joined.stl"/></geometry>
                </collision></link></robot>''')
            (description / 'meshes/collision_mesh_generation.json').write_text(json.dumps({
                'base': {'status': 'fallback', 'reason': 'source_topology_invalid'}}))
            report = inspect_candidate(description)
            self.assertEqual(report['status'], 'ok', report)
            self.assertEqual(report['summary']['warnings'], 0)
            self.assertEqual(len(report['diagnostics']), 1)
            self.assertEqual(report['diagnostics'][0]['code'], 'collision_mesh_topology')
            self.assertEqual(report['diagnostics'][0]['severity'], 'info')
            detail = json.loads((description / 'analysis/collision_diagnostics.json').read_text(encoding='utf-8'))
            self.assertGreater(detail['meshes'][0]['nonmanifold_edges'], 0)

    def test_accepted_simplification_with_damaged_topology_still_warns(self):
        from URDF_Exporter.standalone.export_preflight import inspect_candidate
        with tempfile.TemporaryDirectory() as temp:
            description = Path(temp) / 'r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'meshes').mkdir()
            mesh = trimesh.creation.box()
            mesh.update_faces(np.arange(len(mesh.faces) - 1))
            mesh.export(description / 'meshes/bad.stl')
            (description / 'urdf/r.urdf').write_text('''<robot><link name="base"><collision>
                <geometry><mesh filename="package://r_description/meshes/bad.stl"/></geometry>
                </collision></link></robot>''')
            (description / 'meshes/collision_mesh_generation.json').write_text(json.dumps({
                'base': {'status': 'simplified', 'reason': 'verified'}}))
            report = inspect_candidate(description)
            self.assertEqual(report['status'], 'warning')
            self.assertEqual(report['diagnostics'][0]['code'], 'collision_simplification_damage')
            self.assertEqual(report['diagnostics'][0]['severity'], 'warning')

    def test_nonadjacent_contact_still_warns_and_has_exact_message(self):
        from URDF_Exporter.standalone.export_preflight import inspect_candidate
        class ContactBackend:
            def contacts(self, *args):
                return True
        with tempfile.TemporaryDirectory() as temp:
            description = Path(temp) / 'r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'urdf/r.urdf').write_text('''<robot><link name="base"/>
                <link name="a"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
                <link name="b"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
                <joint name="ja" type="fixed"><parent link="base"/><child link="a"/></joint>
                <joint name="jb" type="fixed"><parent link="base"/><child link="b"/></joint></robot>''')
            report = inspect_candidate(description, backend=ContactBackend())
            self.assertEqual(report['status'], 'warning')
            self.assertEqual(report['diagnostics'][0]['code'], 'collision_contact')
            detail = json.loads((description / 'analysis/collision_diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(detail['pairs'][0]['exact_status'], 'verified')
            self.assertNotIn('실제 충돌 확정은 아닙니다', detail['pairs'][0]['message'])
