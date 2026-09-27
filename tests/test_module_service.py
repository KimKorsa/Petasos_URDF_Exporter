import copy
import unittest
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.module_geometry import capture_module
from URDF_Exporter.standalone.robot_modules import walk_tree
from URDF_Exporter.standalone.module_service import prepare_module_operation
from URDF_Exporter.standalone import module_service


class ModuleServiceTests(unittest.TestCase):
    def setUp(self):
        self.state, self.tree = fixture()
        self.payload = capture_module(self.state, self.tree, self.tree['_modules'][0]['id'])

    def operation(self, state=None, tree=None, **kwargs):
        return prepare_module_operation(state or self.state, tree or self.tree, self.payload,
            parent_link_id=self.tree['_link_id'], prefix=kwargs.pop('prefix', 'tool_'),
            xyz_m=[0, 0, .1], rpy_rad=[0, 0, 1.57], **kwargs)

    def test_attach_twice_remaps_every_reference(self):
        first = self.operation()
        second = self.operation(first['state'], first['tree'], prefix='second_')
        entries = list(walk_tree(second['tree']))
        self.assertEqual(len({n['_link_id'] for n, _, _ in entries}), 7)
        self.assertEqual(len({n['name'] for n, _, _ in entries}), 7)
        self.assertEqual(len(second['state']['inertial']), 7)
        self.assertEqual(len(second['tree']['_modules']), 3)
        with self.assertRaises(ValueError):
            self.operation(first['state'], first['tree'])

    def test_replace_preserves_body_and_attachment(self):
        before = copy.deepcopy(self.tree['children'][0])
        result = self.operation(replace_id=self.tree['_modules'][0]['id'])
        mount = result['tree']['children'][0]
        for key in before.keys() - {'link_group'}:
            self.assertEqual(mount[key], before[key])
        self.assertEqual(result['tree']['components'], self.tree['components'])
        self.assertNotIn('palm_part', result['state']['inertial'])
        self.assertEqual(self.tree['children'][0], before)

    def test_failed_replace_leaves_input_unchanged(self):
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError):
            self.operation(replace_id='unknown')
        self.assertEqual(self.state, before)

    def test_new_instance_has_unique_view_ids_and_updated_preview_frame(self):
        self.payload['tree']['_patcher_id'] = 'same_view_id'
        info = self.payload['tree']['children'][0]['joint_info']
        info['_preview_world_xyz'] = [99, 99, 99]
        result = self.operation()
        inserted = result['tree']['children'][-1]['link_group']
        self.assertNotEqual(inserted.get('_patcher_id'), 'same_view_id')
        info = inserted['children'][0]['joint_info']
        self.assertNotEqual(info.get('_preview_world_xyz'), [99, 99, 99])

    def test_placement_moves_only_module_and_preserves_identity(self):
        state = module_service.reposition_module(self.state, self.tree, self.tree['_modules'][0]['id'], [0,0,.8], [0,0,0])
        self.assertEqual(state['tree']['_modules'], self.tree['_modules'])
        self.assertEqual(state['visual_transforms']['base_part'], self.state['visual_transforms']['base_part'])
        self.assertAlmostEqual(state['visual_transforms']['palm_part'][11], .8)
