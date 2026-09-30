import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def legacy_fixture(project_dir: Path):
    source_dir = project_dir / "sources"
    source_dir.mkdir(parents=True)
    manifest = {
        "format": "petasos-assembly",
        "source": {"application": "Autodesk Inventor", "adapter": "petasos-inventor-active"},
        "assembly": {"units": "mm"},
        "parts": [
            {
                "id": "finger",
                "physical": {
                    "mass": 0.027,
                    "center_of_mass": [-0.119244988, 0.077089474, 0.921020752],
                    "inertia": [1e-6, 1e-6, 1e-6, 0, 0, 0],
                    "provenance": "inventor_mass_properties",
                },
            }
        ],
    }
    (source_dir / "inventor-import.petasos.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    state = {
        "project_name": "robot",
        "report": {"source_application": "Autodesk Inventor"},
        "tree": {"name": "base_link", "components": ["finger"], "children": []},
        "visual_transforms": {"finger": [1, 0, 0, 0] * 4},
        "inertial": {
            "finger": {
                "mass": 0.027,
                "center_of_mass": [-0.000119244988, 0.000077089474, 0.000921020752],
                "inertia": [1e-6, 1e-6, 1e-6, 0, 0, 0],
                "provenance": "cad_metadata",
            }
        },
        "parts": [
            {
                "part_id": "finger",
                "physical": {
                    "center_of_mass": [-0.000119244988, 0.000077089474, 0.000921020752],
                    "mass": 0.027,
                },
            }
        ],
    }
    return state, manifest


class LegacyInventorPhysicalMigrationTests(unittest.TestCase):
    def test_restores_legacy_center_without_changing_tree_or_poses(self):
        from URDF_Exporter.standalone.physical_migration import repair_legacy_inventor_com

        with tempfile.TemporaryDirectory() as temporary:
            state, _ = legacy_fixture(Path(temporary))
            before = copy.deepcopy(state)
            repaired, diagnostics = repair_legacy_inventor_com(state, Path(temporary))

        self.assertEqual(diagnostics, [])
        self.assertEqual(repaired["inertial"]["finger"]["center_of_mass"],
                         [-0.119244988, 0.077089474, 0.921020752])
        self.assertEqual(repaired["parts"][0]["physical"]["center_of_mass"],
                         [-0.119244988, 0.077089474, 0.921020752])
        self.assertEqual(repaired["tree"], before["tree"])
        self.assertEqual(repaired["visual_transforms"], before["visual_transforms"])
        self.assertEqual(state, before)
        self.assertEqual(repaired["physical_com_schema"], 2)

    def test_second_run_and_explicit_mm_manifest_are_unchanged(self):
        from URDF_Exporter.standalone.physical_migration import repair_legacy_inventor_com

        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            state, manifest = legacy_fixture(project_dir)
            repaired, _ = repair_legacy_inventor_com(state, project_dir)
            again, diagnostics = repair_legacy_inventor_com(repaired, project_dir)
            self.assertEqual(again, repaired)
            self.assertEqual(diagnostics, [])

            manifest["parts"][0]["physical"]["center_of_mass_units"] = "mm"
            (project_dir / "sources" / "inventor-import.petasos.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            new_state = copy.deepcopy(state)
            new_state["inertial"]["finger"]["center_of_mass"] = [-0.119244988, 0.077089474, 0.921020752]
            unchanged, diagnostics = repair_legacy_inventor_com(new_state, project_dir)
            self.assertEqual(diagnostics, [])
            self.assertEqual(unchanged["inertial"], new_state["inertial"])

    def test_missing_manifest_and_third_party_sources_are_not_guessed(self):
        from URDF_Exporter.standalone.physical_migration import repair_legacy_inventor_com

        with tempfile.TemporaryDirectory() as temporary:
            state, manifest = legacy_fixture(Path(temporary))
            source_path = Path(temporary) / "sources" / "inventor-import.petasos.json"
            source_path.unlink()
            unchanged, diagnostics = repair_legacy_inventor_com(state, Path(temporary))
            self.assertEqual(unchanged["inertial"], state["inertial"])
            self.assertEqual(diagnostics[0]["code"], "legacy_inventor_manifest_missing")

            manifest["source"]["adapter"] = "third-party"
            source_path.write_text(json.dumps(manifest), encoding="utf-8")
            unchanged, diagnostics = repair_legacy_inventor_com(state, Path(temporary))
            self.assertEqual(diagnostics, [])
            self.assertEqual(unchanged["inertial"], state["inertial"])

    def test_project_export_uses_repaired_state_and_persists_only_after_success(self):
        from URDF_Exporter.standalone.server import ProjectStore

        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary) / "projects" / "robot"
            state, _ = legacy_fixture(project_dir)
            store = ProjectStore(
                projects_root=Path(temporary) / "projects",
                export_root=Path(temporary) / "export",
            )
            store.project_dir = project_dir
            store.state = copy.deepcopy(state)
            seen_centers = []

            def fake_export(export_state, *_args, **_kwargs):
                seen_centers.append(export_state["inertial"]["finger"]["center_of_mass"])
                return {"save_dir": str(Path(temporary) / "export" / "robot_description"), "bundle_dir": None}

            with mock.patch("URDF_Exporter.standalone.server.export_project", side_effect=fake_export):
                store.export(state["tree"], fix_to_world=True)

            self.assertEqual(seen_centers, [[-0.119244988, 0.077089474, 0.921020752]])
            saved = json.loads((project_dir / "project_state.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["inertial"]["finger"]["center_of_mass"], seen_centers[0])
            self.assertEqual(saved["tree"], state["tree"])

    def test_opening_saved_project_repairs_memory_without_rewriting_saved_file(self):
        from URDF_Exporter.standalone.server import ProjectStore

        with tempfile.TemporaryDirectory() as temporary:
            projects_root = Path(temporary) / "projects"
            project_dir = projects_root / "robot"
            state, _ = legacy_fixture(project_dir)
            saved_path = project_dir / "project_state.json"
            original_text = json.dumps(state)
            saved_path.write_text(original_text, encoding="utf-8")
            (projects_root / ".last_project").write_text(str(project_dir), encoding="utf-8")

            store = ProjectStore(projects_root=projects_root)

            self.assertEqual(store.state["inertial"]["finger"]["center_of_mass"],
                             [-0.119244988, 0.077089474, 0.921020752])
            self.assertEqual(saved_path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
