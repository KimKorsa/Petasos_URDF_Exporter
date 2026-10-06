import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from URDF_Exporter.standalone.server import ProjectStore, create_app


def report(status="ok", severity=None):
    diagnostics = [] if severity is None else [{
        "code": "example", "severity": severity, "targets": ["finger"],
        "observed": "overlap", "expected": "clear", "action": "Review contact",
    }]
    return {"status": status, "diagnostics": diagnostics, "summary": {
        "errors": int(severity == "error"), "warnings": int(severity == "warning"),
        "not_checked": int(severity == "not_checked"),
    }}


class ExportTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ProjectStore(self.root / "projects", self.root / "export")
        self.store.project_dir = self.root / "projects" / "robot"
        self.store.project_dir.mkdir()
        self.store.state = {"project_name": "robot", "tree": {"name": "base_link"}}
        (self.store.project_dir / "project_state.json").write_text(
            json.dumps(self.store.state), encoding="utf-8"
        )
        self.old = self.store.export_root / "ros_ws"
        self.old.mkdir()
        (self.old / "sentinel.txt").write_text("old export", encoding="utf-8")

    def fake_export(self, _state, _tree, _fixed, _project_dir, **kwargs):
        stage = Path(kwargs["output_root"])
        description = stage / "ros_ws" / "src" / "robot_description"
        (description / "analysis").mkdir(parents=True)
        (description / "new.txt").write_text("new export", encoding="utf-8")
        return {"save_dir": str(description), "bundle_dir": str(stage / "ros_ws"),
                "include_moveit": True, "link_count": 2, "joint_count": 1,
                "moveit_readiness": {}}

    def prepare(self, result):
        with mock.patch("URDF_Exporter.standalone.server.export_project", side_effect=self.fake_export), \
             mock.patch("URDF_Exporter.standalone.server.inspect_candidate", return_value=result):
            return self.store.prepare_export({"name": "base_link"}, True, True)

    def test_error_and_unacknowledged_warning_preserve_existing_workspace(self):
        prepared = self.prepare(report("error", "error"))
        with self.assertRaisesRegex(ValueError, "error|오류"):
            self.store.commit_export(prepared["token"], True)
        self.assertEqual((self.old / "sentinel.txt").read_text(), "old export")
        prepared = self.prepare(report("warning", "not_checked"))
        with self.assertRaisesRegex(ValueError, "warning|확인"):
            self.store.commit_export(prepared["token"], False)
        self.assertEqual((self.old / "sentinel.txt").read_text(), "old export")

    def test_stale_revision_and_publish_failure_restore_old_output(self):
        prepared = self.prepare(report())
        self.store.revision += 1
        with self.assertRaisesRegex(ValueError, "변경|stale"):
            self.store.commit_export(prepared["token"], True)
        self.assertEqual((self.old / "sentinel.txt").read_text(), "old export")
        prepared = self.prepare(report())
        import os
        real_replace = os.replace

        def fail_new(source, target):
            if ".petasos-stage-" in str(source) and Path(source).name == "ros_ws":
                raise OSError("injected publish failure")
            return real_replace(source, target)

        with mock.patch("URDF_Exporter.standalone.server.os.replace", side_effect=fail_new):
            with self.assertRaisesRegex(OSError, "injected"):
                self.store.commit_export(prepared["token"], True)
        self.assertEqual((self.old / "sentinel.txt").read_text(), "old export")

    def test_acknowledged_candidate_publishes_report_and_new_workspace(self):
        prepared = self.prepare(report("warning", "not_checked"))
        result = self.store.commit_export(prepared["token"], True)
        self.assertEqual((self.old / "src" / "robot_description" / "new.txt").read_text(), "new export")
        self.assertTrue((self.old / "src" / "robot_description" / "analysis" / "export_preflight.json").is_file())
        self.assertEqual(result["preflight"]["status"], "warning")
        self.assertEqual(Path(result["bundle_dir"]), self.old)

    def test_api_exposes_named_diagnostics_and_requires_acknowledgement(self):
        app = create_app(self.store)
        client = app.test_client()
        with mock.patch("URDF_Exporter.standalone.server.export_project", side_effect=self.fake_export), \
             mock.patch("URDF_Exporter.standalone.server.inspect_candidate", return_value=report("warning", "not_checked")):
            response = client.post("/export/prepare", json={
                "tree": {"name": "base_link"}, "include_moveit": True,
            })
        self.assertEqual(response.status_code, 200)
        prepared = response.get_json()
        self.assertEqual(prepared["preflight"]["diagnostics"][0]["targets"], ["finger"])
        denied = client.post("/export/commit", json={"token": prepared["token"]})
        self.assertEqual(denied.status_code, 409)
        accepted = client.post("/export/commit", json={
            "token": prepared["token"], "acknowledge_warnings": True,
        })
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["preflight"]["summary"]["not_checked"], 1)

    def test_repeated_commits_keep_only_latest_backup(self):
        backups = []
        for _ in range(3):
            prepared = self.prepare(report())
            result = self.store.commit_export(prepared["token"], True)
            backups.append(result["previous_export_backup"])
        remaining = sorted(self.store.export_root.glob(".petasos-backup-*"))
        self.assertEqual([str(path.resolve()) for path in remaining], [backups[-1]])
        self.assertEqual(list(self.store.export_root.glob(".petasos-stage-*")), [])

    def test_startup_removes_orphaned_stage_and_old_backups(self):
        import os
        import time
        export_root = self.store.export_root
        (export_root / ".petasos-stage-orphan" / "ros_ws").mkdir(parents=True)
        old_backup = export_root / ".petasos-backup-old"
        new_backup = export_root / ".petasos-backup-new"
        old_backup.mkdir()
        new_backup.mkdir()
        past = time.time() - 3600
        os.utime(old_backup, (past, past))
        ProjectStore(self.root / "projects", export_root)
        self.assertFalse((export_root / ".petasos-stage-orphan").exists())
        self.assertFalse(old_backup.exists())
        self.assertTrue(new_backup.exists())
        self.assertTrue(self.old.exists())

    def test_prepare_rejects_stale_module_revision(self):
        self.store.state["tree"]["_modules"] = [{"id": "m1"}]
        client = create_app(self.store).test_client()
        response = client.post("/export/prepare", json={
            "tree": {"name": "base_link", "_module_revision": self.store.revision + 1},
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(list(self.store.export_root.glob(".petasos-stage-*")), [])


if __name__ == "__main__":
    unittest.main()
