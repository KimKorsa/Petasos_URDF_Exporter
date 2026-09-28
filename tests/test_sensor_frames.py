import copy
import math
import unittest

from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.sensor_frames import (
    create_sensor, update_sensor, delete_sensor, validate_sensors, sensor_frame_name,
    sensor_world_matrix, set_sensor_world_point,
)


class SensorFramesTests(unittest.TestCase):
    def setUp(self):
        _, self.tree = fixture()
        self.root_id = self.tree['_link_id']

    def test_legacy_tree_and_multiple_sensors(self):
        self.assertEqual(validate_sensors(self.tree), [])
        first = create_sensor(self.tree, self.root_id, 'depth_camera', 'front_depth')
        second = create_sensor(first, self.root_id, 'imu', 'body_imu')
        self.assertEqual(len(second['_sensors']), 2)
        self.assertEqual(len({s['id'] for s in second['_sensors']}), 2)
        self.assertEqual(second['_sensors'][0]['xyz_m'], [0, 0, 0])
        self.assertEqual(validate_sensors(second), [])
        self.assertNotIn('_sensors', self.tree)
        self.assertEqual(sensor_frame_name('body_imu'), 'body_imu_frame')

    def test_mutations_copy_and_validate(self):
        created = create_sensor(self.tree, self.root_id, 'depth_camera', 'front')
        identity = created['_sensors'][0]['id']
        moved = update_sensor(created, identity, {'xyz_m': [0.01, 0.02, 0.03], 'rpy_rad': [0, 0, math.pi / 2]})
        self.assertEqual(created['_sensors'][0]['xyz_m'], [0, 0, 0])
        self.assertEqual(moved['_sensors'][0]['xyz_m'], [0.01, 0.02, 0.03])
        self.assertEqual(delete_sensor(moved, identity)['_sensors'], [])

    def test_collision_missing_disabled_nonfinite_rejected(self):
        created = create_sensor(self.tree, self.root_id, 'imu', 'imu')
        with self.assertRaises(ValueError):
            create_sensor(created, self.root_id, 'lidar', 'imu_frame')
        with self.assertRaises(ValueError):
            create_sensor(created, 'missing', 'imu', 'other')
        broken = copy.deepcopy(created)
        broken['_sensors'][0]['xyz_m'][0] = float('nan')
        self.assertTrue(validate_sensors(broken))
        disabled = copy.deepcopy(created)
        disabled['disabled'] = True
        self.assertTrue(validate_sensors(disabled))
        with self.assertRaises(ValueError):
            create_sensor(self.tree, self.root_id, 'camera_x', 'unknown')

    def test_world_pick_uses_rotated_link_local_coordinates(self):
        sensor = create_sensor(self.tree, self.root_id, 'depth_camera', 'front')['_sensors'][0]
        sensor['rpy_rad'] = [0, 0, 0.3]
        link = [0, -1, 0, 1, 1, 0, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1]
        moved = set_sensor_world_point(sensor, link, [1, 3, 3])
        self.assertEqual(moved['xyz_m'], [1, 0, 0])
        self.assertEqual(moved['rpy_rad'], sensor['rpy_rad'])
        self.assertEqual(sensor['xyz_m'], [0, 0, 0])
        world = sensor_world_matrix(moved, link)
        self.assertAlmostEqual(world[3], 1)
        self.assertAlmostEqual(world[7], 3)
