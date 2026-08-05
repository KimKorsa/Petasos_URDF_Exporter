"""Manual Windows smoke test for the native Inventor assembly adapter."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pythoncom
import win32com.client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from URDF_Exporter.standalone.adapters.inventor import (
    _convert_open_document,
    convert_with_inventor,
)
from URDF_Exporter.standalone.importers import build_project


K_PART_DOCUMENT = 12290
K_ASSEMBLY_DOCUMENT = 12291


def _make_box_part(app, path: Path, size_cm: tuple[float, float, float]) -> None:
    document = app.Documents.Add(K_PART_DOCUMENT, "", False)
    geometry = app.TransientGeometry
    box = geometry.CreateBox()
    box.PutBoxData((0.0, 0.0, 0.0), size_cm)
    body = app.TransientBRep.CreateSolidBlock(box)
    document.ComponentDefinition.Features.NonParametricBaseFeatures.Add(body)
    document.SaveAs(str(path), False)
    document.Close(True)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pythoncom.CoInitialize()
        app = win32com.client.DispatchEx("Inventor.Application")
        app.Visible = False
        try:
            app.SilentOperation = True
            base_path = root / "base.ipt"
            arm_path = root / "arm.ipt"
            _make_box_part(app, base_path, (10.0, 8.0, 3.0))
            _make_box_part(app, arm_path, (3.0, 3.0, 20.0))

            assembly = app.Documents.Add(K_ASSEMBLY_DOCUMENT, "", False)
            geometry = app.TransientGeometry
            base_occurrence = assembly.ComponentDefinition.Occurrences.Add(
                str(base_path),
                geometry.CreateMatrix(),
            )
            base_occurrence.Grounded = True
            arm_matrix = geometry.CreateMatrix()
            arm_matrix.SetTranslation(geometry.CreateVector(0.0, 0.0, 15.0))
            assembly.ComponentDefinition.Occurrences.Add(str(arm_path), arm_matrix)
            assembly_path = root / "smoke_robot.iam"
            assembly.SaveAs(str(assembly_path), False)

            active_output = root / "active_import"
            active_manifest_path = _convert_open_document(
                app,
                assembly,
                active_output,
                "active_smoke_robot",
                str(assembly_path),
                "petasos-inventor-active",
            )
            active_manifest = json.loads(
                active_manifest_path.read_text(encoding="utf-8")
            )
            assert len(active_manifest["parts"]) == 2
            assert len(active_manifest["joints"]) == 1
            assert active_manifest["joints"][0]["provenance"] == "inventor_recovered_constraint"
            assert active_manifest["source"]["adapter"] == "petasos-inventor-active"
            assert active_manifest["assembly"]["up_axis"] == "y"
            assert assembly.FullFileName == str(assembly_path)
            assembly.Close(True)
        finally:
            app.Quit()
            pythoncom.CoUninitialize()

        path_output = root / "path_import"
        manifest_path = convert_with_inventor(
            assembly_path,
            path_output,
            "smoke_robot",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest["parts"]) == 2
        assert len(manifest["joints"]) == 1
        assert manifest["joints"][0]["provenance"] == "inventor_recovered_constraint"
        assert manifest["source"]["adapter"] == "petasos-inventor-path"
        assert manifest["assembly"]["up_axis"] == "y"
        assert all(
            (path_output / part["geometry"]).is_file()
            for part in manifest["parts"]
        )
        assert all(part.get("physical", {}).get("mass", 0) > 0 for part in manifest["parts"])
        project = build_project(
            str(path_output),
            str(root / "meshes"),
            "smoke_robot",
        )
        assert project["report"]["parts"] == 2
        assert project["report"]["joints"] == 1
        assert project["tree"]["_standalone"] is True
        assert (
            project["tree"]["children"][0]["joint_info"]["provenance"]
            == "inventor_recovered_constraint"
        )
        print(json.dumps({
            "parts": project["report"]["parts"],
            "joints": project["report"]["joints"],
            "positions_mm": [part["transform"]["position"] for part in manifest["parts"]],
            "masses_kg": [part["physical"]["mass"] for part in manifest["parts"]],
            "active_import": {
                "parts": len(active_manifest["parts"]),
                "joints": len(active_manifest["joints"]),
            },
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
