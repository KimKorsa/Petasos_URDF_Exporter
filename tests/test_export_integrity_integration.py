import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import trimesh
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.robot_modules import walk_tree


class ExportIntegrityIntegrationTests(unittest.TestCase):
    def test_root_mount_corruption_is_rejected(self):
        from URDF_Exporter.standalone.exporter import export_project, Write
        from unittest.mock import patch
        state, tree = fixture()
        state['project_name'] = 'robot'
        state['joints'] = {}
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'], child=node['name'],
                    type=joint['joint_type'], axis=[0, 0, 1], lower_limit=-1, upper_limit=1)
                state['joints'][joint['joint_name']] = joint['joint_info']
        original = Write.write_urdf
        def corrupt(*args, **kwargs):
            original(*args, **kwargs)
            path = Path(args[6]) / 'urdf/robot.xacro'
            document = ET.parse(path)
            document.getroot().find("joint[@name='world_joint']/origin").set('xyz', '1 2 3')
            document.write(path, encoding='utf-8')
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / 'meshes').mkdir()
            for name in state['inertial']:
                trimesh.creation.box(extents=[2, 2, 2]).export(project / 'meshes' / (name + '.stl'))
            with patch.object(Write, 'write_urdf', side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, 'world_joint'):
                    export_project(state, tree, True, str(project))

    def test_real_export_emits_independent_reports_and_runtime_tool(self):
        from URDF_Exporter.standalone.exporter import export_project
        state, tree = fixture()
        state['project_name'] = 'robot'
        state['joints'] = {}
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'], child=node['name'],
                    type=joint['joint_type'], axis=[0, 0, 1], lower_limit=-1, upper_limit=1)
                state['joints'][joint['joint_name']] = joint['joint_info']
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / 'meshes').mkdir()
            for name in state['inertial']:
                trimesh.creation.box(extents=[2, 2, 2]).export(project / 'meshes' / (name + '.stl'))
            result = export_project(state, tree, True, str(project), include_moveit=True)
            description = Path(result['save_dir'])
            consistency = json.loads((description / 'analysis/export_consistency.json').read_text())
            self.assertEqual(consistency['status'], 'ok', consistency)
            self.assertEqual(consistency['runtime']['status'], 'unverified')
            collision = json.loads((description / 'analysis/collision_diagnostics.json').read_text())
            self.assertIn('meshes', collision)
            self.assertTrue((Path(result['bundle_dir']) / 'tools/check_export_runtime.py').is_file())
            self.assertTrue((Path(result['bundle_dir']) / 'check_export_runtime.sh').is_file())

    def test_prepare_export_preserves_previous_moveit_settings(self):
        from URDF_Exporter.standalone.server import ProjectStore
        from unittest import mock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = ProjectStore(root / 'projects', root / 'export')
            store.project_dir = root / 'projects/r'
            store.project_dir.mkdir(parents=True)
            store.state = {'project_name': 'r', 'tree': {'name': 'base_link'}}
            old = root / 'export/ros_ws/src/r_moveit_config/config'
            old.mkdir(parents=True)
            (old / 'r.srdf').write_text('<robot name="r"><group name="old"/></robot>')
            def export(_state, _tree, _fixed, _dir, **kw):
                bundle = Path(kw['output_root']) / 'ros_ws'
                description = bundle / 'src/r_description'
                (description / 'analysis').mkdir(parents=True)
                generated = bundle / 'src/r_moveit_config/config'
                generated.mkdir(parents=True)
                (generated / 'r.srdf').write_text('<robot name="r"><group name="current"/></robot>')
                (description / 'urdf').mkdir()
                (description / 'urdf/r.urdf').write_text('<robot name="r"><link name="base_link"/></robot>')
                return {'save_dir': str(description), 'bundle_dir': str(bundle), 'moveit_dir': str(generated.parent)}
            with mock.patch('URDF_Exporter.standalone.server.export_project', side_effect=export), \
                 mock.patch('URDF_Exporter.standalone.server.inspect_candidate', return_value={'status': 'ok', 'diagnostics': [], 'summary': {}}):
                prepared = store.prepare_export({'name': 'base_link'}, True, True)
                result = store.commit_export(prepared['token'], True)
            self.assertIsNotNone(ET.parse(old / 'r.srdf').find("group[@name='current']"))
            previous = root / 'export/ros_ws/.petasos-previous/r_moveit_config/config/r.srdf'
            self.assertIsNotNone(ET.parse(previous).find("group[@name='old']"))
            self.assertTrue((root / 'export/ros_ws/.petasos-generated/r_moveit_config/config/r.srdf').is_file())
