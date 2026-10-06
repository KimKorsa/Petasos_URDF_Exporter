import copy
import math
import unittest
from xml.etree import ElementTree as ET


def fixture():
    robot = ET.fromstring('''<robot><link name="base"/><link name="a"><inertial>
      <origin xyz="0.01 0 0"/><mass value="1"/><inertia ixx="0.1" iyy="0.2" izz="0.3" ixy="0" ixz="0" iyz="0"/>
      </inertial></link><joint name="j" type="revolute"><parent link="base"/><child link="a"/>
      <axis xyz="0 0 1"/><origin xyz="0 0 0" rpy="0 0 0"/><limit lower="-1" upper="1" effort="10" velocity="1"/></joint></robot>''')
    expected = {'joints': {'j': {'type': 'revolute', 'parent': 'base', 'child': 'a',
      'xyz': [0, 0, 0], 'rpy': [0, 0, 0], 'axis': [0, 0, 1],
      'lower_limit': -1, 'upper_limit': 1, 'effort_limit': 10, 'velocity_limit': 1}},
      'links': {'a': {'mass': 1, 'center_of_mass': [.01, 0, 0], 'inertia': [.1, .2, .3, 0, 0, 0]}}}
    return expected, robot


class ExportConsistencyTests(unittest.TestCase):
    def test_equivalent_euler_rotation_passes(self):
        from URDF_Exporter.standalone.export_consistency import compare_export
        expected, robot = fixture()
        robot.find('joint/origin').set('rpy', f'0 0 {2 * math.pi}')
        self.assertEqual(compare_export(expected, robot)['status'], 'ok')

    def test_axis_com_and_inertia_drift_are_named(self):
        from URDF_Exporter.standalone.export_consistency import compare_export
        expected, robot = fixture()
        robot.find('joint/axis').set('xyz', '0 1 0')
        robot.find('link/inertial/origin').set('xyz', '1 0 0')
        robot.find('link/inertial/inertia').set('ixx', '9')
        report = compare_export(expected, robot)
        self.assertEqual(report['status'], 'error')
        self.assertTrue({'axis', 'center_of_mass', 'inertia'} <= {d['field'] for d in report['differences']})
        self.assertTrue(all(d['target'] in {'a', 'j'} for d in report['differences']))

    def test_observed_state_missing_and_nonzero_are_errors(self):
        from URDF_Exporter.standalone.export_consistency import check_observed_positions
        _, robot = fixture()
        self.assertEqual(check_observed_positions(robot, {'j': 0})['status'], 'ok')
        self.assertEqual(check_observed_positions(robot, {})['status'], 'unverified')
        self.assertEqual(check_observed_positions(robot, {'j': .1})['status'], 'error')

    def test_mimic_offset_checked_from_driver_state(self):
        from URDF_Exporter.standalone.export_consistency import check_observed_positions
        _, robot = fixture()
        joint = copy.deepcopy(robot.find('joint'))
        joint.set('name', 'f')
        joint.find('parent').set('link', 'a')
        joint.find('child').set('link', 'b')
        ET.SubElement(joint, 'mimic', joint='j', multiplier='-1', offset='0.2')
        ET.SubElement(robot, 'link', name='b')
        robot.append(joint)
        report = check_observed_positions(robot, {'j': 0, 'f': .2})
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(check_observed_positions(robot, {'j': 0, 'f': 0})['status'], 'error')

    def test_extra_movable_joint_and_mimic_are_not_silent(self):
        from URDF_Exporter.standalone.export_consistency import compare_export
        expected, robot = fixture()
        ET.SubElement(robot.find('joint'), 'mimic', joint='absent')
        self.assertEqual(compare_export(expected, robot)['status'], 'error')
