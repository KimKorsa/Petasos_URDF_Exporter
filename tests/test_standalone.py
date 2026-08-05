import io
import json
import math
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

import trimesh

from URDF_Exporter.standalone.server import (
    ProjectStore,
    WslRvizRunner,
    _windows_path_to_wsl,
    create_app,
    run,
)
from URDF_Exporter.standalone.occ_loader import load_ocp
from URDF_Exporter.standalone.exporter import (
    _copy_mesh_as_binary_stl,
    _is_binary_stl,
    _root_link_pose,
    _root_orientation_rpy,
    _root_origin_xyz,
    _validate_joint_limits,
)
from URDF_Exporter.standalone.adapters.inventor import (
    _select_open_assembly_document,
    matrix_transform,
    relative_transform,
)
from moveit.validate_moveit_config import (
    repair_joint_limits,
    validate_moveit_package,
)
from moveit.generate_smoke_config import generate_smoke_config
from moveit.wsl_runner import WslMoveItRunner, _robot_details
from moveit.validate_urdf import validate_urdf_for_moveit
from moveit.prepare_assistant_urdf import prepare_assistant_urdf


class StandaloneFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.temp_dir.name) / "projects")
        self.app = create_app(self.store)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def stl_bytes(self, size):
        mesh = trimesh.creation.box(extents=size)
        return mesh.export(file_type="stl")

    def test_ascii_stl_is_normalized_to_binary_for_rviz(self):
        ascii_stl = b"""solid triangle
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid triangle
"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            source = os.path.join(temporary_dir, "ascii.stl")
            target = os.path.join(temporary_dir, "binary.stl")
            Path(source).write_bytes(ascii_stl)

            self.assertFalse(_is_binary_stl(source))
            _copy_mesh_as_binary_stl(source, target)

            self.assertTrue(_is_binary_stl(target))
            self.assertEqual(len(trimesh.load_mesh(target, file_type="stl").faces), 1)

    def step_assembly_bytes(self, single_solid=False):
        load_ocp()
        from OCP import (
            BRep,
            BRepPrimAPI,
            STEPCAFControl,
            STEPControl,
            TCollection,
            TDocStd,
            TopLoc,
            TopoDS,
            XCAFDoc,
            gp,
        )

        base = BRepPrimAPI.BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        arm = BRepPrimAPI.BRepPrimAPI_MakeBox(5, 5, 40).Shape()
        transform = gp.gp_Trsf()
        transform.SetTranslation(gp.gp_Vec(125, 0, 50))
        arm = arm.Located(TopLoc.TopLoc_Location(transform))
        exported_shape = base
        if not single_solid:
            assembly = TopoDS.TopoDS_Compound()
            builder = BRep.BRep_Builder()
            builder.MakeCompound(assembly)
            builder.Add(assembly, base)
            builder.Add(assembly, arm)
            exported_shape = assembly

        document = TDocStd.TDocStd_Document(
            TCollection.TCollection_ExtendedString("XmlXCAF")
        )
        shape_tool = XCAFDoc.XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        shape_tool.AddShape(exported_shape, True, True)
        writer = STEPCAFControl.STEPCAFControl_Writer()
        self.assertTrue(writer.Transfer(document, STEPControl.STEPControl_AsIs))
        step_path = Path(self.temp_dir.name) / "assembly.step"
        writer.Write(str(step_path))
        return step_path.read_bytes()

    def manifest(self):
        return {
            "format": "petasos-assembly",
            "version": "1.0",
            "source": {"application": "Test CAD"},
            "assembly": {
                "name": "simple_arm",
                "units": "mm",
                "angle_units": "deg",
                "up_axis": "z",
                "handedness": "right",
            },
            "parts": [
                {
                    "id": "base",
                    "name": "base",
                    "geometry": "base.stl",
                    "physical": {
                        "mass": 3.0,
                        "center_of_mass": [0, 0, 10],
                        "inertia": [0.02, 0.02, 0.02, 0, 0, 0],
                    },
                },
                {
                    "id": "arm",
                    "name": "arm",
                    "geometry": "arm.stl",
                    "transform": {"position": [0, 0, 150], "rotation": [0, 0, 0]},
                    "physical": {
                        "mass": 1.0,
                        "center_of_mass": [0, 0, 50],
                        "inertia": [0.01, 0.01, 0.002, 0, 0, 0],
                    },
                },
            ],
            "joints": [
                {
                    "name": "base_to_arm",
                    "parent": "base",
                    "child": "arm",
                    "type": "revolute",
                    "origin": {"xyz": [0, 0, 150], "rpy": [0, 0, 0]},
                    "axis": [0, 1, 0],
                    "limits": {"lower": -90, "upper": 90},
                    "provenance": "test_cad_joint",
                }
            ],
        }

    def write_fake_inventor_exchange(self, output_dir, adapter):
        source = Path(output_dir)
        source.mkdir(parents=True, exist_ok=True)
        (source / "base.stl").write_bytes(self.stl_bytes([100, 100, 30]))
        (source / "arm.stl").write_bytes(self.stl_bytes([25, 25, 200]))
        manifest = self.manifest()
        manifest["source"] = {
            "application": "Autodesk Inventor",
            "document": "robot.iam",
            "adapter": adapter,
        }
        path = source / "inventor-import.petasos.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def import_demo(self):
        response = self.client.post(
            "/import",
            data={
                "project_name": "Simple Arm",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (
                        io.BytesIO(json.dumps(self.manifest()).encode("utf-8")),
                        "simple-arm.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def test_empty_app_uses_a1_editor_in_standalone_mode(self):
        response = self.client.get("/data")
        self.assertEqual(response.status_code, 200)
        tree = response.get_json()
        self.assertTrue(tree["_standalone"])
        self.assertTrue(tree["_empty"])
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn(".iam", html)
        self.assertIn("width: clamp(300px, 20vw, 380px)", html)
        self.assertIn("flex: 0 0 clamp(300px, 20vw, 380px)", html)
        self.assertIn("IAM은 형상을 내장하지 않습니다", html)
        self.assertIn("LINK_GROUP_COLORS", html)
        self.assertIn("applyLinkGroupColors", html)
        self.assertNotIn("같은 링크로 묶을 카드", html)
        self.assertIn("THREE.EdgesGeometry", html)
        self.assertIn("handleViewerMeshPick", html)
        self.assertIn("findMeshByProjectedBounds", html)
        self.assertIn("viewer-located", html)
        self.assertIn("addEventListener('dblclick'", html)
        self.assertIn("집중 보기 해제 · 전체 부품 보기", html)
        self.assertIn("selectedLinkPulse", html)
        self.assertIn("선택 링크 다시 찾기", html)
        self.assertIn("모델 위쪽 축", html)
        self.assertIn("compact-children", html)
        self.assertIn("ground-face-button", html)
        self.assertIn("handleGroundFacePick", html)
        self.assertIn("planarFaceSnapCandidate", html)
        self.assertIn("meshComponentByObject = new WeakMap()", html)
        self.assertIn("{ refreshMatrices: false }", html)
        self.assertIn("{ hoverOnly: true }", html)
        self.assertIn("if (options.hoverOnly) return null", html)
        self.assertIn("normalizedRadius", html)
        self.assertIn("rankedCandidates.slice(0, 24)", html)
        self.assertIn("const nearestSurfaceDepth = new Map()", html)
        self.assertIn("candidateDepth > visibleSurfaceDepth + depthTolerance", html)
        self.assertIn("connected_planar_face_centroid", html)
        self.assertIn("showGroundSnapMarker", html)
        self.assertIn("ground-align-edge", html)
        self.assertIn("normal_center_and_boundary_axis", html)
        self.assertIn("boundaryDirectionClusters", html)
        self.assertIn("_preview_root_quaternion", html)
        self.assertIn(">로봇 구조 트리</div>", html)
        self.assertNotIn("로봇 구조 트리 (메인맵)", html)
        self.assertNotIn("🛠️ URDF 구조 병합 및 3D 프리뷰 에디터", html)
        self.assertNotIn("👁️ 로봇 3D 뷰어", html)
        self.assertNotIn("🧠 로봇 구조 트리", html)
        self.assertIn(".tree-title-overlay { left: 20px; }", html)
        self.assertIn("padding-top: 24px; box-sizing: border-box;", html)
        self.assertIn("patcher-canvas", html)
        self.assertIn("patcher-viewport", html)
        self.assertIn("zoomPatcher", html)
        self.assertIn("fitPatcherView", html)
        self.assertIn("patcher-arrow-fixed", html)
        self.assertIn("togglePatcherGroupingMode", html)
        self.assertIn("mergePatcherSelection", html)
        self.assertIn("mergePatcherNodeInto", html)
        self.assertIn("ungroupSelectedPatcherLink", html)
        self.assertIn("ungroupPatcherLink", html)
        self.assertIn("patcher-ungroup-selected", html)
        self.assertIn("applyMergedLinkColor", html)
        self.assertIn("findPatcherMergeTarget", html)
        self.assertIn("attachPatcherNodeMove(box", html)
        self.assertIn("pointerInside || ratio >= 0.08", html)
        self.assertIn("merge-drop-target", html)
        self.assertIn("WORLD 출력 포트", html)
        self.assertIn("setPatcherWorldRoot", html)
        self.assertIn("beginPatcherConnection", html)
        self.assertIn("validatePatcherGraph", html)
        self.assertIn("patcherActiveChildren", html)
        self.assertIn("connected-output", html)
        self.assertIn("add-output", html)
        self.assertIn("새 분기 출력 포트", html)
        self.assertIn("patcherConnectionDrag.outputKey", html)
        self.assertIn("isPatcherGroupCandidate", html)
        self.assertIn("group_candidate", html)
        self.assertIn("never create a movable pivot or a visible joint frame", html)
        self.assertIn("renderPatcher(container);", html)
        self.assertIn("선택된 항목 속성", html)
        self.assertNotIn("🔍 선택된 항목 속성", html)
        self.assertNotIn("🗂️ 링크 리스트", html)
        self.assertNotIn("카드 겹치기 = 링크 병합", html)
        self.assertNotIn("자유 배치 링크 그룹화 + 조인트 배선", html)
        self.assertNotIn("링크 카드 겹쳐 놓기", html)
        self.assertIn("controls.mouseButtons.MIDDLE = THREE.MOUSE.PAN", html)
        self.assertIn("handleViewerMeshSelect", html)
        self.assertIn("viewerSelectedComponents = new Set()", html)
        self.assertIn("groupViewerSelectedComponents", html)
        self.assertIn("viewer-context-menu", html)
        self.assertIn("activateSelectedJoint", html)
        self.assertIn("const TREE_EDITOR_MODE = false", html)
        self.assertIn("tree-wire-port", html)
        self.assertIn("renderTreeWires", html)
        self.assertIn("armTreeConnection", html)
        self.assertIn("finishTreeConnection", html)
        self.assertIn("treeWirePath", html)
        self.assertIn("autoRename(target)", html)
        self.assertIn(".patcher-node.disconnected .link-box.finalized", html)
        self.assertIn("? 'LINK'", html)
        self.assertIn("patcher-node-rename", html)
        self.assertIn("startPatcherLinkRename", html)
        self.assertIn("renameLinkNode", html)
        self.assertIn("toggleJointOriginPick", html)
        self.assertIn("handleJointOriginPick", html)
        self.assertIn("jointOriginPickStage = 'parent'", html)
        self.assertIn("jointOriginParentSnap", html)
        self.assertIn("refreshJointPickStageViewer", html)
        self.assertIn("applyLinkGroupColors();", html)
        self.assertIn("1/2 부모 연결점", html)
        self.assertIn("2/2 자식 연결점", html)
        self.assertIn("parent_child_surface_frames", html)
        self.assertIn("gap_m: mateGap / unitsPerMeter", html)
        self.assertIn("jointFrameFromSurface", html)
        self.assertIn("connected_planar_face_centroid_and_normal", html)
        self.assertIn("user_3d_joint_pick", html)
        self.assertIn("flipSelectedJointAxis", html)
        self.assertIn("delete jointInfo._joint_world_matrix", html)
        self.assertIn("ensureJointMotionLimits", html)
        self.assertIn("selectedJointMotionEditorHtml", html)
        self.assertIn('data-preview-joint-value="${index}"', html)
        self.assertIn("commitPreviewJointValue", html)
        self.assertIn("handlePreviewJointValueKey", html)
        self.assertIn("joint-current-input", html)
        self.assertIn("const connectedColumnGap = 290", html)
        self.assertIn("const connectedRowGap = 32", html)
        self.assertIn("restoreImportedAssemblyPose(false)", html)
        self.assertIn("조립품 원래 자세로 복원", html)
        self.assertIn("saveWorkspace(true, saveName)", html)
        self.assertIn("scheduleWorkspaceAutosave", html)
        self.assertIn("workspace-active-save", html)
        self.assertIn("saveCurrentNamedWorkspace", html)
        self.assertIn("현재 작업에 이어 저장", html)
        self.assertIn("새 이름으로 저장", html)
        self.assertIn("선택한 작업 불러오기", html)
        self.assertIn("다른 이름으로 저장·불러오기", html)
        self.assertIn("workspace-saved-list", html)
        self.assertIn("CAD 조립품 불러오기", html)
        self.assertIn("이전 작업 불러오기", html)
        self.assertIn("standalone-workspace-list", html)
        self.assertIn("setStandaloneImportMode", html)
        self.assertIn("/workspace/list?all_projects=1", html)
        self.assertIn("loadStandaloneWorkspace", html)
        self.assertIn("extractComponentFromPatcherLink", html)
        self.assertIn("populateLinkPartsList", html)
        self.assertIn("링크에는 최소 한 개의 부품이 남아 있어야 합니다.", html)
        self.assertIn("remove.textContent = '⊖'", html)
        self.assertNotIn("remove.textContent = '빼기'", html)
        self.assertNotIn("remove.textContent = '⛔'", html)
        self.assertIn('aria-label="조립품 불러오기"', html)
        self.assertIn('aria-label="현재 작업 저장"', html)
        self.assertIn('aria-label="다른 이름으로 저장·불러오기"', html)
        self.assertIn('class="save-complete-icon"', html)
        self.assertIn("button.classList.toggle('is-saved', isSaved)", html)
        self.assertIn("setWorkspaceSaveButtonState('저장 완료')", html)
        self.assertIn("workspace-save-as-button", html)
        self.assertIn("saveActiveWorkspaceFromHeader", html)
        self.assertIn("openWorkspaceManager('save_as')", html)
        self.assertNotIn(
            "if (!saveName) {\n                openWorkspaceManager('save_as');",
            html,
        )
        self.assertIn('<svg viewBox="0 0 24 24" aria-hidden="true">', html)
        self.assertIn(".patcher-node.world-node {\n            width: 176px;", html)
        self.assertIn("height: 72px; min-height: 72px;", html)
        self.assertIn("disconnectPatcherPort", html)
        self.assertIn("더블클릭하면 이 배선을 끊습니다", html)
        self.assertIn('class="pane-section-divider"', html)
        self.assertIn("openStructureNamingAssistant", html)
        self.assertIn("buildStructureNamingPlan", html)
        self.assertIn("applyStructureNamingAssistant", html)
        self.assertIn("↕ 이름 정렬", html)
        self.assertIn("openStructureNamingAssistant(false)", html)
        self.assertIn("patcher-auto-layout-button", html)
        self.assertIn("patcher-name-order-button", html)
        self.assertIn("patcherLayoutNeedsAttention", html)
        self.assertIn("structureNamingNeedsAttention", html)
        self.assertIn("updatePatcherAssistantButtonStates", html)
        self.assertIn(".patcher-toolbar button.needs-attention", html)
        self.assertIn("정리 후 URDF 생성", html)
        self.assertIn("현재 이름 유지하고 생성", html)
        self.assertIn("continueExportWithoutStructureRename", html)
        self.assertIn("hasBlockingStructureProblem", html)
        self.assertIn("미연결 링크 ${structureNamingPlan.disconnectedLinks}개는 뒤 번호로 정리", html)
        self.assertLess(
            html.index('<div id="grouping-list"></div>'),
            html.index('<div class="pane-grouping-help">'),
        )
        self.assertIn("world_joint 생성", html)
        self.assertIn(
            'type="button" class="btn btn-green" onclick="saveAndExit()">URDF 생성</button>',
            html,
        )
        self.assertNotIn("바닥에 고정 (world_joint 생성)", html)
        self.assertNotIn("정리 완료 및 URDF 생성", html)
        self.assertIn("height: 38px; min-height: 38px; box-sizing: border-box;", html)
        self.assertIn("patcher-world-fix", html)
        self.assertIn("world-disabled", html)
        self.assertIn("worldFixControl.id = 'fix-to-world-label'", html)
        self.assertNotIn('<label id="fix-to-world-label"', html)
        self.assertIn('class="export-action-group"', html)
        self.assertIn('class="export-mode-control"', html)
        self.assertIn('<label for="export-mode">📦 출력 유형</label>', html)
        self.assertIn('aria-label="출력 유형"', html)
        self.assertIn("PETASOS_LOW_SPEC_RENDERING", html)
        self.assertIn("PREVIEW_FRAME_INTERVAL_MS", html)
        self.assertIn("antialias: !PETASOS_LOW_SPEC_RENDERING", html)
        self.assertIn("new ResizeObserver(onWindowResize)", html)
        self.assertIn("scheduleMeshEdges(mesh, geometry, comp)", html)
        self.assertIn("const mesh = new THREE.Mesh(geometry, defaultMaterial);", html)
        self.assertIn("const collisionMesh = new THREE.Mesh(\n                        geometry,", html)
        self.assertIn("border-radius: 4px 0 0 4px;", html)
        self.assertIn("border-radius: 0 4px 4px 0;", html)
        self.assertIn("finalizeConnectedPatcherNode", html)
        self.assertIn("syncPatcherJointLinkNames", html)
        self.assertIn("jointOriginToolsHtml", html)
        self.assertLess(
            html.index("${jointOriginToolsHtml}"),
            html.index("${groupCandidate ? `", html.index("${jointOriginToolsHtml}")),
        )
        self.assertIn("setPreviewJointLimit", html)
        self.assertIn("setPreviewJointLimitDegrees", html)
        self.assertIn("applyPreviewJointLimitDegrees", html)
        self.assertNotIn("clearPreviewJointLimit", html)
        self.assertIn("nudgePreviewJoint", html)
        self.assertIn("event.deltaY < 0 ? 1 : -1", html)
        self.assertIn("_manual_limit_lower_set", html)
        self.assertIn("_manual_limit_upper_set", html)
        self.assertIn("user_visual_joint_limit", html)
        self.assertIn("_preview_local_quaternion", html)
        self.assertIn("_preview_world_quaternion", html)
        self.assertIn("_preview_world_frame_matrix", html)
        self.assertIn("attachJointSnapMarkerToRig", html)
        self.assertIn("syncPickedJointLocalFrames", html)
        self.assertIn("areaWeightedNormal", html)
        self.assertIn("minimumNormalAgreement", html)
        self.assertIn("orthogonalityError", html)
        self.assertIn("root_y_axis", html)
        self.assertIn("fitCircularBoundary", html)
        self.assertIn("circular_arc_center", html)
        self.assertIn("cadSnapCandidate", html)
        self.assertIn("projectedCadSnapCandidates", html)
        self.assertIn("resolveBestSurfaceSnap", html)
        self.assertIn("screenDistanceToSegment", html)
        self.assertIn("Shift: 다음 후보", html)
        self.assertIn("jointPickAllowedComponents", html)
        self.assertIn("setJointPickComponentScope", html)
        self.assertIn("jointSnapCandidateKey", html)
        self.assertIn("selectJointSnapCandidate", html)
        self.assertIn("cycleJointSnapCandidate", html)
        self.assertIn("겹친 자석 선택", html)
        self.assertNotIn("Fusion식 겹친 자석 선택", html)
        self.assertIn("클릭 판정에 남길 부품", html)
        self.assertIn("IAM을 다시 가져와야 원·호 중심이 정확", html)
        self.assertIn("snapDisplayLabel", html)
        self.assertIn("opencascade_exact_geometry", html)
        self.assertIn("snap.snapSource === 'opencascade'", html)
        self.assertIn("viewerIsolatedNode", html)
        self.assertIn("applyViewerIsolationVisibility", html)
        self.assertIn("isolateSelectedJointChild", html)
        self.assertIn("👁 자식 링크만 보기", html)
        self.assertIn("setFromQuaternion(quaternion, 'ZYX')", html)
        self.assertIn("new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX')", html)
        self.assertIn("jointInfo.lower_limit = -Math.PI", html)
        self.assertIn("jointInfo.upper_limit = Math.PI", html)
        self.assertIn("min-width: 280px; max-width: 44vw", html)
        self.assertIn("fetch('/open-export-folder'", html)
        self.assertIn("startWslMoveItAssistant", html)
        self.assertIn("fetch('/moveit/wsl/assistant'", html)
        self.assertIn("fetch('/moveit/wsl/demo'", html)
        self.assertIn("fetch('/moveit/wsl/smoke'", html)
        self.assertIn("움직임 자동검사", html)
        self.assertIn('class="export-result-shell"', html)
        self.assertIn('class="export-result-summary"', html)
        self.assertIn('class="result-section"', html)
        self.assertIn("URDF 생성이 완료되었습니다", html)
        self.assertIn('id="export-mode"', html)
        self.assertIn('value="description" selected', html)
        self.assertIn('value="moveit"', html)
        self.assertIn("data.include_moveit", html)

    def test_health_endpoint_identifies_petasos_a2(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["application"], "petasos-a2")
        self.assertEqual(response.get_json()["status"], "ok")
        self.assertIsInstance(response.get_json()["pid"], int)

    def test_second_foreground_launcher_detects_the_existing_petasos_server(self):
        probe = mock.MagicMock()
        probe.__enter__.return_value.connect_ex.return_value = 0
        with (
            mock.patch(
                "URDF_Exporter.standalone.server.socket.socket",
                return_value=probe,
            ),
            mock.patch(
                "URDF_Exporter.standalone.server._petasos_server_is_healthy",
                return_value=True,
            ),
            mock.patch.dict(os.environ, {"PETASOS_NO_BROWSER": "1"}),
        ):
            self.assertFalse(run())

    def test_foreground_launcher_rejects_an_unrelated_port_owner(self):
        probe = mock.MagicMock()
        probe.__enter__.return_value.connect_ex.return_value = 0
        with (
            mock.patch(
                "URDF_Exporter.standalone.server.socket.socket",
                return_value=probe,
            ),
            mock.patch(
                "URDF_Exporter.standalone.server._petasos_server_is_healthy",
                return_value=False,
            ),
        ):
            with self.assertRaises(RuntimeError):
                run()

    def test_import_preserves_joint_and_builds_a1_tree(self):
        payload = self.import_demo()
        self.assertEqual(payload["report"]["parts"], 2)
        self.assertEqual(payload["report"]["joints"], 1)
        tree = self.client.get("/data").get_json()
        self.assertEqual(tree["name"], "base")
        self.assertEqual(tree["children"][0]["joint_name"], "base_to_arm")
        self.assertEqual(tree["children"][0]["joint_type"], "revolute")
        self.assertEqual(
            tree["children"][0]["joint_info"]["provenance"],
            "test_cad_joint",
        )
        self.assertEqual(tree["children"][0]["link_group"]["name"], "arm")
        self.assertEqual(tree["_preview_units_per_meter"], 1000.0)
        self.assertEqual(tree["_preview_up_axis"], "z")

    def test_preview_workspace_can_be_saved_and_reloaded_without_export(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        tree["name"] = "edited_base_link"
        tree["_patcher_view"] = {"x": 81, "y": 42, "zoom": 1.1}

        saved = self.client.post(
            "/workspace/save",
            json={
                "tree": tree,
                "editor_settings": {
                    "fix_to_world": False,
                    "export_mode": "moveit",
                },
                "save_name": "조인트 수정안 A",
            },
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        self.assertEqual(saved.get_json()["status"], "saved")
        self.assertEqual(saved.get_json()["save_name"], "조인트 수정안 A")
        self.assertEqual(
            saved.get_json()["active_workspace_name"],
            "조인트 수정안 A",
        )

        current_tree = self.client.get("/data").get_json()
        current_tree["name"] = "newer_autosave"
        autosaved = self.client.post(
            "/workspace/save",
            json={"tree": current_tree, "editor_settings": {}},
        )
        self.assertEqual(autosaved.status_code, 200)

        listed = self.client.get("/workspace/list")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["name"] for item in listed.get_json()["items"]],
            ["조인트 수정안 A"],
        )

        loaded = self.client.post(
            "/workspace/reload",
            json={"save_name": "조인트 수정안 A"},
        )
        self.assertEqual(loaded.status_code, 200, loaded.get_data(as_text=True))
        restored = loaded.get_json()["tree"]
        self.assertEqual(restored["name"], "edited_base_link")
        self.assertEqual(restored["_patcher_view"]["zoom"], 1.1)
        self.assertFalse(restored["_editor_settings"]["fix_to_world"])
        self.assertEqual(restored["_editor_settings"]["export_mode"], "moveit")
        self.assertEqual(restored["_active_workspace_name"], "조인트 수정안 A")

        restored["name"] = "continued_named_workspace"
        continued = self.client.post(
            "/workspace/save",
            json={
                "tree": restored,
                "editor_settings": restored["_editor_settings"],
                "save_name": restored["_active_workspace_name"],
            },
        )
        self.assertEqual(continued.status_code, 200)
        self.assertEqual(
            [item["name"] for item in self.client.get("/workspace/list").get_json()["items"]],
            ["조인트 수정안 A"],
        )
        loaded_again = self.client.post(
            "/workspace/reload",
            json={"save_name": "조인트 수정안 A"},
        )
        self.assertEqual(loaded_again.status_code, 200)
        self.assertEqual(
            loaded_again.get_json()["tree"]["name"],
            "continued_named_workspace",
        )

        reopened_store = ProjectStore(Path(self.temp_dir.name) / "projects")
        self.assertEqual(reopened_store.tree()["name"], "continued_named_workspace")
        self.assertEqual(
            reopened_store.tree()["_active_workspace_name"],
            "조인트 수정안 A",
        )

    def test_step_xde_assembly_is_split_into_positioned_part_candidates(self):
        response = self.client.post(
            "/import",
            data={
                "project_name": "Universal STEP",
                "files": [
                    (io.BytesIO(self.step_assembly_bytes()), "robot.step"),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        report = response.get_json()["report"]
        self.assertEqual(report["parts"], 2)
        self.assertEqual(report["import_mode"], "step_xde_position_only")
        self.assertIn("OpenCascade XDE", report["source_application"])

        tree = self.client.get("/data").get_json()
        transforms = list(tree["_preview_transforms"].values())
        translations = {
            (
                round(transform[12], 3),
                round(transform[13], 3),
                round(transform[14], 3),
            )
            for transform in transforms
        }
        self.assertEqual(translations, {(0.0, 0.0, 0.0), (125.0, 0.0, 50.0)})
        self.assertGreaterEqual(report["recovered_connections"], 1)
        self.assertTrue(tree["_cad_snap_features"])

    def test_flattened_step_reports_that_part_structure_was_lost(self):
        response = self.client.post(
            "/import",
            data={
                "project_name": "Flattened STEP",
                "files": [
                    (
                        io.BytesIO(self.step_assembly_bytes(single_solid=True)),
                        "flattened.step",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        report = response.get_json()["report"]
        self.assertEqual(report["parts"], 1)
        warning_codes = {warning["code"] for warning in report["warnings"]}
        self.assertIn("flattened_step", warning_codes)

    def test_import_dialog_can_list_and_reload_saved_work_from_all_projects(self):
        self.import_demo()
        first_project_id = self.store.project_dir.name
        first_tree = self.client.get("/data").get_json()
        first_tree["name"] = "first_saved_root"
        saved = self.client.post(
            "/workspace/save",
            json={"tree": first_tree, "save_name": "첫 작업"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))

        imported = self.client.post(
            "/import",
            data={
                "project_name": "Second Robot",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (
                        io.BytesIO(json.dumps(self.manifest()).encode("utf-8")),
                        "second-arm.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(imported.status_code, 200, imported.get_data(as_text=True))
        second_project_id = self.store.project_dir.name
        second_tree = self.client.get("/data").get_json()
        second_tree["name"] = "second_saved_root"
        saved = self.client.post(
            "/workspace/save",
            json={"tree": second_tree, "save_name": "두번째 작업"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))

        listed = self.client.get("/workspace/list?all_projects=1")
        self.assertEqual(listed.status_code, 200)
        items = listed.get_json()["items"]
        self.assertEqual(
            {(item["project_id"], item["name"]) for item in items},
            {
                (first_project_id, "첫 작업"),
                (second_project_id, "두번째 작업"),
            },
        )

        loaded = self.client.post(
            "/workspace/reload",
            json={"project_id": first_project_id, "save_name": "첫 작업"},
        )
        self.assertEqual(loaded.status_code, 200, loaded.get_data(as_text=True))
        self.assertEqual(loaded.get_json()["tree"]["name"], "first_saved_root")
        self.assertEqual(self.store.project_dir.name, first_project_id)
        self.assertEqual(self.client.get("/data").get_json()["name"], "first_saved_root")

    def test_branching_links_export_as_two_children_of_one_parent(self):
        manifest = self.manifest()
        manifest["assembly"]["name"] = "branched_robot"
        manifest["parts"].append(
            {
                "id": "camera",
                "name": "camera",
                "geometry": "camera.stl",
                "transform": {"position": [40, 0, 40], "rotation": [0, 0, 0]},
                "physical": {
                    "mass": 0.2,
                    "center_of_mass": [0, 0, 10],
                    "inertia": [0.001, 0.001, 0.001, 0, 0, 0],
                },
            }
        )
        manifest["joints"].append(
            {
                "name": "base_to_camera",
                "parent": "base",
                "child": "camera",
                "type": "fixed",
                "origin": {"xyz": [40, 0, 40], "rpy": [0, 0, 0]},
                "axis": [0, 0, 1],
                "provenance": "test_cad_joint",
            }
        )
        response = self.client.post(
            "/import",
            data={
                "project_name": "Branched Robot",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (io.BytesIO(self.stl_bytes([35, 35, 25])), "camera.stl"),
                    (
                        io.BytesIO(json.dumps(manifest).encode("utf-8")),
                        "branched-robot.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        tree = self.client.get("/data").get_json()
        self.assertEqual(len(tree["children"]), 2)

        saved = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        xacro = ElementTree.parse(
            Path(saved.get_json()["save_dir"]) / "urdf" / "branched_robot.xacro"
        )
        joints = [
            joint
            for joint in xacro.getroot().findall("joint")
            if joint.get("name") != "world_joint"
        ]
        self.assertEqual(len(joints), 2)
        self.assertEqual(
            len({joint.find("parent").get("link") for joint in joints}),
            1,
        )
        self.assertEqual(
            len({joint.find("child").get("link") for joint in joints}),
            2,
        )

    def test_inventor_fixed_joint_becomes_inactive_group_candidate(self):
        manifest = self.manifest()
        manifest["source"] = {"application": "Autodesk Inventor"}
        manifest["joints"][0]["type"] = "fixed"
        manifest["joints"][0]["provenance"] = "inventor_assembly_joint"
        response = self.client.post(
            "/import",
            data={
                "project_name": "Inventor Fixed",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (
                        io.BytesIO(json.dumps(manifest).encode("utf-8")),
                        "inventor-fixed.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        report = response.get_json()["report"]
        self.assertEqual(report["import_mode"], "inventor_safe")
        self.assertEqual(report["active_joints"], 0)
        self.assertEqual(report["rigid_group_candidates"], 1)
        tree = self.client.get("/data").get_json()
        self.assertEqual(
            tree["children"][0]["joint_info"]["provenance"],
            "inventor_fixed_group_candidate",
        )
        self.assertEqual(tree["_preview_transforms"]["arm"][14], 150.0)

    def test_non_inventor_fixed_joint_remains_active(self):
        manifest = self.manifest()
        manifest["joints"][0]["type"] = "fixed"
        response = self.client.post(
            "/import",
            data={
                "project_name": "Neutral Fixed",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (
                        io.BytesIO(json.dumps(manifest).encode("utf-8")),
                        "neutral-fixed.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        report = response.get_json()["report"]
        self.assertEqual(report["import_mode"], "standard")
        self.assertEqual(report["active_joints"], 1)
        tree = self.client.get("/data").get_json()
        self.assertEqual(
            tree["children"][0]["joint_info"]["provenance"],
            "test_cad_joint",
        )

    def test_inventor_group_candidate_merges_without_exporting_fake_joint(self):
        manifest = self.manifest()
        manifest["source"] = {"application": "Autodesk Inventor"}
        manifest["joints"][0]["type"] = "fixed"
        manifest["joints"][0]["provenance"] = "inventor_assembly_joint"
        response = self.client.post(
            "/import",
            data={
                "project_name": "Inventor Merged",
                "files": [
                    (io.BytesIO(self.stl_bytes([100, 100, 40])), "base.stl"),
                    (io.BytesIO(self.stl_bytes([30, 30, 300])), "arm.stl"),
                    (
                        io.BytesIO(json.dumps(manifest).encode("utf-8")),
                        "inventor-merged.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        tree = self.client.get("/data").get_json()
        candidate = tree["children"].pop(0)
        tree["components"].extend(candidate["link_group"]["components"])
        tree["is_finalized"] = True
        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["link_count"], 1)
        self.assertEqual(payload["joint_count"], 0)
        xacro = Path(payload["save_dir"]) / "urdf" / "inventor_merged.xacro"
        xacro_tree = ElementTree.parse(xacro)
        joints = xacro_tree.getroot().findall("joint")
        self.assertEqual([joint.get("name") for joint in joints], ["world_joint"])
        links = xacro_tree.getroot().findall("link")
        robot_link = next(link for link in links if link.get("name") != "world")
        self.assertEqual(len(robot_link.findall("visual")), 2)
        self.assertEqual(len(robot_link.findall("collision")), 1)
        collision_mesh = robot_link.find("collision/geometry/mesh")
        self.assertTrue(collision_mesh.get("filename").endswith("_collision.stl"))
        self.assertTrue(
            os.path.isfile(
                Path(payload["save_dir"])
                / "meshes"
                / Path(collision_mesh.get("filename")).name
            )
        )

    def test_import_to_ros2_zip_export(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        response = self.client.post(
            "/save",
            json={
                "tree": tree,
                "fix_to_world": True,
                "include_moveit": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["include_moveit"])
        self.assertIsNotNone(payload["bundle_dir"])
        save_dir = payload["save_dir"]
        xacro = os.path.join(save_dir, "urdf", "simple_arm.xacro")
        self.assertTrue(os.path.isfile(xacro))
        xacro_text = Path(xacro).read_text(encoding="utf-8")
        self.assertIn(
            '<xacro:arg name="use_gazebo" default="false"',
            xacro_text,
        )
        self.assertTrue(os.path.isfile(os.path.join(save_dir, "meshes", "base.stl")))
        self.assertTrue(os.path.isfile(os.path.join(save_dir, "meshes", "arm.stl")))
        self.assertTrue(
            os.path.isfile(os.path.join(save_dir, "meshes", "base_link_collision.stl"))
        )
        self.assertTrue(
            os.path.isfile(os.path.join(save_dir, "meshes", "arm_collision.stl"))
        )
        self.assertTrue(os.path.isfile(os.path.join(save_dir, "analysis", "assembly.json")))
        readiness_path = Path(save_dir, "analysis", "moveit_readiness.json")
        self.assertTrue(readiness_path.is_file())
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["controlled_joint_count"], 1)
        self.assertEqual(payload["moveit_readiness"]["status"], "ready")
        sensors_3d = (
            Path(payload["bundle_dir"])
            / "src"
            / "simple_arm_moveit_config"
            / "config"
            / "sensors_3d.yaml"
        ).read_text(encoding="utf-8")
        self.assertEqual(sensors_3d, "sensors: []\n")
        self.assertFalse(os.path.exists(os.path.join(save_dir, "run_rviz.sh")))
        self.assertFalse(os.path.exists(os.path.join(save_dir, "run_rviz.bat")))
        self.assertFalse(os.path.exists(os.path.join(save_dir, "run_rviz_wsl.bat")))
        self.assertFalse(os.path.exists(os.path.join(save_dir, "RVIZ_실행방법.txt")))
        launch_path = os.path.join(save_dir, "launch", "display.launch.py")
        launch_text = Path(launch_path).read_text(encoding="utf-8")
        compile(launch_text, launch_path, "exec")
        self.assertIn("import xacro", launch_text)
        self.assertIn("xacro.process_file(xacro_file)", launch_text)
        self.assertIn("robot_description_config.toxml()", launch_text)
        self.assertIn("DeclareLaunchArgument", launch_text)
        self.assertIn('LaunchConfiguration("gui")', launch_text)
        self.assertIn("UnlessCondition(show_gui)", launch_text)
        self.assertIn('package="joint_state_publisher"', launch_text)
        self.assertIn("IfCondition(show_gui)", launch_text)
        self.assertNotIn("from launch.substitutions import Command", launch_text)
        rviz_text = Path(save_dir, "config", "display.rviz").read_text(encoding="utf-8")
        self.assertIn("Fixed Frame: world", rviz_text)
        self.assertIn("Class: rviz_default_plugins/Grid", rviz_text)
        self.assertIn("Class: rviz_default_plugins/Orbit", rviz_text)
        self.assertIn("Distance: 0.85", rviz_text)
        for tool_class in (
            "Interact",
            "MoveCamera",
            "Select",
            "FocusCamera",
            "Measure",
            "SetInitialPose",
            "SetGoal",
            "PublishPoint",
        ):
            self.assertIn(
                f"Class: rviz_default_plugins/{tool_class}",
                rviz_text,
            )
        self.assertIn("Value: /initialpose", rviz_text)
        self.assertIn("Value: /goal_pose", rviz_text)
        self.assertIn("Value: /clicked_point", rviz_text)
        xacro_tree = ElementTree.parse(xacro)
        world_joint = next(
            joint
            for joint in xacro_tree.getroot().findall("joint")
            if joint.get("name") == "world_joint"
        )
        self.assertEqual(
            world_joint.find("origin").get("rpy"),
            "0.0 0.0 0.0",
        )
        robot_links = [
            link
            for link in xacro_tree.getroot().findall("link")
            if link.get("name") != "world"
        ]
        self.assertTrue(all(len(link.findall("collision")) == 1 for link in robot_links))
        self.assertTrue(
            all(
                link.find("collision/geometry/mesh")
                .get("filename")
                .endswith("_collision.stl")
                for link in robot_links
            )
        )
        transmission_path = Path(save_dir, "urdf", "simple_arm.trans")
        transmission_text = transmission_path.read_text(encoding="utf-8")
        self.assertIn("<ros2_control", transmission_text)
        self.assertIn("mock_components/GenericSystem", transmission_text)
        self.assertIn("gazebo_ros2_control/GazeboSystem", transmission_text)
        self.assertIn('<xacro:if value="$(arg use_gazebo)">', transmission_text)
        gazebo_xacro_text = Path(
            save_dir,
            "urdf",
            "simple_arm.gazebo",
        ).read_text(encoding="utf-8")
        self.assertIn("libgazebo_ros2_control.so", gazebo_xacro_text)
        self.assertIn("gazebo_controllers.yaml", gazebo_xacro_text)
        self.assertIn('<command_interface name="position">', transmission_text)
        self.assertIn('<state_interface name="position"', transmission_text)
        self.assertIn('<state_interface name="velocity"', transmission_text)
        self.assertIn('<param name="initial_value">0.0</param>', transmission_text)
        self.assertNotIn("<transmission", transmission_text)
        self.assertNotIn("SimpleTransmission", transmission_text)
        self.assertNotIn("hardwareInterface", transmission_text)
        self.assertFalse(
            list(Path(save_dir, "urdf").glob("*.moveit.xacro"))
        )
        robot_name, assistant_relative = _robot_details(Path(save_dir))
        self.assertEqual(robot_name, "simple_arm")
        self.assertEqual(
            assistant_relative.as_posix(),
            "urdf/simple_arm.xacro",
        )
        package_text = Path(save_dir, "package.xml").read_text(encoding="utf-8")
        self.assertIn("<exec_depend>ros2_control</exec_depend>", package_text)
        self.assertIn("<exec_depend>ros2_controllers</exec_depend>", package_text)
        self.assertIn("<exec_depend>gazebo_ros</exec_depend>", package_text)
        self.assertIn("<exec_depend>gazebo_ros2_control</exec_depend>", package_text)
        gazebo_controller_text = Path(
            save_dir,
            "config",
            "gazebo_controllers.yaml",
        ).read_text(encoding="utf-8")
        self.assertIn("joint_state_broadcaster:", gazebo_controller_text)
        self.assertIn("arm_controller:", gazebo_controller_text)
        self.assertIn("command_interfaces:\n      - position", gazebo_controller_text)
        self.assertIn("      - joint_1", gazebo_controller_text)
        gazebo_launch_path = Path(save_dir, "launch", "gazebo.launch.py")
        gazebo_launch_text = gazebo_launch_path.read_text(encoding="utf-8")
        compile(gazebo_launch_text, str(gazebo_launch_path), "exec")
        self.assertIn('mappings={"use_gazebo": "true"}', gazebo_launch_text)
        self.assertIn('executable="spawn_entity.py"', gazebo_launch_text)
        self.assertIn("OnProcessExit", gazebo_launch_text)
        self.assertIn('"arm_controller"', gazebo_launch_text)
        bundle_dir = Path(save_dir).parent.parent
        self.assertEqual(bundle_dir.name, "ros_ws")
        moveit_dir = bundle_dir / "src" / "simple_arm_moveit_config"
        ros2_controller_text = (
            moveit_dir / "config" / "ros2_controllers.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("command_interfaces:\n      - position", ros2_controller_text)
        self.assertNotIn("      - effort", ros2_controller_text)
        self.assertIn(
            "--fix",
            (bundle_dir / "normalize_moveit.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "-c src/simple_arm_moveit_config",
            (bundle_dir / "open_moveit_assistant.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            '.petasos_runtime',
            (bundle_dir / "open_moveit_assistant.sh").read_text(encoding="utf-8"),
        )
        setup_assistant_text = (
            moveit_dir / ".setup_assistant"
        ).read_text(encoding="utf-8")
        self.assertIn("package_settings:", setup_assistant_text)
        self.assertIn("author_name: Petasos", setup_assistant_text)
        self.assertIn("author_email: contact@petasos.dev", setup_assistant_text)
        self.assertTrue((bundle_dir / "run_moveit_demo.sh").is_file())
        download = self.client.get("/download")
        self.assertEqual(download.status_code, 410)

        runner = self.app.config["PETASOS_WSL_RVIZ"]
        with mock.patch.object(
            runner,
            "start",
            return_value={"status": "preparing", "message": "building", "output": []},
        ) as start:
            launch = self.client.post("/rviz/wsl")
        self.assertEqual(launch.status_code, 200)
        start.assert_called_once_with(Path(save_dir))

    def test_basic_export_omits_moveit_bundle_and_blocks_moveit_actions(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        response = self.client.post(
            "/save",
            json={
                "tree": tree,
                "fix_to_world": True,
                "include_moveit": False,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        save_dir = Path(payload["save_dir"])
        self.assertFalse(payload["include_moveit"])
        self.assertIsNone(payload["bundle_dir"])
        self.assertEqual(save_dir.name, "simple_arm_description")
        self.assertTrue((save_dir / "urdf" / "simple_arm.xacro").is_file())
        self.assertFalse(
            (save_dir.parent / "simple_arm_moveit_config").exists()
        )
        self.assertFalse((save_dir / "open_moveit_assistant.sh").exists())
        self.assertFalse(save_dir.with_suffix(".zip").exists())

        assistant = self.client.post("/moveit/wsl/assistant")
        demo = self.client.post("/moveit/wsl/demo")
        self.assertEqual(assistant.status_code, 409)
        self.assertEqual(demo.status_code, 409)

    def test_wsl_rviz_requires_an_export(self):
        response = self.client.post("/rviz/wsl")
        self.assertEqual(response.status_code, 404)
        runner = self.app.config["PETASOS_WSL_RVIZ"]
        with mock.patch.object(
            runner,
            "stop",
            return_value={"status": "stopped", "message": "stopped", "output": []},
        ) as stop:
            stopped = self.client.post("/rviz/wsl/stop")
        self.assertEqual(stopped.status_code, 200)
        stop.assert_called_once_with()

    def test_visual_revolute_limits_are_written_to_urdf_in_radians(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        joint = tree["children"][0]
        joint["joint_type"] = "revolute"
        joint["joint_info"]["type"] = "revolute"
        joint["joint_info"]["lower_limit"] = -math.pi / 3.0
        joint["joint_info"]["upper_limit"] = math.pi / 4.0
        joint["joint_info"]["_manual_limit_lower_set"] = True
        joint["joint_info"]["_manual_limit_upper_set"] = True
        joint["joint_info"]["provenance"] = "user_visual_joint_limit"

        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        save_dir = Path(response.get_json()["save_dir"])
        xacro = ElementTree.parse(save_dir / "urdf" / "simple_arm.xacro")
        exported = next(
            item for item in xacro.getroot().findall("joint")
            if item.get("name") == "joint_1"
        )
        self.assertEqual(exported.get("type"), "revolute")
        limit = exported.find("limit")
        self.assertIsNotNone(limit)
        self.assertAlmostEqual(float(limit.get("lower")), -math.pi / 3.0)
        self.assertAlmostEqual(float(limit.get("upper")), math.pi / 4.0)

    def test_ros2_control_initial_position_is_inside_negative_only_limit(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        joint = tree["children"][0]
        joint["joint_type"] = "revolute"
        joint["joint_info"]["type"] = "revolute"
        joint["joint_info"]["lower_limit"] = -3.0
        joint["joint_info"]["upper_limit"] = -1.0
        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        transmission = ElementTree.parse(
            Path(response.get_json()["save_dir"])
            / "urdf"
            / "simple_arm.trans"
        ).getroot()
        control_joint = transmission.find("ros2_control/joint")
        initial = control_joint.find(
            "state_interface[@name='position']/param[@name='initial_value']"
        )
        self.assertIsNotNone(initial)
        self.assertEqual(float(initial.text), -2.0)

    def test_export_rejects_lower_limit_equal_to_or_above_upper(self):
        base = {
            "type": "revolute",
            "lower_limit": 1.0,
            "upper_limit": 1.0,
        }
        with self.assertRaisesRegex(ValueError, "lower must be smaller than upper"):
            _validate_joint_limits({"joint_equal": base})

        reversed_range = dict(base, lower_limit=2.0, upper_limit=-1.0)
        with self.assertRaisesRegex(ValueError, "joint_reversed"):
            _validate_joint_limits({"joint_reversed": reversed_range})

        _validate_joint_limits({
            "joint_valid": dict(base, lower_limit=-1.0, upper_limit=2.0),
            "joint_continuous": {
                "type": "continuous",
                "lower_limit": 5.0,
                "upper_limit": -5.0,
            },
        })

    def test_whole_number_joint_limits_are_serialized_as_reals(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        joint = tree["children"][0]
        joint["joint_type"] = "revolute"
        joint["joint_info"]["type"] = "revolute"
        joint["joint_info"]["lower_limit"] = -1
        joint["joint_info"]["upper_limit"] = 2

        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        save_dir = Path(response.get_json()["save_dir"])

        xacro = ElementTree.parse(save_dir / "urdf" / "simple_arm.xacro")
        exported_joint = next(
            item for item in xacro.getroot().findall("joint")
            if item.get("name") == "joint_1"
        )
        limit = exported_joint.find("limit")
        self.assertEqual(limit.get("lower"), "-1.0")
        self.assertEqual(limit.get("upper"), "2.0")
        self.assertEqual(limit.get("effort"), "100.0")
        self.assertEqual(limit.get("velocity"), "1.0")

        control = ElementTree.parse(
            save_dir / "urdf" / "simple_arm.trans"
        ).getroot().find("ros2_control")
        command = control.find("joint/command_interface")
        params = {item.get("name"): item.text for item in command.findall("param")}
        self.assertEqual(params, {"min": "-1.0", "max": "2.0"})

    def test_continuous_joint_gets_required_effort_and_velocity_limits(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        joint = tree["children"][0]
        joint["joint_type"] = "continuous"
        joint["joint_info"]["type"] = "continuous"
        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        exported = ElementTree.parse(
            Path(response.get_json()["save_dir"])
            / "urdf"
            / "simple_arm.xacro"
        ).getroot()
        movable = next(
            item
            for item in exported.findall("joint")
            if item.get("name") == "joint_1"
        )
        limit = movable.find("limit")
        self.assertIsNotNone(limit)
        self.assertIsNone(limit.get("lower"))
        self.assertIsNone(limit.get("upper"))
        self.assertEqual(limit.get("effort"), "100.0")
        self.assertEqual(limit.get("velocity"), "1.0")

    def test_open_export_folder_opens_the_latest_package_directory(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        saved = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        save_dir = Path(saved.get_json()["save_dir"])

        with mock.patch(
            "URDF_Exporter.standalone.server._open_folder"
        ) as open_folder:
            response = self.client.post("/open-export-folder")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(Path(response.get_json()["path"]), save_dir)
        open_folder.assert_called_once_with(save_dir)

    def test_windows_export_path_is_mapped_to_wsl_mount(self):
        source = Path(r"X:\portable\robot_description")
        self.assertEqual(
            _windows_path_to_wsl(source),
            "/mnt/x/portable/robot_description",
        )

    def test_rviz_reports_missing_humble_before_building(self):
        runner = WslRvizRunner()
        missing = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="missing"
        )
        with mock.patch(
            "URDF_Exporter.standalone.server.subprocess.run",
            return_value=missing,
        ):
            with self.assertRaisesRegex(RuntimeError, "setup_petasos.cmd"):
                runner._ensure_ros_ready()

    def test_rviz_preflight_sources_humble_before_finding_ros2(self):
        runner = WslRvizRunner()
        ready = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with mock.patch(
            "URDF_Exporter.standalone.server.subprocess.run",
            return_value=ready,
        ) as run:
            runner._ensure_ros_ready()
        command = run.call_args.args[0][-1]
        self.assertIn("source /opt/ros/humble/setup.bash", command)
        self.assertLess(command.index("source "), command.index("command -v ros2"))

    def test_rviz_streams_package_without_windows_mount_path(self):
        server_text = Path("URDF_Exporter/standalone/server.py").read_text(
            encoding="utf-8"
        )
        start_text = server_text.split("    def start(self, package_dir: Path)", 1)[1]
        start_text = start_text.split("    def stop(self)", 1)[0]
        self.assertIn("tar -xpf - -C", start_text)
        self.assertIn("target=self._stream_package", start_text)
        self.assertIn("self._stage_wsl_script(script, package_name)", start_text)
        self.assertIn('"bash", linux_script', start_text)
        self.assertNotIn("_windows_path_to_wsl(package_dir)", start_text)

    def test_rviz_stages_script_as_base64_without_windows_path(self):
        runner = WslRvizRunner()
        ready = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with mock.patch(
            "URDF_Exporter.standalone.server.subprocess.run",
            return_value=ready,
        ) as run:
            path = runner._stage_wsl_script("echo $workspace", "robot_description")
        self.assertEqual(path, "/tmp/petasos-rviz-robot_description.sh")
        command = run.call_args.args[0][-1]
        self.assertIn("base64 -d", command)
        self.assertNotIn("$workspace", command)

    def test_rviz_uses_base_link_when_world_fix_is_disabled(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": False},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        save_dir = Path(response.get_json()["save_dir"])
        rviz_text = (save_dir / "config" / "display.rviz").read_text(encoding="utf-8")
        self.assertIn("Fixed Frame: base_link", rviz_text)
        xacro = ElementTree.parse(save_dir / "urdf" / "simple_arm.xacro")
        self.assertNotIn(
            "world_joint",
            [joint.get("name") for joint in xacro.getroot().findall("joint")],
        )

    def test_brep_is_meshed_and_given_si_physical_values(self):
        load_ocp()
        from OCP import BRepPrimAPI, BRepTools

        brep_path = os.path.join(self.temp_dir.name, "cad_box.brep")
        shape = BRepPrimAPI.BRepPrimAPI_MakeBox(100, 50, 20).Shape()
        self.assertTrue(BRepTools.BRepTools.Write_s(shape, brep_path))
        with open(brep_path, "rb") as stream:
            brep_bytes = stream.read()
        response = self.client.post(
            "/import",
            data={
                "project_name": "CAD Box",
                "files": [(io.BytesIO(brep_bytes), "cad_box.brep")],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        state = self.store.state
        self.assertIsNotNone(state)
        physical = state["inertial"]["cad_box"]
        self.assertAlmostEqual(physical["mass"], 0.1, places=5)
        self.assertGreater(physical["inertia"][0], 0)
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.store.project_dir, "meshes", "cad_box.stl")
            )
        )
        cad_snaps = state["tree"]["_cad_snap_features"]["cad_box"]
        self.assertEqual(cad_snaps["source"], "opencascade")
        self.assertGreater(len(cad_snaps["features"]), 0)
        self.assertIn(
            "planar_face_center",
            {feature["type"] for feature in cad_snaps["features"]},
        )

    def test_cad_companion_geometry_drives_exact_circle_and_axis_snaps(self):
        load_ocp()
        from OCP import BRepPrimAPI, BRepTools

        brep_path = Path(self.temp_dir.name) / "cylinder.brep"
        shape = BRepPrimAPI.BRepPrimAPI_MakeCylinder(25, 80).Shape()
        self.assertTrue(BRepTools.BRepTools.Write_s(shape, str(brep_path)))
        manifest = {
            "format": "petasos-assembly",
            "version": "1.0",
            "source": {"application": "Autodesk Inventor"},
            "assembly": {
                "name": "cad_snap",
                "units": "mm",
                "angle_units": "rad",
                "up_axis": "y",
            },
            "parts": [
                {
                    "id": "cylinder",
                    "name": "cylinder",
                    "geometry": "cylinder.stl",
                    "cad_geometry": "cylinder.brep",
                    "physical": {
                        "mass": 1.0,
                        "center_of_mass": [0, 0, 40],
                        "inertia": [0.1, 0.1, 0.1, 0, 0, 0],
                    },
                }
            ],
            "joints": [],
        }
        with open(brep_path, "rb") as stream:
            brep_bytes = stream.read()
        cylinder_mesh = trimesh.creation.cylinder(radius=25, height=80)
        cylinder_mesh.apply_translation([0, 0, 40])
        response = self.client.post(
            "/import",
            data={
                "project_name": "CAD Snap",
                "files": [
                    (io.BytesIO(cylinder_mesh.export(file_type="stl")), "cylinder.stl"),
                    (io.BytesIO(brep_bytes), "cylinder.brep"),
                    (
                        io.BytesIO(json.dumps(manifest).encode("utf-8")),
                        "cylinder.petasos.json",
                    ),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        tree = self.client.get("/data").get_json()
        record = tree["_cad_snap_features"]["cylinder"]
        feature_types = {feature["type"] for feature in record["features"]}
        self.assertIn("circle_center", feature_types)
        self.assertIn("cylinder_axis", feature_types)
        circle = next(
            feature for feature in record["features"]
            if feature["type"] == "circle_center"
        )
        self.assertAlmostEqual(circle["radius"], 25.0, places=2)
        self.assertEqual(circle["source"], "opencascade")
        self.assertEqual(tree["_import_report"]["cad_snap_parts"], 1)

    def test_inventor_matrix_uses_centimeters_and_relative_pose(self):
        parent = [
            [1.0, 0.0, 0.0, 2.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        child = [
            [1.0, 0.0, 0.0, 7.0],
            [0.0, 1.0, 0.0, 3.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        self.assertEqual(matrix_transform(child)["position"], [70.0, 30.0, 0.0])
        relative = relative_transform(parent, child)
        self.assertEqual(relative["position"], [50.0, 30.0, 0.0])
        self.assertEqual(relative["rotation"], [0.0, 0.0, 0.0])

    def test_active_inventor_part_finds_its_open_assembly(self):
        class Collection:
            def __init__(self, items):
                self.items = items
                self.Count = len(items)

            def Item(self, index):
                return self.items[index - 1]

        class Document:
            def __init__(self, name, document_type, referring=None):
                self.FullFileName = name
                self.DisplayName = Path(name).name
                self.DocumentType = document_type
                self.ReferencingDocuments = Collection(referring or [])

        assembly = Document("C:/robot/robot.iam", 12291)
        part = Document("C:/robot/arm.ipt", 12290, [assembly])
        app = type("InventorApp", (), {
            "ActiveDocument": part,
            "Documents": Collection([part, assembly]),
        })()

        self.assertIs(_select_open_assembly_document(app), assembly)

    def test_cad_up_axes_map_to_ros_z_up(self):
        self.assertEqual(_root_orientation_rpy("z"), [0.0, 0.0, 0.0])
        self.assertEqual(
            _root_orientation_rpy("y"),
            [1.5707963267948966, 0.0, 0.0],
        )
        self.assertEqual(
            _root_orientation_rpy("x"),
            [0.0, -1.5707963267948966, 0.0],
        )
        self.assertEqual(
            _root_orientation_rpy("y", [0.1, 0.2, 0.3]),
            [0.1, 0.2, 0.3],
        )
        self.assertEqual(_root_origin_xyz([0.0, 0.0, 0.125]), [0.0, 0.0, 0.125])
        self.assertEqual(_root_origin_xyz(["bad", 0, 0]), [0.0, 0.0, 0.0])

    def test_root_link_pose_includes_root_component_cad_transform(self):
        tree = {
            "components": ["root_part"],
            "_preview_up_axis": "z",
            "_preview_root_rpy": [0.0, 0.0, 1.5707963267948966],
            "_preview_root_xyz": [10.0, 20.0, 30.0],
        }
        state = {
            "visual_transforms": {
                "root_part": [
                    1.0, 0.0, 0.0, 1.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    0.0, 0.0, 0.0, 1.0,
                ],
            },
        }

        xyz, rpy = _root_link_pose(state, tree)

        for actual, expected in zip(xyz, [10.0, 21.0, 30.0]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(rpy, [0.0, 0.0, 1.5707963267948966]):
            self.assertAlmostEqual(actual, expected)

    def test_custom_ground_face_transform_is_exported_and_persisted(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        tree["_preview_root_rpy"] = [0.1, -0.2, 0.3]
        tree["_preview_root_xyz"] = [0.0, 0.0, 0.125]
        tree["_preview_root_quaternion"] = [0.0, 0.0, 0.0, 1.0]
        tree["_preview_root_position"] = [0.0, 125.0, 0.0]
        tree["_preview_ground_face"] = {
            "component": "base",
            "snap_mode": "connected_planar_face_centroid",
            "center_local": [50.0, 50.0, 0.0],
            "alignment_mode": "normal_center_and_boundary_axis",
            "target_axis": "+X",
            "world_origin": [0.0, 0.0, 0.0],
        }

        response = self.client.post(
            "/save",
            json={"tree": tree, "fix_to_world": True},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        xacro = Path(response.get_json()["save_dir"]) / "urdf" / "simple_arm.xacro"
        root = ElementTree.parse(xacro).getroot()
        world_joint = next(
            joint for joint in root.findall("joint")
            if joint.get("name") == "world_joint"
        )
        origin = world_joint.find("origin")
        # The saved Three.js quaternion is authoritative. An identity viewer
        # quaternion maps Y-up to ROS Z-up with a +90 degree X rotation.
        self.assertEqual(origin.get("rpy"), "1.570796326795 0.0 0.0")
        self.assertEqual(origin.get("xyz"), "0.0 0.0 0.125")

        persisted = json.loads(
            (self.store.project_dir / "project_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(persisted["tree"]["_preview_ground_face"]["component"], "base")
        self.assertEqual(
            persisted["tree"]["_preview_ground_face"]["snap_mode"],
            "connected_planar_face_centroid",
        )
        self.assertEqual(
            persisted["tree"]["_preview_ground_face"]["world_origin"],
            [0.0, 0.0, 0.0],
        )
        self.assertEqual(
            persisted["tree"]["_preview_ground_face"]["target_axis"],
            "+X",
        )

    @mock.patch("URDF_Exporter.standalone.importers.prepare_native_assembly")
    def test_iam_project_folder_runs_native_adapter(self, prepare_native):
        def fake_adapter(source_dir, project_name):
            source = Path(source_dir)
            self.assertTrue((source / "robot.iam").is_file())
            (source / "base.stl").write_bytes(self.stl_bytes([100, 100, 30]))
            (source / "arm.stl").write_bytes(self.stl_bytes([25, 25, 200]))
            manifest = self.manifest()
            manifest["source"] = {
                "application": "Autodesk Inventor",
                "document": "robot.iam",
                "adapter": "petasos-inventor-com",
            }
            path = source / "inventor-import.petasos.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return path

        prepare_native.side_effect = fake_adapter
        response = self.client.post(
            "/import",
            data={
                "project_name": "Inventor Robot",
                "relative_files": [
                    (io.BytesIO(b"fake iam"), "inventor_project/robot.iam"),
                    (io.BytesIO(b"fake ipt"), "inventor_project/base.ipt"),
                ],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["report"]["source_application"], "Autodesk Inventor")
        self.assertEqual(payload["report"]["parts"], 2)
        prepare_native.assert_called_once()

    @mock.patch(
        "URDF_Exporter.standalone.server.convert_active_inventor"
    )
    def test_current_open_inventor_route(self, convert_active):
        convert_active.side_effect = lambda output_dir, project_name: (
            self.write_fake_inventor_exchange(
                output_dir,
                "petasos-inventor-active",
            )
        )
        response = self.client.post(
            "/import/inventor-active",
            json={"project_name": "Active Robot"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["status"], "imported")
        self.assertEqual(payload["report"]["source_application"], "Autodesk Inventor")
        self.assertEqual(payload["report"]["parts"], 2)
        convert_active.assert_called_once()

    @mock.patch("URDF_Exporter.standalone.server.convert_with_inventor")
    @mock.patch("URDF_Exporter.standalone.server._choose_inventor_file")
    def test_original_iam_path_route(self, choose_file, convert_path):
        assembly_path = Path(self.temp_dir.name) / "original_robot.iam"
        assembly_path.write_bytes(b"fake iam")
        choose_file.return_value = assembly_path
        convert_path.side_effect = lambda path, output_dir, project_name: (
            self.write_fake_inventor_exchange(
                output_dir,
                "petasos-inventor-path",
            )
        )
        response = self.client.post(
            "/import/inventor-file",
            json={"project_name": "Original Robot"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["status"], "imported")
        self.assertEqual(payload["source_path"], str(assembly_path))
        self.assertEqual(payload["report"]["parts"], 2)
        convert_path.assert_called_once()
        self.assertEqual(Path(convert_path.call_args.args[0]), assembly_path)

    @mock.patch("URDF_Exporter.standalone.server._choose_inventor_file")
    def test_original_iam_path_cancel_is_not_an_error(self, choose_file):
        choose_file.return_value = None
        response = self.client.post(
            "/import/inventor-file",
            json={"project_name": "Cancelled Robot"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "cancelled")

    @mock.patch("URDF_Exporter.standalone.server.convert_active_inventor")
    def test_failed_direct_import_preserves_existing_project(self, convert_active):
        self.import_demo()
        previous_dir = self.store.project_dir
        previous_state = self.store.state
        previous_source_files = sorted(
            path.name for path in (previous_dir / "sources").iterdir()
        )
        convert_active.side_effect = RuntimeError("simulated Inventor failure")

        response = self.client.post(
            "/import/inventor-active",
            json={"project_name": "Simple Arm"},
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.store.project_dir, previous_dir)
        self.assertEqual(self.store.state, previous_state)
        self.assertEqual(
            sorted(path.name for path in (previous_dir / "sources").iterdir()),
            previous_source_files,
        )

    def test_moveit_routes_use_latest_export_and_can_stop(self):
        self.import_demo()
        tree = self.client.get("/data").get_json()
        saved = self.client.post(
            "/save",
            json={
                "tree": tree,
                "fix_to_world": True,
                "include_moveit": True,
            },
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        package_dir = Path(saved.get_json()["save_dir"])
        runner = self.app.config["PETASOS_WSL_MOVEIT"]

        with mock.patch.object(
            runner,
            "start_assistant",
            return_value={
                "status": "preparing",
                "message": "assistant",
                "mode": "assistant",
                "output": [],
            },
        ) as start_assistant:
            response = self.client.post("/moveit/wsl/assistant")
        self.assertEqual(response.status_code, 200)
        start_assistant.assert_called_once_with(package_dir)

        with mock.patch.object(
            runner,
            "start_demo",
            return_value={
                "status": "preparing",
                "message": "demo",
                "mode": "demo",
                "output": [],
            },
        ) as start_demo:
            response = self.client.post("/moveit/wsl/demo")
        self.assertEqual(response.status_code, 200)
        start_demo.assert_called_once_with(package_dir)

        with mock.patch.object(
            runner,
            "stop",
            return_value={
                "status": "stopped",
                "message": "stopped",
                "mode": None,
                "output": [],
            },
        ) as stop:
            response = self.client.post("/moveit/wsl/stop")
        self.assertEqual(response.status_code, 200)
        stop.assert_called_once_with()

        with mock.patch.object(
            runner,
            "run_smoke",
            return_value={
                "status": "demo_running",
                "message": "movement ok",
                "mode": "demo",
                "smoke_result": {"success": True},
                "output": [],
            },
        ) as run_smoke:
            response = self.client.post("/moveit/wsl/smoke")
        self.assertEqual(response.status_code, 200)
        run_smoke.assert_called_once_with()

    def test_browser_refresh_stops_rviz_moveit_and_stale_wsl_gui(self):
        rviz_runner = self.app.config["PETASOS_WSL_RVIZ"]
        moveit_runner = self.app.config["PETASOS_WSL_MOVEIT"]
        cleanup = mock.Mock(return_value={"status": "stopped", "stopped": 4})
        self.app.config["PETASOS_WSL_GUI_CLEANUP"] = cleanup

        with mock.patch.object(rviz_runner, "stop") as stop_rviz, \
             mock.patch.object(moveit_runner, "stop") as stop_moveit:
            response = self.client.post("/wsl/gui/stop")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "stopped")
        self.assertEqual(response.get_json()["stopped"], 4)
        stop_rviz.assert_called_once_with()
        stop_moveit.assert_called_once_with()
        cleanup.assert_called_once_with()

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("cleanupWslGuiBeforeRefresh", html)
        self.assertIn("navigator.sendBeacon('/wsl/gui/stop')", html)
        self.assertIn("event.key === 'F5'", html)

    def test_moveit_routes_require_an_export(self):
        self.assertEqual(
            self.client.post("/moveit/wsl/assistant").status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/moveit/wsl/demo").status_code,
            404,
        )

    def test_moveit_joint_limits_are_repaired_as_yaml_floats(self):
        package = Path(self.temp_dir.name) / "simple_arm_moveit_config"
        (package / "config").mkdir(parents=True)
        (package / "launch").mkdir()
        (package / "package.xml").write_text("<package/>", encoding="utf-8")
        (package / ".setup_assistant").write_text(
            "moveit_setup_assistant_config:\n"
            "  package_settings:\n"
            "    author_name: Test\n"
            "    author_email: test@local.invalid\n"
            "    generated_timestamp: 0\n",
            encoding="utf-8",
        )
        (package / "launch" / "demo.launch.py").write_text(
            "# demo",
            encoding="utf-8",
        )
        (package / "config" / "kinematics.yaml").write_text(
            "arm: {}\n",
            encoding="utf-8",
        )
        (package / "config" / "moveit_controllers.yaml").write_text(
            "type: FollowJointTrajectory\n",
            encoding="utf-8",
        )
        (package / "config" / "ros2_controllers.yaml").write_text(
            "type: joint_trajectory_controller/JointTrajectoryController\n"
            "joint_state_broadcaster: {}\n",
            encoding="utf-8",
        )
        (package / "config" / "initial_positions.yaml").write_text(
            "initial_positions:\n  joint_1: 0.0\n",
            encoding="utf-8",
        )
        (package / "config" / "simple_arm.srdf").write_text(
            '<robot name="simple_arm"><group name="arm">'
            '<joint name="joint_1"/></group></robot>\n',
            encoding="utf-8",
        )
        limits = package / "config" / "joint_limits.yaml"
        limits.write_text(
            "joint_limits:\n"
            "  joint_1:\n"
            "    max_velocity: 1\n"
            "    max_acceleration: 2\n"
            "    has_velocity_limits: true\n",
            encoding="utf-8",
        )

        initial = repair_joint_limits(limits)
        self.assertFalse(initial["valid"])
        result = validate_moveit_package(package, fix=True)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["joint_limits"]["repaired"]), 2)
        text = limits.read_text(encoding="utf-8")
        self.assertIn("max_velocity: 1.0", text)
        self.assertIn("max_acceleration: 2.0", text)
        self.assertIn(
            "action_ns: follow_joint_trajectory",
            (package / "config" / "moveit_controllers.yaml").read_text(
                encoding="utf-8"
            ),
        )

    def test_moveit_assistant_controller_output_is_repaired_for_humble(self):
        package = Path(self.temp_dir.name) / "sample_moveit_config"
        (package / "config").mkdir(parents=True)
        (package / "launch").mkdir()
        (package / "package.xml").write_text("<package/>", encoding="utf-8")
        (package / ".setup_assistant").write_text(
            "moveit_setup_assistant_config:\n"
            "  package_settings:\n"
            "    author_name: Test\n"
            "    author_email: test@local.invalid\n"
            "    generated_timestamp: 0\n",
            encoding="utf-8",
        )
        (package / "launch" / "demo.launch.py").write_text(
            "# demo\n",
            encoding="utf-8",
        )
        (package / "config" / "kinematics.yaml").write_text(
            "arm: {}\n",
            encoding="utf-8",
        )
        (package / "config" / "joint_limits.yaml").write_text(
            "joint_limits:\n"
            "  joint_a:\n"
            "    has_velocity_limits: true\n"
            "    max_velocity: 1.0\n"
            "    has_acceleration_limits: true\n"
            "    max_acceleration: 1.0\n",
            encoding="utf-8",
        )
        (package / "config" / "sample.srdf").write_text(
            '<robot name="sample"><group name="arm">'
            '<joint name="joint_a"/></group></robot>\n',
            encoding="utf-8",
        )
        moveit_controllers = package / "config" / "moveit_controllers.yaml"
        moveit_controllers.write_text(
            "moveit_simple_controller_manager:\n"
            "  controller_names:\n"
            "    - arm_group_controller\n"
            "  arm_group_controller:\n"
            "    type: FollowJointTrajectory\n"
            "    joints:\n"
            "      - joint_a\n",
            encoding="utf-8",
        )
        ros2_controllers = package / "config" / "ros2_controllers.yaml"
        ros2_controllers.write_text(
            "controller_manager:\n"
            "  ros__parameters:\n"
            "    arm_group_controller:\n"
            "      type: joint_trajectory_controller/JointTrajectoryController\n"
            "    joint_state_broadcaster:\n"
            "      type: joint_state_broadcaster/JointStateBroadcaster\n"
            "arm_group_controller:\n"
            "  ros__parameters:\n"
            "    command_interfaces:\n"
            "      - position\n"
            "      - velocity\n"
            "      - effort\n"
            "    state_interfaces:\n"
            "      - position\n"
            "      - velocity\n"
            "      - effort\n"
            "    joints:\n"
            "      - joint_a\n",
            encoding="utf-8",
        )
        initial_positions = package / "config" / "initial_positions.yaml"
        initial_positions.write_text(
            "initial_positions:\n  joint_a: 0\n",
            encoding="utf-8",
        )
        urdf = Path(self.temp_dir.name) / "sample.urdf"
        urdf.write_text(
            """
<robot name="sample">
  <link name="base_link"/>
  <link name="tip"/>
  <joint name="joint_a" type="revolute">
    <parent link="base_link"/>
    <child link="tip"/>
    <axis xyz="0.0 0.0 1.0"/>
    <limit lower="-3.0" upper="-1.0" effort="100.0" velocity="1.0"/>
  </joint>
</robot>
""",
            encoding="utf-8",
        )

        result = validate_moveit_package(
            package,
            fix=True,
            urdf_path=urdf,
            external_control=True,
        )

        self.assertTrue(result["valid"], result)
        self.assertIn(
            "action_ns: follow_joint_trajectory",
            moveit_controllers.read_text(encoding="utf-8"),
        )
        controller_text = ros2_controllers.read_text(encoding="utf-8")
        command_block = controller_text.split("command_interfaces:", 1)[1].split(
            "state_interfaces:",
            1,
        )[0]
        state_block = controller_text.split("state_interfaces:", 1)[1].split(
            "joints:",
            1,
        )[0]
        self.assertIn("- position", command_block)
        self.assertNotIn("- velocity", command_block)
        self.assertNotIn("- effort", command_block)
        self.assertIn("- position", state_block)
        self.assertIn("- velocity", state_block)
        self.assertNotIn("- effort", state_block)
        self.assertIn(
            "joint_a: -2.0",
            initial_positions.read_text(encoding="utf-8"),
        )

    def test_moveit_assistant_urdf_is_sanitized_only_internally(self):
        urdf = Path(self.temp_dir.name) / "sample.urdf"
        urdf.write_text(
            """
<robot name="sample">
  <link name="base_link"/>
  <link name="tip"/>
  <joint name="joint_a" type="revolute">
    <parent link="base_link"/>
    <child link="tip"/>
    <limit lower="-1.0" upper="1.0" effort="10.0" velocity="1.0"/>
  </joint>
  <ros2_control name="sample_system" type="system">
    <hardware><plugin>mock_components/GenericSystem</plugin></hardware>
  </ros2_control>
  <transmission name="legacy"/>
  <gazebo>
    <plugin name="control" filename="libgazebo_ros2_control.so"/>
  </gazebo>
</robot>
""",
            encoding="utf-8",
        )

        result = prepare_assistant_urdf(urdf)
        root = ElementTree.parse(urdf).getroot()

        self.assertEqual(result["removed_ros2_control"], 1)
        self.assertEqual(result["removed_transmissions"], 1)
        self.assertEqual(result["removed_gazebo_plugins"], 1)
        self.assertIsNone(root.find("ros2_control"))
        self.assertIsNone(root.find("transmission"))
        self.assertIsNone(root.find("gazebo"))
        self.assertIsNotNone(root.find("joint"))

    def test_moveit_smoke_config_uses_float_limits_and_first_group(self):
        description = Path(self.temp_dir.name) / "sample_description"
        description.mkdir()
        (description / "package.xml").write_text(
            "<package/>",
            encoding="utf-8",
        )
        urdf = description / "sample.urdf"
        urdf.write_text(
            """
<robot name="sample">
  <link name="base_link"/>
  <link name="tip"/>
  <joint name="joint_a" type="revolute">
    <parent link="base_link"/>
    <child link="tip"/>
    <limit lower="-2.0" upper="-1.0" effort="10.0" velocity="1.0"/>
  </joint>
</robot>
""",
            encoding="utf-8",
        )
        output = Path(self.temp_dir.name) / "sample_moveit_config"
        result = generate_smoke_config(description, urdf, output)
        self.assertEqual(result["joints"][0]["initial"], -1.5)
        self.assertIn(
            '<group name="arm">',
            (output / "config" / "sample.srdf").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "max_velocity: 1.0",
            (output / "config" / "joint_limits.yaml").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            '.planning_pipelines(pipelines=["ompl"])',
            (output / "launch" / "demo.launch.py").read_text(
                encoding="utf-8"
            ),
        )
        validated = validate_moveit_package(output)
        self.assertTrue(validated["valid"], validated)
        self.assertEqual(validated["planning_groups"], ["arm"])

    def test_moveit_assistant_uses_seed_and_normalizes_saved_result(self):
        description = Path(self.temp_dir.name) / "sample_description"
        (description / "urdf").mkdir(parents=True)
        (description / "package.xml").write_text(
            "<package/>",
            encoding="utf-8",
        )
        (description / "urdf" / "sample.xacro").write_text(
            '<robot name="sample" xmlns:xacro="http://www.ros.org/wiki/xacro"/>',
            encoding="utf-8",
        )
        moveit_config = description.parent / "sample_moveit_config"
        moveit_config.mkdir()
        (moveit_config / "package.xml").write_text(
            "<package/>",
            encoding="utf-8",
        )
        runner = WslMoveItRunner(
            Path("moveit/validate_moveit_config.py")
        )
        with mock.patch.object(
            runner,
            "_spawn",
            return_value={"status": "preparing"},
        ) as spawn:
            runner.start_assistant(description)

        script = spawn.call_args.args[0]
        self.assertIn(' -c "$config_target"', script)
        self.assertNotIn(' -u "$target"', script)
        self.assertNotIn("generate_smoke_config.py", script)
        self.assertNotIn("prepare_assistant_urdf.py", script)
        self.assertNotIn("petasos_moveit_ws", script)
        self.assertNotIn("cp -a --", script)
        self.assertIn('target="$workspace/src/sample_description"', script)
        self.assertIn('config_target="$workspace/src/sample_moveit_config"', script)
        self.assertIn('runtime_root="$workspace/.petasos_runtime"', script)
        self.assertIn('--build-base "$runtime_root/build"', script)
        self.assertNotIn('source "$workspace/install/setup.bash"', script)
        self.assertIn(" --fix", script)
        self.assertIn("PETASOS_ASSISTANT_VALIDATION:", script)

    def test_moveit_demo_validates_source_and_assistant_result_without_repair(self):
        description = Path(self.temp_dir.name) / "sample_description"
        (description / "urdf").mkdir(parents=True)
        (description / "package.xml").write_text(
            "<package/>",
            encoding="utf-8",
        )
        (description / "urdf" / "sample.xacro").write_text(
            '<robot name="sample" xmlns:xacro="http://www.ros.org/wiki/xacro"/>',
            encoding="utf-8",
        )
        runner = WslMoveItRunner(
            Path("moveit/validate_moveit_config.py")
        )
        with mock.patch.object(
            runner,
            "_spawn",
            return_value={"status": "preparing"},
        ) as spawn:
            runner.start_demo(description)

        script = spawn.call_args.args[0]
        self.assertIn("validate_urdf.py", script)
        self.assertIn("validate_moveit_config.py", script)
        self.assertNotIn("prepare_assistant_urdf.py", script)
        self.assertNotIn(" --external-control", script)
        self.assertNotIn("petasos_moveit_ws", script)
        self.assertNotIn("cp -a --", script)
        self.assertIn('runtime_root="$workspace/.petasos_runtime"', script)
        self.assertIn('--install-base "$runtime_root/install"', script)
        self.assertIn(" --fix", script)

    def test_moveit_smoke_runner_sends_lf_only_script_to_wsl(self):
        runner = WslMoveItRunner(
            Path("moveit/validate_moveit_config.py")
        )
        runner._process = mock.MagicMock()
        runner._process.poll.return_value = None
        runner._mode = "demo"
        runner._status = "demo_running"
        runner._robot_name = "sample"
        runner._description_package = "sample_description"
        runner._config_package = "sample_moveit_config"
        runner._workspace_dir = Path(self.temp_dir.name) / "ros_ws"
        runner._workspace_wsl_path = "/mnt/c/export/ros_ws"
        payload = {
            "success": True,
            "error_code": 1,
            "max_target_error": 0.0001,
        }
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "PETASOS_MOVEIT_SMOKE_RESULT="
                + json.dumps(payload)
                + "\n"
            ).encode(),
            stderr=b"",
        )
        with mock.patch(
            "moveit.wsl_runner.subprocess.run",
            return_value=completed,
        ) as run:
            result = runner.run_smoke()
        self.assertEqual(result["smoke_result"], payload)
        self.assertEqual(result["status"], "demo_running")
        script = run.call_args.kwargs["input"]
        self.assertIsInstance(script, bytes)
        self.assertNotIn(b"\r\n", script)
        self.assertIn(b"ROS_DOMAIN_ID=42", script)
        self.assertIn(b".petasos_runtime/install/setup.bash", script)

    def test_moveit_urdf_preflight_rejects_out_of_range_initial_value(self):
        urdf = Path(self.temp_dir.name) / "robot.urdf"
        urdf.write_text(
            """
<robot name="sample">
  <link name="base_link"/>
  <link name="tip"/>
  <joint name="joint_1" type="revolute">
    <parent link="base_link"/>
    <child link="tip"/>
    <axis xyz="0.0 0.0 1.0"/>
    <limit lower="-3.0" upper="-1.0" effort="100.0" velocity="1.0"/>
  </joint>
  <ros2_control name="sample_system" type="system">
    <hardware><plugin>mock_components/GenericSystem</plugin></hardware>
    <joint name="joint_1">
      <command_interface name="position"/>
      <state_interface name="position">
        <param name="initial_value">0.0</param>
      </state_interface>
      <state_interface name="velocity"/>
    </joint>
  </ros2_control>
</robot>
""",
            encoding="utf-8",
        )
        result = validate_urdf_for_moveit(urdf)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("outside" in error for error in result["errors"]),
            result,
        )

        text = urdf.read_text(encoding="utf-8").replace(
            '<param name="initial_value">0.0</param>',
            '<param name="initial_value">-2.0</param>',
        )
        urdf.write_text(text, encoding="utf-8")
        result = validate_urdf_for_moveit(urdf)
        self.assertTrue(result["valid"], result)

    def test_moveit_urdf_preflight_rejects_ambiguous_control_interfaces(self):
        urdf = Path(self.temp_dir.name) / "robot.urdf"
        urdf.write_text(
            """
<robot name="sample">
  <link name="base_link"/>
  <link name="tip"/>
  <joint name="joint_1" type="revolute">
    <parent link="base_link"/>
    <child link="tip"/>
    <axis xyz="0.0 0.0 1.0"/>
    <limit lower="-1.0" upper="1.0" effort="100.0" velocity="1.0"/>
  </joint>
  <ros2_control name="sample_system" type="system">
    <hardware><plugin>mock_components/GenericSystem</plugin></hardware>
    <joint name="joint_1">
      <command_interface name="position"/>
      <command_interface name="effort"/>
      <state_interface name="position">
        <param name="initial_value">0.0</param>
      </state_interface>
      <state_interface name="velocity"/>
      <state_interface name="effort"/>
    </joint>
  </ros2_control>
</robot>
""",
            encoding="utf-8",
        )
        result = validate_urdf_for_moveit(urdf)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("command interfaces must be exactly" in error for error in result["errors"]),
            result,
        )
        self.assertTrue(
            any("state interfaces must be exactly" in error for error in result["errors"]),
            result,
        )

    def test_safe_setup_helper_is_local_opt_in_and_non_destructive(self):
        setup_cmd = Path("setup_petasos.cmd").read_text(
            encoding="utf-8",
        )
        setup_ps1 = Path("tools/setup_petasos.ps1").read_text(
            encoding="utf-8",
        )
        launcher = Path("start_petasos.cmd").read_text(
            encoding="utf-8",
        )
        rviz_cleanup = Path("tools/stop_petasos_wsl_gui.ps1").read_text(
            encoding="utf-8",
        )
        requirements = Path("requirements-standalone.txt").read_text(
            encoding="utf-8",
        )

        self.assertIn('Join-Path $ProjectRoot ".venv', setup_ps1)
        self.assertIn('$VenvRoot = Join-Path $ProjectRoot ".venv"', setup_ps1)
        self.assertIn(".venv.petasos-backup-$backupSuffix", setup_ps1)
        self.assertIn("Move-Item -LiteralPath $VenvRoot", setup_ps1)
        self.assertIn("& $BasePython.Path -m venv $VenvRoot", setup_ps1)
        self.assertIn("Read-Host", setup_ps1)
        self.assertIn('"-m", "pip", "install"', setup_ps1)
        self.assertIn('"--disable-pip-version-check"', setup_ps1)
        self.assertIn('"-r", $quotedRequirements', setup_ps1)
        self.assertIn("[switch]$CheckOnly", setup_ps1)
        self.assertIn("function Show-PythonInstallGuide", setup_ps1)
        self.assertIn('wsl.exe --list --quiet 2>$null', setup_ps1)
        self.assertIn(") *> $null", setup_ps1)
        self.assertIn("Python 3.12 is recommended", setup_ps1)
        self.assertIn("function Install-CompatiblePythonWithWinget", setup_ps1)
        self.assertIn("Get-Command winget.exe", setup_ps1)
        self.assertIn(
            "Install Python 3.12 automatically for the current Windows user?",
            setup_ps1,
        )
        self.assertIn("Python.Python.3.12", setup_ps1)
        self.assertIn("--scope user", setup_ps1)
        self.assertIn("--accept-package-agreements", setup_ps1)
        self.assertIn("--accept-source-agreements", setup_ps1)
        self.assertIn("--disable-interactivity", setup_ps1)
        self.assertIn("Open the official Python download page now?", setup_ps1)
        self.assertIn("https://www.python.org/downloads/windows/", setup_ps1)
        self.assertIn("if ($null -eq $basePython)", setup_ps1)
        self.assertIn("setup_petasos.ps1", setup_cmd)
        self.assertIn("PETASOS_SETUP_VERSION=2026.08.03.20", setup_ps1)
        self.assertIn("PETASOS_SETUP_VERSION=2026.08.03.20", setup_cmd)
        self.assertIn("PETASOS_ROS_SETUP_VERSION=2026.08.03.20", setup_cmd)
        self.assertIn(r"Local\PetasosA2Setup", setup_ps1)
        self.assertTrue(setup_cmd.isascii())
        self.assertIn("Copy setup_petasos.cmd and the complete tools folder", setup_cmd)
        self.assertIn("Missing or unusable Python modules", setup_ps1)
        self.assertIn("[1/3] Creating the project-local .venv", setup_ps1)
        self.assertIn("[2/3] Still installing Python/CAD packages", setup_ps1)
        self.assertIn("[3/3] Verifying Flask, numerical, mesh, and OpenCascade modules", setup_ps1)
        self.assertIn("WaitForExit(10000)", setup_ps1)
        self.assertIn("$pipProcess.Refresh()", setup_ps1)
        self.assertIn("Checking the installed environment", setup_ps1)
        self.assertIn("& $VenvPython -m pip check", setup_ps1)
        self.assertIn("continuing despite the stale pip exit code", setup_ps1)
        self.assertIn("OneDrive is scanning this .venv", setup_ps1)
        self.assertIn("trimesh\n", requirements)
        self.assertNotIn("trimesh[all]", requirements)
        self.assertIn('if not exist "%~dp0tools\\setup_petasos.ps1"', setup_cmd)
        self.assertIn('choose "Extract All"', setup_cmd)
        self.assertIn("setup_petasos.cmd first", launcher)
        self.assertIn('setup_petasos.ps1" -CheckOnly', launcher)
        self.assertIn('call "%~dp0setup_petasos.cmd"', launcher)
        self.assertIn('if not exist "%~dp0petasos_standalone.py"', launcher)
        self.assertIn('choose "Extract All"', launcher)
        self.assertIn("stop_petasos_wsl_gui.ps1", launcher)
        self.assertIn("Closing any previous Petasos RViz window", launcher)
        self.assertIn("pkill -TERM -x rviz2", rviz_cleanup)
        self.assertIn("pkill -KILL -x rviz2", rviz_cleanup)
        self.assertIn("moveit_setup_assistant", rviz_cleanup)
        self.assertIn("move_group", rviz_cleanup)
        self.assertIn("demo\\.launch\\.py", rviz_cleanup)
        self.assertIn("display.launch.py", rviz_cleanup)
        self.assertNotIn("wsl.exe --shutdown", rviz_cleanup)

        lowered = setup_ps1.lower()
        self.assertNotIn("wsl --install", lowered)
        self.assertNotIn("setx ", lowered)
        self.assertNotIn("remove-item", lowered)
        self.assertNotIn("enable-windowsoptionalfeature", lowered)

    def test_guided_ros_setup_requires_consent_and_targets_only_humble(self):
        setup_ps1 = Path("tools/setup_petasos.ps1").read_text(
            encoding="utf-8",
        )
        windows_installer = Path(
            "tools/install_ros2_humble.ps1",
        ).read_text(encoding="utf-8")
        ubuntu_installer = Path(
            "tools/install_ros2_humble.sh",
        ).read_text(encoding="utf-8")

        self.assertIn("Start-RosGuidedSetup", setup_ps1)
        self.assertIn("Read-Host", windows_installer)
        self.assertIn("[switch]$CheckOnly", windows_installer)
        self.assertIn("function Invoke-WslCapture", windows_installer)
        self.assertIn("petasos-ros-check-", windows_installer)
        self.assertIn("CHECK_ONLY:", windows_installer)
        self.assertIn("function Test-UbuntuRegistered", windows_installer)
        self.assertIn("function Get-RegisteredWslDistros", windows_installer)
        self.assertIn("function Get-UbuntuRelease", windows_installer)
        self.assertIn("ConvertFrom-NativeText", windows_installer)
        self.assertIn("Ubuntu first-run setup is still incomplete", windows_installer)
        self.assertIn('@("--shutdown")', windows_installer)
        self.assertIn('@("--unregister", $Distro)', windows_installer)
        self.assertIn("Reset only Ubuntu-22.04 and reinstall it?", windows_installer)
        self.assertIn("permanently deletes files", windows_installer)
        self.assertIn("Start-Process", windows_installer)
        self.assertIn(
            '@("--install", "--web-download", "--no-launch", "-d", "Ubuntu-22.04")',
            windows_installer,
        )
        self.assertIn(r"Local\PetasosA2RosSetup", windows_installer)
        self.assertIn("Another Petasos WSL/ROS setup is already running", windows_installer)
        self.assertIn("Using direct web download", windows_installer)
        self.assertIn("--no-launch", windows_installer)
        self.assertIn(
            "Ubuntu first-run setup completed. Continuing with ROS 2 installation.",
            windows_installer,
        )
        self.assertIn("-d $Distro -u root -- bash $linuxPath $linuxUser", windows_installer)
        self.assertIn("The default Ubuntu user remains unchanged", windows_installer)
        self.assertIn('TARGET_USER="${1:-}"', ubuntu_installer)
        self.assertIn('sudo -H -u "$TARGET_USER" rosdep update', ubuntu_installer)
        self.assertIn("Microsoft-Windows-Subsystem-Linux", windows_installer)
        self.assertIn("VirtualMachinePlatform", windows_installer)
        self.assertIn("-EncodedCommand", windows_installer)
        self.assertIn("petasos-wsl-bootstrap-", windows_installer)
        self.assertIn("Get-Content -LiteralPath $logPath -Tail 80", windows_installer)
        self.assertIn("[WSL setup] Still working... elapsed", windows_installer)
        self.assertIn("WaitForExit(5000)", windows_installer)
        self.assertIn("HCS_E_HYPERV_NOT_INSTALLED", windows_installer)
        self.assertIn("VirtualizationFirmwareEnabled", windows_installer)
        self.assertIn("hypervisorlaunchtype", windows_installer)
        self.assertIn("$env:WSL_UTF8", windows_installer)
        self.assertIn("ERROR_ALREADY_EXISTS confirmed", windows_installer)
        self.assertIn("Distribution is already registered; installation skipped", windows_installer)
        self.assertIn("[System.IO.File]::ReadAllBytes($LinuxInstaller)", windows_installer)
        self.assertIn("[System.Convert]::ToBase64String", windows_installer)
        self.assertIn("base64 -d", windows_installer)
        self.assertIn("/tmp/petasos-install-ros2-humble.sh", windows_installer)
        self.assertNotIn('"wslpath", "-a", "-u", $portableWindowsPath', windows_installer)
        self.assertIn("Windows drive letters and non-ASCII user names", windows_installer)
        self.assertIn("function Get-Utf8Text", windows_installer)
        self.assertIn("V2luZG93c+ulvCDsnqzrtoDtjIXtlZwg65Kk", windows_installer)
        self.assertIn("nested virtualization|중첩 가상화", windows_installer)
        self.assertIn("ROS installation cannot run in this Windows virtual machine", windows_installer)
        self.assertIn("run ROS 2 directly in an Ubuntu 22.04 VM", windows_installer)
        self.assertIn("$guidedSetupExitCode = [int]$LASTEXITCODE", setup_ps1)
        self.assertIn("return $guidedSetupExitCode", setup_ps1)
        self.assertIn("$rosSetupExitCode -ne 0", setup_ps1)
        self.assertIn('@("--update")', windows_installer)
        self.assertIn("-Verb RunAs", windows_installer)
        self.assertIn('"ubuntu|22.04"', windows_installer)
        self.assertIn("Detected: '$release'", windows_installer)
        self.assertIn('VERSION_ID:-}" != "22.04"', ubuntu_installer)
        self.assertIn("ros-humble-desktop", ubuntu_installer)
        self.assertIn("ros-humble-joint-state-publisher-gui", ubuntu_installer)
        self.assertIn("ros-humble-moveit", ubuntu_installer)
        self.assertIn("ros-humble-moveit-setup-assistant", ubuntu_installer)
        self.assertIn("ros2 pkg prefix controller_manager", ubuntu_installer)
        self.assertIn("ros2 pkg prefix joint_trajectory_controller", ubuntu_installer)
        self.assertIn("ros2 pkg prefix gazebo_ros", ubuntu_installer)
        self.assertIn("command -v colcon", ubuntu_installer)
        self.assertIn("[1/5] Updating Ubuntu package information", ubuntu_installer)
        self.assertIn("[5/5] Verifying ROS 2, RViz, and MoveIt", ubuntu_installer)
        self.assertIn("set +u\nsource /opt/ros/humble/setup.bash\nset -u", ubuntu_installer)
        self.assertNotIn("apt-get remove", ubuntu_installer)
        self.assertNotIn("apt-get autoremove", ubuntu_installer)
        self.assertNotIn("wsl.exe --unregister", windows_installer.lower())

    def test_ground_edge_alignment_checkbox_has_visible_label(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn('class="ground-edge-toggle"', html)
        self.assertIn("바닥면 방향도 자동 정렬", html)
        self.assertIn("긴 모서리를 월드 X/Z축에 맞춤", html)
        self.assertIn(
            '.preview-control-range input[type="range"]',
            html,
        )
        self.assertNotIn(
            ".preview-control-range input, .joint-slider",
            html,
        )

    def test_preview_joint_details_are_collapsible_and_remembered(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("let expandedPreviewJointDetails = new Set();", html)
        self.assertIn("function togglePreviewJointDetails", html)
        self.assertIn('class="joint-details-toggle"', html)
        self.assertNotIn("리밋 · 축 세부 설정", html)
        self.assertIn("'세부 설정 펼치기'", html)
        self.assertIn('class="joint-details-arrow"', html)
        self.assertIn('d="M1 1l5 5 5-5"', html)
        self.assertIn("grid-template-columns: 1fr 28px 1fr", html)
        self.assertIn('class="joint-details"', html)
        self.assertIn(
            ".joint-control.details-expanded .joint-details",
            html,
        )

    def test_header_shows_active_workspace_name_next_to_import(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        import_position = html.index('id="standalone-import-button"')
        name_position = html.index('id="header-workspace-name"')
        save_position = html.index('id="workspace-save-button"')
        self.assertLess(import_position, name_position)
        self.assertLess(name_position, save_position)
        self.assertIn('onclick="toggleHeaderWorkspaceMenu(event)"', html)
        self.assertIn('class="header-workspace-label">현재 작업', html)
        self.assertIn('id="header-workspace-value"', html)
        self.assertIn('class="header-workspace-chevron"', html)
        self.assertIn('id="header-workspace-menu"', html)
        self.assertIn("function toggleHeaderWorkspaceMenu", html)
        self.assertIn("async function refreshHeaderWorkspaceMenu", html)
        self.assertIn("async function switchHeaderWorkspace", html)
        self.assertIn("top: calc(100% + 7px)", html)
        self.assertIn(
            "const displayName = activeName || projectName || '새 작업';",
            html,
        )
        self.assertIn("headerValue.textContent = displayName", html)

    def test_undo_history_orders_tree_preview_and_camera_actions(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("function pushHistoryEntry(entry)", html)
        self.assertIn("pushHistoryEntry({kind: 'tree', snapshot})", html)
        self.assertIn("kind: 'preview_joint'", html)
        self.assertIn("kind: 'preview_pose'", html)
        self.assertIn("kind: 'viewer_camera'", html)
        self.assertIn("controls.addEventListener('start', beginViewerCameraGesture)", html)
        self.assertIn("controls.addEventListener('end', endViewerCameraGesture)", html)
        self.assertIn(
            "pendingPreviewPoseRestore = capturePreviewJointPose();",
            html,
        )
        undo_block = html[
            html.index("function undo()"):
            html.index("document.addEventListener('keydown'", html.index("function undo()"))
        ]
        self.assertIn("historyStack.pop()", undo_block)
        self.assertIn("entry.kind === 'viewer_camera'", undo_block)
        self.assertIn("entry.kind === 'preview_joint'", undo_block)
        self.assertIn("entry.kind === 'preview_pose'", undo_block)
        self.assertIn("entry.kind !== 'tree'", undo_block)
        self.assertNotIn("fitCameraToRobot()", undo_block)

    def test_ground_selection_rebuilds_visible_scaled_world_grid(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("function refreshWorldReferencePlane", html)
        self.assertIn("span * 5", html)
        self.assertIn("gridHelper.position.y = Number(groundY) - groundOffset", html)
        self.assertIn("material.depthWrite = false", html)
        self.assertIn("refreshWorldReferencePlane(0);", html)
        world_toggle = html[
            html.index("function toggleWorldFrame"):
            html.index("function toggleJointFrames")
        ]
        self.assertIn("gridHelper.visible = visible", world_toggle)

    def test_ground_selection_keeps_robot_bulk_above_selected_plane(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("const alignedBounds = new THREE.Box3();", html)
        self.assertIn("alignedModelCenter.y < -verticalTolerance", html)
        self.assertIn("flipAroundWorldX", html)
        self.assertIn(
            "const flippedAnchorWorld = robotRoot.localToWorld(rootLocalCenter.clone());",
            html,
        )
        self.assertIn(
            "normal_flipped_to_keep_model_above: normalFlippedToKeepModelAbove",
            html,
        )
        self.assertIn("function repairStoredGroundTransformIfBelowPlane", html)
        self.assertIn("ground.repaired_after_load = true", html)
        self.assertIn(
            "if (repairStoredGroundTransformIfBelowPlane())",
            html,
        )
        self.assertIn("anchorDistance > anchorDiagonal * 8", html)
        self.assertIn("clearCustomGroundTransform();", html)
        self.assertIn("applyRobotRootUpAxis(resolvePreviewUpAxis());", html)

    def test_opencascade_snap_rejects_implausibly_large_arc_candidates(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("const featureCenterDistance = geometry?.boundingBox", html)
        self.assertIn("const maximumCadExtent = diagonal * 8;", html)
        self.assertIn("featureCenterDistance > maximumCadExtent", html)
        self.assertIn("radius > maximumCadExtent", html)
        projected_block = html[
            html.index("function projectedCadSnapCandidates"):
            html.index("function resolveBestSurfaceSnap")
        ]
        self.assertIn("mesh.geometry.boundingBox", projected_block)
        self.assertIn(".distanceToPoint(localCenter)", projected_block)
        self.assertIn("featureCenterDistance > maximumCadExtent", projected_block)

    def test_ground_origin_is_presented_as_a_required_primary_step(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn('id="ground-origin-panel"', html)
        self.assertIn('<strong>기준 좌표 설정</strong>', html)
        self.assertIn('id="ground-origin-state"', html)
        self.assertIn('class="ground-face-btn primary"', html)
        self.assertIn("state.textContent = hasGroundOrigin ? '설정 완료' : '필수 설정'", html)
        self.assertIn("panel.classList.toggle('is-complete', hasGroundOrigin)", html)
        self.assertIn(".ground-origin-panel.is-complete:not(.is-picking)", html)
        self.assertIn("? '변경'", html)
        self.assertIn(".ground-origin-secondary,", html)

    def test_grouping_list_candidate_cards_do_not_repeat_instruction_text(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertNotIn(
            "🧲 묶음 후보 · 같은 링크면 다른 카드와 겹치세요",
            html,
        )

    def test_link_part_remove_icon_turns_soft_red_on_hover(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn(".link-part-remove:hover,", html)
        self.assertIn("color: #ff7676; opacity: 1", html)
        self.assertIn("drop-shadow(0 0 3px rgba(255,86,86,0.32))", html)

    def test_continuous_joint_ui_does_not_offer_position_limits(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("const isContinuous = controller.type === 'continuous';", html)
        self.assertIn(
            "controller.type === 'revolute' ? `\n                        <div class=\"joint-limit-editor\">",
            html,
        )
        self.assertIn("연속 회전 · 최소/최대 제한 없음", html)
        self.assertIn("미리보기 조작 범위 · URDF 회전 제한 아님", html)
        self.assertNotIn("제한 없음 · 값을 지정하면 revolute로 전환", html)

    def test_joint_type_settings_card_contains_required_urdf_values(self):
        html = Path("URDF_Exporter/core/web_ui.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("<strong>URDF 동작 설정</strong>", html)
        self.assertIn("최대 힘 (${effortUnit})", html)
        self.assertIn("최대 속도 (${velocityUnit})", html)
        self.assertIn("최소 이동 (m)", html)
        self.assertIn("최대 이동 (m)", html)
        self.assertIn("function updateJointUrdfValue", html)
        self.assertIn("최소값은 최대값보다 작아야 합니다.", html)
        self.assertIn("fixed 조인트", html)
        self.assertIn("축·리밋·effort·velocity 설정이 필요하지 않습니다.", html)


if __name__ == "__main__":
    unittest.main()
