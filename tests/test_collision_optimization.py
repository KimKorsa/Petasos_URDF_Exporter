import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
import trimesh

from URDF_Exporter.standalone.export_preflight import inspect_candidate, TrimeshFCLBackend
from URDF_Exporter.standalone.collision_diagnostics import diagnose_collision_meshes


class CollisionOptimizationTests(unittest.TestCase):
    def test_visual_and_collision_share_file_read_but_keep_scale_and_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / 'r_description'
            (package / 'urdf').mkdir(parents=True)
            (package / 'meshes').mkdir()
            trimesh.creation.box(extents=[2, 2, 2]).export(package / 'meshes' / 'box.stl')
            (package / 'urdf' / 'r.urdf').write_text('''<robot><link name="base">
              <visual><geometry><mesh filename="package://r_description/meshes/box.stl" scale="2 2 2"/></geometry></visual>
              <collision><origin xyz="1 0 0"/><geometry><mesh filename="package://r_description/meshes/box.stl"/></geometry></collision>
            </link></robot>''')
            with patch('trimesh.load_mesh', wraps=trimesh.load_mesh) as load:
                report = inspect_candidate(package)
            self.assertEqual(report['status'], 'ok')
            diagnostic = __import__('json').loads((package / 'analysis' / 'collision_diagnostics.json').read_text(encoding='utf-8'))
            np.testing.assert_allclose(diagnostic['meshes'][0]['world_bounds'], [[0, -1, -1], [2, 1, 1]])
            self.assertEqual(load.call_count, 1)

    def test_collision_models_are_reused_and_transforms_are_updated(self):
        try:
            backend = TrimeshFCLBackend()
        except ImportError:
            self.skipTest('python-fcl is unavailable')
        a, b = trimesh.creation.box(), trimesh.creation.box()
        near, far = np.eye(4), np.eye(4)
        far[0, 3] = 3
        with patch('trimesh.collision.mesh_to_convex', wraps=trimesh.collision.mesh_to_convex) as build:
            self.assertTrue(backend.contacts(a, b, near, near))
            self.assertFalse(backend.contacts(a, b, near, far))
            self.assertTrue(backend.contacts(a, b, near, near))
            self.assertEqual(build.call_count, 2)
        self.assertFalse(backend.contacts(a, a, near, far))
        b.apply_translation([5, 0, 0])
        self.assertFalse(backend.contacts(a, b, near, near))

    def test_invalid_primitive_dimensions_are_blocking(self):
        for shape in ('<box size="0 1 1"/>', '<box size="-1 1 1"/>',
                      '<sphere radius="-1"/>', '<sphere radius="0"/>',
                      '<cylinder radius="1" length="0"/>'):
            with self.subTest(shape=shape):
                robot = ET.fromstring(f'<robot><link name="base"><collision><geometry>{shape}</geometry></collision></link></robot>')
                report = diagnose_collision_meshes(robot, Path('.'))
                self.assertEqual(report['status'], 'error')
                self.assertEqual(report['meshes'][0]['status'], 'error')

    def test_second_transform_keeps_sub_float32_clearance(self):
        try:
            backend = TrimeshFCLBackend()
        except ImportError:
            self.skipTest('python-fcl is unavailable')
        box = trimesh.creation.box()
        for angle, clearance, expected in ((0.5, 1e-8, False), (0.2, -1e-8, True)):
            with self.subTest(angle=angle, clearance=clearance):
                first = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
                second = first.copy()
                second[:3, 3] = first[:3, 0] * (1 + clearance)
                self.assertEqual(backend.contacts(box, box, first, second), expected)
