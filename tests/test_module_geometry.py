import copy
import unittest
import numpy as np
from tests.test_robot_modules import sample_tree
from URDF_Exporter.standalone.robot_modules import ensure_module_ids, create_module
from URDF_Exporter.standalone.module_geometry import capture_module, place_module


def fixture():
    tree = ensure_module_ids(sample_tree())
    palm = tree['children'][0]['link_group']
    tree['children'][0]['joint_info']['xyz'] = [0.1, 0.2, 0.3]
    palm['children'][0]['joint_info']['xyz'] = [0.02, 0, 0]
    tree = create_module(tree, [palm['_link_id'], palm['children'][0]['link_group']['_link_id']],
                         [palm['children'][0]['_joint_id']], 'gripper')
    transforms = {}
    for name, position in [('base_part', [0, 0, 0]), ('palm_part', [.1, .2, .3]), ('finger_part', [.12, .2, .3])]:
        matrix = np.eye(4)
        matrix[:3, 3] = position
        transforms[name] = matrix.flatten().tolist()
    state = {'tree': tree, 'visual_transforms': transforms, 'parts': [
        {'name': name, 'position_mm': [0, 0, 0], 'rotation_rpy': [0, 0, 0]} for name in transforms],
        'inertial': {name: {'mass': 1, 'center_of_mass': [.001, .002, .003], 'inertia': [1, 2, 3, .1, .2, .3]} for name in transforms},
        'materials': {name: {'material': 'steel'} for name in transforms}, 'colors': {'steel': '0.5 0.5 0.5 1'}}
    return state, tree


class ModuleGeometryTests(unittest.TestCase):
    def test_rotated_module_preserves_fk_and_inertia(self):
        state, tree = fixture()
        original = copy.deepcopy(state)
        payload = capture_module(state, tree, tree['_modules'][0]['id'])
        target = np.array([[0, -1, 0, .1], [1, 0, 0, .2], [0, 0, 1, .3], [0, 0, 0, 1]])
        placed = place_module(payload, target.flatten().tolist())
        np.testing.assert_allclose(np.linalg.inv(target) @ np.array(placed['visual_transforms']['finger_part']).reshape(4, 4),
                                   np.array(payload['visual_transforms']['finger_part']).reshape(4, 4), atol=1e-8)
        self.assertEqual(payload['inertial'], placed['inertial'])
        self.assertEqual(state, original)
        self.assertEqual(placed['tree']['children'][0]['joint_info']['xyz'], [.02, 0, 0])

    def test_capture_is_independent_of_cad_world_origin(self):
        state, tree = fixture()
        first = capture_module(state, tree, tree['_modules'][0]['id'])
        for matrix in state['visual_transforms'].values():
            matrix[3] += 5
            matrix[7] -= 3
        second = capture_module(state, tree, tree['_modules'][0]['id'])
        for name in first['visual_transforms']:
            np.testing.assert_allclose(first['visual_transforms'][name], second['visual_transforms'][name], atol=1e-8)

    def test_rejects_nonrigid_or_nonfinite_placement(self):
        state, tree = fixture()
        payload = capture_module(state, tree, tree['_modules'][0]['id'])
        for matrix in [np.zeros(16), np.full(16, np.nan)]:
            with self.assertRaises(ValueError):
                place_module(payload, matrix.tolist())
