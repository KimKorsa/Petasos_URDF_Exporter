import tempfile
import unittest
from pathlib import Path

from URDF_Exporter.standalone.server import ProjectStore, create_app


class ApiInputValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = create_app(ProjectStore(root / 'projects', root / 'export'))
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_non_object_json_is_rejected_by_editor_endpoints(self):
        routes = ('/workspace/save', '/workspace/reload', '/save', '/export/prepare',
                  '/export/commit', '/export/cancel', '/modules/create', '/modules/placement')
        for route in routes:
            for payload in ([1], 'invalid', 1, True):
                with self.subTest(route=route, payload=payload):
                    response = self.client.post(route, json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertIsInstance(response.get_json().get('error'), str)

    def test_invalid_tree_and_malformed_json_are_rejected_before_mutation(self):
        for route in ('/workspace/save', '/save', '/export/prepare', '/modules/validate'):
            for payload in ({'tree': [1]}, {'tree': 'invalid'}, {'tree': None}):
                with self.subTest(route=route, payload=payload):
                    response = self.client.post(route, json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertIsInstance(response.get_json().get('error'), str)
            response = self.client.post(route, data='{broken', content_type='application/json')
            self.assertEqual(response.status_code, 400)
            self.assertIsInstance(response.get_json().get('error'), str)
