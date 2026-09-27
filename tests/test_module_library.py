import tempfile
import unittest
import zipfile
from pathlib import Path
from tests.test_module_geometry import fixture
from URDF_Exporter.standalone.module_geometry import capture_module
from URDF_Exporter.standalone.module_library import ModuleLibrary


class ModuleLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = ModuleLibrary(self.root / 'library')
        state, tree = fixture()
        self.payload = capture_module(state, tree, tree['_modules'][0]['id'])
        self.meshes = self.root / 'meshes'
        self.meshes.mkdir()
        for name in ('palm_part', 'finger_part'):
            (self.meshes / (name + '.stl')).write_bytes(b'solid test\nendsolid test')

    def test_archive_roundtrip(self):
        summary = self.library.save(self.payload, self.meshes)
        archive = self.library.export_archive(summary['id'], self.root / 'module.zip')
        imported = self.library.import_archive(archive)
        payload, folder = self.library.load(imported['id'])
        self.assertEqual(payload, self.payload)
        self.assertNotEqual(imported['id'], summary['id'])
        self.assertEqual((folder / 'meshes/palm_part.stl').read_bytes(), (self.meshes / 'palm_part.stl').read_bytes())

    def test_rejects_zip_slip_symlink_duplicate_and_case_collision(self):
        for names in [('../outside.stl',), ('/absolute.stl',), ('C:/outside.stl',),
                      ('a.stl', 'a.stl'), ('a.stl', 'A.stl'), ('CON.stl',), ('a:stream.stl',)]:
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                for name in names:
                    zipped.writestr(name, b'test')
            with self.assertRaises(ValueError):
                self.library.import_archive(archive)
        with zipfile.ZipFile(self.root / 'bad.zip', 'w') as zipped:
            info = zipfile.ZipInfo('link.stl')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            zipped.writestr(info, b'/outside')
        with self.assertRaises(ValueError):
            self.library.import_archive(self.root / 'bad.zip')
        self.assertEqual(self.library.list_modules(), [])

    def test_limits_and_version(self):
        summary = self.library.save(self.payload, self.meshes)
        archive = self.library.export_archive(summary['id'], self.root / 'module.zip')
        for limits in ({'compressed_limit': 1}, {'expanded_limit': 1}, {'file_limit': 1}):
            with self.assertRaises(ValueError):
                ModuleLibrary(self.root / 'other', **limits).import_archive(archive)
        self.payload['version'] = 9
        with self.assertRaises(ValueError):
            self.library.save(self.payload, self.meshes)
