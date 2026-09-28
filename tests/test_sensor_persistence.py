import copy
import tempfile
import unittest
from pathlib import Path
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.sensor_frames import create_sensor
from URDF_Exporter.standalone.server import ProjectStore, ImportFailure


class SensorPersistenceTests(unittest.TestCase):
    def test_save_and_reload_preserves_sensor_and_rejects_orphan(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / 'projects')
            store.project_dir = store.projects_root / 'robot'
            store.project_dir.mkdir()
            state, tree = fixture()
            store.state = state
            store._write_current_state()
            added = create_sensor(store.tree(), store.tree()['_link_id'], 'depth_camera', 'front')
            store.save_workspace(added)
            self.assertEqual(store.tree()['_sensors'][0]['name'], 'front')
            broken = copy.deepcopy(store.tree())
            broken['_sensors'][0]['parent_link_id'] = 'deleted'
            with self.assertRaises(ImportFailure):
                store.save_workspace(broken)
            self.assertEqual(store.tree()['_sensors'][0]['name'], 'front')
