import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import trimesh
import xacro

from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.sensor_frames import create_sensor, validate_sensors
from URDF_Exporter.standalone.module_geometry import capture_module
from URDF_Exporter.standalone.module_library import validate_payload
from URDF_Exporter.standalone.module_service import prepare_module_operation
from URDF_Exporter.standalone.robot_modules import walk_tree
from URDF_Exporter.standalone.exporter import export_project


class SensorModuleTests(unittest.TestCase):
    def setUp(self):
        self.state, self.tree = fixture()
        self.module = self.tree['_modules'][0]
        self.owner = self.module['root_link_id']
        self.tree = create_sensor(self.tree, self.owner, 'depth_camera', 'camera')

    def test_capture_and_two_instances_have_disjoint_ids_and_frames(self):
        payload = capture_module(self.state, self.tree, self.module['id'])
        self.assertEqual(len(payload['sensors']), 1)
        validate_payload(payload)
        first = prepare_module_operation(self.state, self.tree, payload,
            parent_link_id=self.tree['_link_id'], prefix='first_', xyz_m=[0, 0, .2], rpy_rad=[0, 0, 0])
        second = prepare_module_operation(first['state'], first['tree'], payload,
            parent_link_id=self.tree['_link_id'], prefix='second_', xyz_m=[0, 0, .3], rpy_rad=[0, 0, 0])
        sensors = second['tree']['_sensors']
        self.assertEqual(len(sensors), 3)
        self.assertEqual(len({s['id'] for s in sensors}), 3)
        self.assertEqual(len({s['name'] for s in sensors}), 3)
        self.assertEqual(validate_sensors(second['tree']), [])
        state, tree = second['state'], second['tree']
        state['project_name'] = 'robot'
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'], child=node['name'],
                    type=joint['joint_type'], axis=[0, 0, 1], lower_limit=0,
                    upper_limit=.1, velocity_limit=1, effort_limit=1)
        state['joints'] = {joint['joint_name']: copy.deepcopy(joint['joint_info'])
                           for _, joint, _ in walk_tree(tree) if joint is not None}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'meshes').mkdir()
            for name in state['inertial']:
                trimesh.creation.box(extents=[10, 10, 10]).export(root / 'meshes' / f'{name}.stl')
            exported = export_project(state, tree, True, str(root))
            robot = ET.fromstring(xacro.process_file(str(Path(exported['save_dir']) / 'urdf/robot.xacro')).toxml())
            for sensor in sensors:
                self.assertIsNotNone(robot.find(f"joint[@name='{sensor['name']}_frame_joint']"))

    def test_replace_removes_only_old_module_sensors(self):
        payload = capture_module(self.state, self.tree, self.module['id'])
        result = prepare_module_operation(self.state, self.tree, payload,
            parent_link_id=self.tree['_link_id'], prefix='first_', xyz_m=[0, 0, .2], rpy_rad=[0, 0, 0])
        replaced = prepare_module_operation(result['state'], result['tree'], payload,
            parent_link_id=self.tree['_link_id'], prefix='new_', xyz_m=[0, 0, .2],
            rpy_rad=[0, 0, 0], replace_id=result['module_id'])
        self.assertEqual({s['name'] for s in replaced['tree']['_sensors']}, {'camera', 'new_camera'})
        self.assertEqual(validate_sensors(replaced['tree']), [])

    def test_export_moves_owned_frames_into_module_xacro(self):
        state, tree = self.state, self.tree
        state['project_name'] = 'robot'
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'], child=node['name'],
                    type=joint['joint_type'], axis=[0, 0, 1], lower_limit=0,
                    upper_limit=.1, velocity_limit=1, effort_limit=1)
        state['joints'] = {joint['joint_name']: copy.deepcopy(joint['joint_info'])
                           for _, joint, _ in walk_tree(tree) if joint is not None}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'meshes').mkdir()
            for name in state['inertial']:
                trimesh.creation.box(extents=[10, 10, 10]).export(root / 'meshes' / f'{name}.stl')
            exported = export_project(state, tree, True, str(root))
            package = Path(exported['save_dir'])
            module_source = (package / 'urdf/modules/gripper.xacro').read_text()
            self.assertIn('camera_frame', module_source)
            robot = ET.fromstring(xacro.process_file(str(package / 'urdf/robot.xacro')).toxml())
            self.assertIsNotNone(robot.find("joint[@name='camera_frame_joint']"))


if __name__ == '__main__':
    unittest.main()
