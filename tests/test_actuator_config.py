import math
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from URDF_Exporter.core import Actuator, Write


class ActuatorConfigTests(unittest.TestCase):
    def test_mixed_models_have_independent_ratios(self):
        self.assertEqual(Actuator.normalize({'model': 'AK45-36'})['gear_ratio'], 36)
        self.assertEqual(Actuator.normalize({'model': 'AK45-10'})['gear_ratio'], 10)

    def test_output_feedback_is_not_reduced_twice(self):
        config = Actuator.normalize({'model': 'AK45-36', 'feedback_reference': 'output_shaft',
                                     'direction': -1, 'zero_offset': 0.2})
        self.assertAlmostEqual(Actuator.feedback_to_joint(1.2, config), -1)
        config['feedback_reference'] = 'motor_shaft'
        self.assertAlmostEqual(Actuator.feedback_to_joint(43.2, config), -1)

    def test_position_command_round_trip_uses_selected_reference(self):
        for reference in ('motor_shaft', 'output_shaft'):
            config = Actuator.normalize({'model': 'AK45-10', 'command_reference': reference,
                                         'feedback_reference': reference, 'direction': -1,
                                         'zero_offset': 0.25})
            command = Actuator.joint_to_command(math.pi / 2, config)
            self.assertAlmostEqual(Actuator.feedback_to_joint(command, config), math.pi / 2)

    def test_invalid_hardware_values_are_rejected(self):
        for value in ({'gear_ratio': 0}, {'gear_ratio': float('nan')}, {'direction': 0},
                      {'command_reference': 'unknown'}, {'zero_offset': float('inf')}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Actuator.normalize({'model': 'custom', **value})

    def test_export_keeps_joint_limits_and_includes_actuator_settings(self):
        joints = {'joint_1': {'type': 'revolute', 'lower_limit': -1, 'upper_limit': 1,
                             'effort_limit': 8, 'velocity_limit': 1,
                             'actuator': {'model': 'AK45-36', 'direction': -1,
                                          'zero_offset': 0.1}}}
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'urdf').mkdir()
            Write.write_transmissions_xacro(joints, 'robot', folder)
            root = ET.parse(Path(folder, 'urdf/robot.trans')).getroot()
            joint = root.find('ros2_control/joint')
            params = {p.get('name'): p.text for p in joint.findall('param')}
            self.assertEqual(params['actuator_gear_ratio'], '36.0')
            self.assertEqual(params['actuator_command_reference'], 'output_shaft')
            self.assertEqual(joint.find("command_interface/param[@name='min']").text, '-1.0')
            path = Write.write_actuator_config(joints, folder)
            self.assertTrue(path.is_file())
            document = json.loads(path.read_text(encoding='utf-8'))
            config = document['joints']['joint_1']
            self.assertEqual(config['gear_ratio'], 36)
            self.assertEqual(config['direction'], -1)
            self.assertEqual(config['zero_offset'], 0.1)
            self.assertEqual(config['zero_offset_unit'], 'output_shaft_rad')
            self.assertEqual(config['output_limits'], {'max_velocity_rad_s': 1, 'max_torque_nm': 8})
            self.assertTrue(document['driver_integration_required'])


if __name__ == '__main__':
    unittest.main()
