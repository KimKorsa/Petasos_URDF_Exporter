import unittest
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET


def group_fixture():
    joints = {
        'j1': dict(type='revolute', parent='base', child='palm'),
        'j2': dict(type='prismatic', parent='palm', child='left'),
        'j3': dict(type='prismatic', parent='palm', child='right', mimic_joint='j2'),
        'j4': dict(type='fixed', parent='palm', child='camera')}
    names = {'joints': {'1': 'j1', '2': 'j2', '3': 'j3', '4': 'j4'}, 'links': {}}
    tree = {'_modules': [{'name': 'tool', 'joint_ids': ['1', '2', '3', '4'], 'attachment_joint_id': '1'}]}
    controllers = [{'name': 'grip', 'type': 'position_controllers/GripperActionController', 'joints': ['j2']}]
    return tree, names, joints, controllers


class MoveItGroupsTests(unittest.TestCase):
    def test_manual_module_and_attachment_split_arm_gripper(self):
        from URDF_Exporter.standalone.moveit_groups import resolve_planning_groups
        groups = resolve_planning_groups(*group_fixture())
        self.assertEqual(groups[0]['name'], 'arm')
        self.assertEqual(groups[0]['joints'], ['j1'])
        self.assertEqual(groups[1]['joints'], ['j2', 'j3'])
        self.assertEqual(groups[1]['driven_joints'], ['j2'])
        self.assertEqual(groups[1]['role'], 'gripper')
        self.assertFalse(groups[1]['chain_supported'])

    def test_no_modules_keeps_arm_but_branches_disable_kdl(self):
        from URDF_Exporter.standalone.moveit_groups import resolve_planning_groups
        _, names, joints, controllers = group_fixture()
        groups = resolve_planning_groups({}, names, joints, controllers)
        self.assertEqual(groups[0]['name'], 'arm')
        self.assertFalse(groups[0]['chain_supported'])

    def test_reserved_group_name_collision_is_error(self):
        from URDF_Exporter.standalone.moveit_groups import resolve_planning_groups
        tree, names, joints, controllers = group_fixture()
        tree['_modules'][0]['name'] = 'arm'
        with self.assertRaisesRegex(ValueError, '이름'):
            resolve_planning_groups(tree, names, joints, controllers)

    def test_generated_srdf_splits_groups_and_no_gripper_kdl(self):
        from URDF_Exporter.standalone.moveit_groups import resolve_planning_groups
        from moveit.generate_smoke_config import generate_smoke_config
        groups = resolve_planning_groups(*group_fixture())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            description = root / 'r_description'
            description.mkdir()
            urdf = root / 'r.urdf'
            urdf.write_text('''<robot name="r"><link name="base"/><link name="palm"/><link name="left"/><link name="right"/>
            <joint name="j1" type="revolute"><parent link="base"/><child link="palm"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint>
            <joint name="j2" type="prismatic"><parent link="palm"/><child link="left"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint>
            <joint name="j3" type="prismatic"><parent link="palm"/><child link="right"/><limit lower="-1" upper="1" effort="10" velocity="1"/><mimic joint="j2" multiplier="-1"/></joint></robot>''')
            output = root / 'r_moveit_config'
            generate_smoke_config(description, urdf, output, planning_groups=groups)
            srdf = ET.parse(output / 'config/r.srdf').getroot()
            self.assertEqual([g.get('name') for g in srdf.findall('group')], ['arm', 'tool'])
            self.assertEqual([j.get('name') for j in srdf.find("group[@name='arm']")], ['j1'])
            text = (output / 'config/kinematics.yaml').read_text()
            self.assertIn('arm:', text)
            self.assertNotIn('tool:', text)

    def test_assistant_settings_are_preserved_with_candidate_diff(self):
        from URDF_Exporter.standalone.moveit_groups import preserve_assistant_config
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, generated = root / 'old/r_moveit_config', root / 'new/src/r_moveit_config'
            for folder in (old, generated):
                (folder / 'config').mkdir(parents=True)
            (old / 'config/r.srdf').write_text('<robot name="r"><group name="old"/></robot>')
            (generated / 'config/r.srdf').write_text('<robot name="r"><group name="current"/></robot>')
            report = preserve_assistant_config(old, generated, root / 'new')
            self.assertIsNotNone(ET.parse(old / 'config/r.srdf').find("group[@name='old']"))
            self.assertIsNotNone(ET.parse(generated / 'config/r.srdf').find("group[@name='current']"))
            self.assertIsNotNone(ET.parse(root / 'new/.petasos-generated/r_moveit_config/config/r.srdf').find("group[@name='current']"))
            self.assertIsNotNone(ET.parse(root / 'new/.petasos-previous/r_moveit_config/config/r.srdf').find("group[@name='old']"))
            self.assertIn('config/r.srdf', report['changed_files'])
