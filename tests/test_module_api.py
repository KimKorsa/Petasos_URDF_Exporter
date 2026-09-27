import copy
import tempfile
import unittest
from pathlib import Path
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.server import ProjectStore, create_app


class ModuleApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProjectStore(Path(self.temp.name) / 'projects')
        self.store.project_dir = self.store.projects_root / 'robot'
        self.store.project_dir.mkdir()
        (self.store.project_dir / 'meshes').mkdir()
        self.state, self.tree = fixture()
        self.store.state = self.state
        self.store._write_current_state()
        for name in self.state['inertial']:
            (self.store.project_dir / 'meshes' / (name + '.stl')).write_text('solid t\nendsolid t')
        self.client = create_app(self.store).test_client()

    def test_library_attach_replace_restore_flow(self):
        response = self.client.post('/modules/library/save', json={'tree': self.tree, 'module_id': self.tree['_modules'][0]['id'], 'revision': self.store.revision})
        self.assertEqual(response.status_code, 200, response.data)
        library_id = response.json['id']
        request = {'library_id': library_id, 'tree': self.store.tree(), 'parent_link_id': self.tree['_link_id'],
                   'prefix': 'tool_', 'xyz_m': [0, 0, .1], 'rpy_rad': [0, 0, 0], 'revision': self.store.revision}
        applied = self.client.post('/modules/apply', json=request)
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(len(applied.json['tree']['_modules']), 2)
        before = copy.deepcopy(self.store.state)
        stale = self.client.post('/modules/apply', json=request)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.store.state, before)
        restored = self.client.post('/modules/restore', json={'snapshot_id': applied.json['undo_snapshot_id'], 'revision': applied.json['revision']})
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(len(restored.json['tree']['_modules']), 1)
        self.assertNotIn('tool_palm_part', self.store.state['inertial'])

    def test_invalid_module_workspace_is_not_saved(self):
        broken = copy.deepcopy(self.tree)
        broken['_module_revision'] = self.store.revision
        broken['children'][0]['link_group']['children'] = []
        before = copy.deepcopy(self.store.state)
        response = self.client.post('/workspace/save', json={'tree': broken})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(before, self.store.state)

    def test_stale_module_workspace_cannot_overwrite_new_state(self):
        tree = copy.deepcopy(self.store.tree())
        self.store._write_current_state()
        before = copy.deepcopy(self.store.state)
        response = self.client.post('/workspace/save', json={'tree': tree})
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(before, self.store.state)
