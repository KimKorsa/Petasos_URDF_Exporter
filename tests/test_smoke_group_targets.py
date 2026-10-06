import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


class SmokeGroupTargetsTests(unittest.TestCase):
    def test_targets_exclude_other_group_and_mimic_follower(self):
        from moveit.smoke_plan import _automatic_targets, _group_joint_names
        xml = '''<robot><joint name="arm" type="revolute"><parent link="base"/><child link="palm"/><limit lower="-1" upper="1"/></joint>
        <joint name="grip" type="prismatic"><parent link="palm"/><child link="left"/><limit lower="0" upper="0.05"/></joint>
        <joint name="follow" type="prismatic"><parent link="palm"/><child link="right"/><limit lower="0" upper="0.05"/><mimic joint="grip"/></joint></robot>'''
        srdf = ET.fromstring('<robot><group name="arm"><joint name="arm"/></group><group name="gripper"><joint name="grip"/><joint name="follow"/></group></robot>')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'robot.urdf'
            path.write_text(xml)
            allowed = _group_joint_names(srdf, ET.fromstring(xml), 'gripper')
            self.assertEqual(allowed, {'grip'})
            targets = _automatic_targets(path, {'arm': 0, 'grip': 0, 'follow': 0}, allowed)
            self.assertEqual(set(targets), {'grip'})
            self.assertGreater(targets['grip'], 0)

    def test_chain_and_subgroup_resolve_independent_joints(self):
        from moveit.smoke_plan import _group_joint_names
        urdf = ET.fromstring('<robot><joint name="j" type="revolute"><parent link="a"/><child link="b"/></joint></robot>')
        srdf = ET.fromstring('<robot><group name="chain"><chain base_link="a" tip_link="b"/></group><group name="all"><group name="chain"/></group></robot>')
        self.assertEqual(_group_joint_names(srdf, urdf, 'all'), {'j'})
