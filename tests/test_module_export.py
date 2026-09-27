import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import xacro
from URDF_Exporter.standalone.module_export import write_module_xacros


class ModuleExportTests(unittest.TestCase):
    def test_real_export_twice_instanced_module_meshes_and_names(self):
        import copy
        import trimesh
        from tests.test_module_geometry import fixture
        from URDF_Exporter.standalone.module_geometry import capture_module
        from URDF_Exporter.standalone.module_service import prepare_module_operation
        from URDF_Exporter.standalone.robot_modules import walk_tree
        from URDF_Exporter.standalone.exporter import export_project
        state, tree = fixture()
        state['project_name'] = 'robot'
        for node, joint, parent in walk_tree(tree):
            if joint is not None:
                joint['joint_info'].update(parent=parent['name'],child=node['name'],type=joint['joint_type'],
                    axis=[0,0,1], lower_limit=0,upper_limit=.1,velocity_limit=1,effort_limit=1)
        state['joints'] = {j['joint_name']:copy.deepcopy(j['joint_info']) for _,j,_ in walk_tree(tree) if j is not None}
        payload = capture_module(state, tree, tree['_modules'][0]['id'])
        result = prepare_module_operation(state, tree, payload, parent_link_id=tree['_link_id'],prefix='second_',xyz_m=[0,0,.5],rpy_rad=[0,0,1.57])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'meshes').mkdir()
            for name in result['state']['inertial']:
                trimesh.creation.box(extents=[10,10,10]).export(root/'meshes'/f'{name}.stl')
            exported = export_project(result['state'],result['tree'],True,str(root))
            package = Path(exported['save_dir'])
            expanded = ET.fromstring(xacro.process_file(str(package/'urdf/robot.xacro')).toxml())
            self.assertEqual(len(expanded.findall('link')),6)
            self.assertEqual(len({j.get('name') for j in expanded.findall('joint')}),5)
            self.assertEqual(len(list((package/'urdf/modules').glob('*.xacro'))),2)
            for mesh in expanded.iter('mesh'):
                self.assertTrue((package/'meshes'/mesh.get('filename').split('/')[-1]).exists())

    def test_gripper_controller_keeps_action_type_and_position_only(self):
        from moveit.generate_smoke_config import generate_smoke_config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            description = root / 'robot_description'; description.mkdir()
            urdf = root / 'robot.urdf'
            urdf.write_text('<robot name="robot"><link name="base_link"/><link name="finger"/><joint name="grip" type="prismatic"><parent link="base_link"/><child link="finger"/><limit lower="0" upper="0.1" velocity="1" effort="2"/></joint></robot>')
            output = root / 'robot_moveit_config'
            groups = [{'name':'gripper', 'type':'position_controllers/GripperActionController','joints':['grip']}]
            with self.assertRaisesRegex(ValueError, 'velocity'):
                generate_smoke_config(description, urdf, output, {'grip':{'state_interfaces':['position']}}, groups)
            generate_smoke_config(description, urdf, output, {'grip':{'state_interfaces':['position','velocity']}}, groups)
            self.assertIn('type: GripperCommand', (output/'config/moveit_controllers.yaml').read_text())
            controllers = (output/'config/ros2_controllers.yaml').read_text()
            self.assertIn('type: position_controllers/GripperActionController', controllers)
            self.assertIn('joint: grip', controllers)
            self.assertNotIn('- velocity', controllers)
            groups[0]['type'] = 'pid_controller/PidController'
            with self.assertRaisesRegex(ValueError, 'unsupported|Unsupported'):
                generate_smoke_config(description, urdf, output, {}, groups)

    def test_module_expansion_matches_flat_robot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); urdf = root / 'urdf'; urdf.mkdir()
            path = urdf / 'robot.xacro'
            path.write_text('''<robot name="robot" xmlns:xacro="http://www.ros.org/wiki/xacro">
              <xacro:include filename="robot.trans"/>
              <link name="base"/><link name="palm"><visual><geometry><mesh filename="package://robot/meshes/palm.stl"/></geometry></visual></link><link name="finger"/>
              <joint name="mount" type="fixed"><parent link="base"/><child link="palm"/><origin xyz="0 0 0.1" rpy="0 0 1.57"/></joint>
              <joint name="grip" type="prismatic"><parent link="palm"/><child link="finger"/><origin xyz="0.01 0 0"/><mimic joint="grip"/></joint>
              </robot>''')
            (urdf / 'robot.trans').write_text('<robot><ros2_control name="robot" type="system"><joint name="grip"><command_interface name="position"/><state_interface name="position"/></joint></ros2_control></robot>')
            before = ET.fromstring(xacro.process_file(str(path)).toxml())
            write_module_xacros(root, [{'name':'gripper','links':['palm','finger'],'joints':['grip']}])
            after = ET.fromstring(xacro.process_file(str(path)).toxml())
            def canonical(element):
                return (element.tag, sorted(element.attrib.items()), (element.text or '').strip(), sorted(canonical(e) for e in element))
            self.assertEqual(canonical(before), canonical(after))
            self.assertTrue((urdf / 'modules/gripper.xacro').exists())
            self.assertEqual(len(after.findall('ros2_control')), 1)

    def test_export_without_modules_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(write_module_xacros(Path(directory), []), {'modules': []})
