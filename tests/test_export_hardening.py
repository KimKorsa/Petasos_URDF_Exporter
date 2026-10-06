import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
import yaml

from URDF_Exporter.standalone.exporter import _simplify_collision_mesh
from URDF_Exporter.standalone.moveit_groups import preserve_assistant_config


class CollisionSimplificationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original = trimesh.creation.icosphere(subdivisions=5)

    def test_open_decimation_result_falls_back_to_original(self):
        bad = trimesh.creation.icosphere(subdivisions=3)
        bad.update_faces(np.arange(len(bad.faces) - 1))
        with patch.object(trimesh.Trimesh, 'simplify_quadric_decimation', return_value=bad):
            result = _simplify_collision_mesh(self.original)
        self.assertEqual(len(result.faces), 20480)
        self.assertTrue(result.is_watertight)

    def test_closed_but_shrunken_decimation_falls_back_to_original(self):
        bad = trimesh.creation.icosphere(subdivisions=3, radius=0.3)
        with patch.object(trimesh.Trimesh, 'simplify_quadric_decimation', return_value=bad):
            result = _simplify_collision_mesh(self.original)
        np.testing.assert_allclose(result.bounds, [[-1, -1, -1], [1, 1, 1]])

    def test_valid_decimation_is_used(self):
        good = trimesh.creation.icosphere(subdivisions=3)
        with patch.object(trimesh.Trimesh, 'simplify_quadric_decimation', return_value=good):
            result = _simplify_collision_mesh(self.original)
        self.assertEqual(len(result.faces), 1280)
        self.assertTrue(result.is_watertight)

    def test_nonmanifold_result_is_rejected(self):
        bad = trimesh.creation.icosphere(subdivisions=3)
        bad.faces = np.vstack([bad.faces, bad.faces[0]])
        with patch.object(trimesh.Trimesh, 'simplify_quadric_decimation', return_value=bad):
            result = _simplify_collision_mesh(self.original)
        self.assertTrue(result.is_watertight)
        self.assertEqual(len(result.faces), 20480)

    def test_losing_a_small_separate_component_is_rejected(self):
        source = trimesh.util.concatenate([self.original, trimesh.creation.icosphere(subdivisions=1, radius=0.01)])
        with patch.object(trimesh.Trimesh, 'simplify_quadric_decimation', return_value=trimesh.creation.icosphere(subdivisions=3)):
            result = _simplify_collision_mesh(source)
        self.assertEqual(result.body_count, 2)

    def test_open_source_is_kept_without_further_damage(self):
        source = self.original.copy()
        source.update_faces(np.arange(len(source.faces) - 1))
        result = _simplify_collision_mesh(source)
        np.testing.assert_array_equal(result.faces, source.faces)
        self.assertEqual(result.metadata['collision_simplification']['reason'], 'source_topology_invalid')


class MoveItSynchronizationTests(unittest.TestCase):
    def test_current_groups_and_controllers_replace_stale_definitions_and_keep_user_tuning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'old/r_moveit_config', root / 'stage/src/r_moveit_config'
            for folder in (old, new):
                (folder / 'config').mkdir(parents=True)
            old_srdf = '<robot name="r"><group name="arm"><joint name="j1"/><joint name="j2"/></group><group_state name="home" group="arm"><joint name="j1" value="0.5"/></group_state><disable_collisions link1="base" link2="tool" reason="User"/></robot>'
            new_srdf = '<robot name="r"><group name="arm"><joint name="j1"/></group><group name="gripper"><joint name="j2"/></group><group_state name="home" group="arm"><joint name="j1" value="0"/></group_state></robot>'
            (old / 'config/r.srdf').write_text(old_srdf)
            (new / 'config/r.srdf').write_text(new_srdf)
            description = root / 'stage/src/r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'urdf/r.urdf').write_text('<robot name="r"><link name="base"/><link name="palm"/><link name="tool"/><joint name="j1" type="revolute"><parent link="base"/><child link="palm"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint><joint name="j2" type="prismatic"><parent link="palm"/><child link="tool"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint></robot>')
            old_ros = {'controller_manager': {'ros__parameters': {'old_grip': {'type': 'joint_trajectory_controller/JointTrajectoryController'}}}, 'old_grip': {'ros__parameters': {'joints': ['j2']}}}
            new_ros = {'controller_manager': {'ros__parameters': {'grip': {'type': 'effort_controllers/GripperActionController'}}}, 'grip': {'ros__parameters': {'joint': 'j2'}}}
            for folder, data in ((old, old_ros), (new, new_ros)):
                (folder / 'config/ros2_controllers.yaml').write_text(yaml.safe_dump(data))
            (old / 'config/moveit_controllers.yaml').write_text(yaml.safe_dump({'trajectory_execution': {'allowed_start_tolerance': 0.12}, 'moveit_simple_controller_manager': {'controller_names': ['old_grip']}}))
            (new / 'config/moveit_controllers.yaml').write_text(yaml.safe_dump({'trajectory_execution': {'allowed_start_tolerance': 0.05}, 'moveit_simple_controller_manager': {'controller_names': ['grip']}}))
            (old / 'config/custom.yaml').write_text('custom: keep\n')
            report = preserve_assistant_config(old, new, root / 'stage', description)
            srdf = ET.parse(new / 'config/r.srdf').getroot()
            self.assertEqual([j.get('name') for j in srdf.find("group[@name='arm']")], ['j1'])
            self.assertIsNotNone(srdf.find("group[@name='gripper']"))
            self.assertEqual(srdf.find("group_state[@name='home']/joint").get('value'), '0')
            self.assertEqual(srdf.find('disable_collisions').get('reason'), 'User')
            ros = yaml.safe_load((new / 'config/ros2_controllers.yaml').read_text())
            self.assertNotIn('old_grip', ros)
            self.assertEqual(ros['grip']['ros__parameters']['joint'], 'j2')
            moveit = yaml.safe_load((new / 'config/moveit_controllers.yaml').read_text())
            self.assertEqual(moveit['moveit_simple_controller_manager']['controller_names'], ['grip'])
            self.assertEqual(moveit['trajectory_execution']['allowed_start_tolerance'], 0.12)
            self.assertEqual((new / 'config/custom.yaml').read_text(), 'custom: keep\n')
            self.assertEqual((old / 'config/r.srdf').read_text(), old_srdf)
            self.assertEqual((root / 'stage' / report['previous_relative_path'] / 'config/r.srdf').read_text(), old_srdf)
            self.assertEqual(report['status'], 'synchronized')

    def test_invalid_assistant_file_does_not_replace_valid_generated_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'old/r_moveit_config', root / 'stage/src/r_moveit_config'
            for folder in (old, new):
                (folder / 'config').mkdir(parents=True)
            (old / 'config/r.srdf').write_text('broken xml')
            (new / 'config/r.srdf').write_text('<robot name="r"/>')
            report = preserve_assistant_config(old, new, root / 'stage')
            self.assertEqual(ET.parse(new / 'config/r.srdf').getroot().tag, 'robot')
            self.assertIn('config/r.srdf', report['review_files'])

    def test_stable_group_tuning_and_valid_stored_pose_survive_but_out_of_range_pose_does_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'old/r_moveit_config', root / 'stage/src/r_moveit_config'
            for folder in (old, new):
                (folder / 'config').mkdir(parents=True)
            group = '<group name="arm"><joint name="j1"/></group>'
            (old / 'config/r.srdf').write_text('<robot name="r">' + group + '<group_state name="parked" group="arm"><joint name="j1" value="0.5"/></group_state><group_state name="bad" group="arm"><joint name="j1" value="2"/></group_state></robot>')
            (new / 'config/r.srdf').write_text('<robot name="r">' + group + '</robot>')
            for folder, timeout in ((old, 0.8), (new, 0.1)):
                (folder / 'config/kinematics.yaml').write_text(yaml.safe_dump({'arm': {'kinematics_solver_timeout': timeout}}))
            description = root / 'stage/src/r_description'
            (description / 'urdf').mkdir(parents=True)
            (description / 'urdf/r.urdf').write_text('<robot name="r"><link name="base"/><link name="tip"/><joint name="j1" type="revolute"><parent link="base"/><child link="tip"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint></robot>')
            report = preserve_assistant_config(old, new, root / 'stage', description)
            srdf = ET.parse(new / 'config/r.srdf')
            self.assertIsNotNone(srdf.find("group_state[@name='parked']"))
            self.assertIsNone(srdf.find("group_state[@name='bad']"))
            self.assertEqual(yaml.safe_load((new / 'config/kinematics.yaml').read_text())['arm']['kinematics_solver_timeout'], 0.8)
            self.assertIn('config/r.srdf', report['review_files'])
