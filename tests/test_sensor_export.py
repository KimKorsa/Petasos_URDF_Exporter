import copy
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
import xacro
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.sensor_frames import create_sensor, update_sensor, resolved_sensor_frames, write_sensor_frames


class SensorExportTests(unittest.TestCase):
    def test_moveit_seed_has_same_sensor_frame_topology(self):
        from URDF_Exporter.standalone.exporter import _write_moveit_seed_urdf
        sensor = {'name': 'camera', 'frame': 'camera_frame', 'joint_name': 'camera_frame_joint',
                  'parent': 'base_link', 'xyz_m': [.01, 0, .02], 'rpy_rad': [0, 0, 0]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seed.urdf'
            _write_moveit_seed_urdf(SimpleNamespace(inertial={'base_link': {}}, joints={}),
                                    'robot', str(path), True, 'world', sensor_frames=[sensor])
            robot = ET.parse(path).getroot()
            self.assertIsNotNone(robot.find("link[@name='camera_frame']"))
            self.assertEqual(robot.find("joint[@name='camera_frame_joint']/parent").get('link'), 'base_link')

    def test_real_export_contains_sensor_on_standardized_base_link(self):
        import trimesh
        from URDF_Exporter.standalone.exporter import export_project
        from URDF_Exporter.standalone.robot_modules import walk_tree
        state, tree = fixture()
        state['project_name'] = 'robot'
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'], child=node['name'],
                    type=joint['joint_type'], axis=[0, 0, 1], lower_limit=0,
                    upper_limit=.1, velocity_limit=1, effort_limit=1)
        state['joints'] = {joint['joint_name']: copy.deepcopy(joint['joint_info'])
                           for _, joint, _ in walk_tree(tree) if joint is not None}
        tree = create_sensor(tree, tree['_link_id'], 'depth_camera', 'front')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'meshes').mkdir()
            for name in state['inertial']:
                trimesh.creation.box(extents=[10, 10, 10]).export(root / 'meshes' / f'{name}.stl')
            exported = export_project(state, tree, True, str(root))
            robot = ET.fromstring(xacro.process_file(str(Path(exported['save_dir']) / 'urdf/robot.xacro')).toxml())
            self.assertEqual(robot.find("joint[@name='front_frame_joint']/parent").get('link'), 'base_link')

    def test_resolves_renamed_parent_and_expands_massless_fixed_frame(self):
        _, tree = fixture()
        tree = create_sensor(tree, tree['_link_id'], 'depth_camera', 'front')
        sensor = tree['_sensors'][0]
        tree = update_sensor(tree, sensor['id'], {'xyz_m': [0.01, 0.02, 0.03], 'rpy_rad': [0, 0, math.pi / 2]})
        resolved = resolved_sensor_frames(tree, {'links': {tree['_link_id']: 'base_link'}})
        self.assertEqual(resolved[0]['parent'], 'base_link')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'robot.xacro'
            path.write_text('<robot name="robot" xmlns:xacro="http://www.ros.org/wiki/xacro"><link name="base_link"/></robot>')
            write_sensor_frames(path, resolved)
            robot = ET.fromstring(xacro.process_file(str(path)).toxml())
            frame = robot.find("link[@name='front_frame']")
            joint = robot.find("joint[@name='front_frame_joint']")
            self.assertIsNotNone(frame)
            self.assertEqual(len(frame), 0)
            self.assertEqual(joint.get('type'), 'fixed')
            self.assertEqual(joint.find('parent').get('link'), 'base_link')
            self.assertEqual(joint.find('origin').get('xyz'), '0.01 0.02 0.03')
            self.assertAlmostEqual(float(joint.find('origin').get('rpy').split()[2]), math.pi / 2)
            self.assertIsNone(robot.find('ros2_control'))

    def test_invalid_parent_and_existing_names_fail_without_modifying_xacro(self):
        _, tree = fixture()
        tree = create_sensor(tree, tree['_link_id'], 'imu', 'imu')
        with self.assertRaises(ValueError):
            resolved_sensor_frames(tree, {'links': {}})
        resolved = resolved_sensor_frames(tree, {'links': {tree['_link_id']: 'base_link'}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'robot.xacro'
            original = '<robot name="robot"><link name="imu_frame"/></robot>'
            path.write_text(original)
            with self.assertRaises(ValueError):
                write_sensor_frames(path, resolved)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(write_sensor_frames(path, []), None)
            self.assertEqual(path.read_text(), original)
