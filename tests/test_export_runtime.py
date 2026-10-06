import unittest
from types import SimpleNamespace as NS
from xml.etree import ElementTree as ET


class ExportRuntimeTests(unittest.TestCase):
    def test_contacts_keep_link_names_and_depth(self):
        from moveit.check_export_runtime import summarize_validity
        response = NS(valid=False, contacts=[NS(contact_body_1='palm', contact_body_2='finger', depth=.01,
                      position=NS(x=1., y=2., z=3.), normal=NS(x=0., y=0., z=1.))])
        report = summarize_validity(response, {'j': 0}, None)
        self.assertEqual(report['status'], 'collision')
        self.assertEqual(report['contacts'][0]['links'], ['palm', 'finger'])
        self.assertEqual(report['pose'], {'j': 0})

    def test_invalid_without_contact_not_mislabeled_collision(self):
        from moveit.check_export_runtime import summarize_validity
        self.assertEqual(summarize_validity(NS(valid=False, contacts=[]), {}, None)['status'], 'invalid')

    def test_missing_ros_returns_unverified(self):
        from moveit.check_export_runtime import check_state_validity
        from unittest.mock import patch
        with patch.dict('sys.modules', {'rclpy': None}):
            report = check_state_validity(ET.fromstring('<robot/>'), None, {})
        self.assertEqual(report['status'], 'unverified')
