# Reusable Robot Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 트리에서 수동 선택한 그리퍼를 저장·재사용·교체하고 모듈별 Xacro로 내보낸다.

**Architecture:** 기존 트리는 유지하고 영속 ID와 `_modules`를 추가한다. 순수 그래프 검증·좌표 변환, 안전한 라이브러리 파일 입출력, 프로젝트 적용, UI 선택, Xacro 출력을 분리한다. 본체와 한 곳으로 연결되는 끝단 모듈만 첫 버전에서 지원한다.

**Tech Stack:** Python, unittest, Flask, NumPy/trimesh, 기존 JavaScript/Three.js 편집기, ROS 2 Humble Xacro/MoveIt.

**Spec:** `docs/superpowers/specs/2026-09-28-reusable-robot-modules-design.md` — 사용자 승인됨.

## Global Constraints

- Ctrl+클릭 다중 선택과 드래그 영역 선택을 지원한다.
- 선택 링크의 하위 구조 전체를 자동으로 포함하지 않는다.
- XYZ UI 단위는 mm, RPY UI 단위는 degree, 내부 및 URDF 단위는 m/rad다.
- 모듈은 링크 병합, 컨트롤러 그룹과 별개의 개념이다.
- `world`, `base_footprint`, 로봇 본체 루트, 중첩 모듈, 같은 링크의 중복 모듈 소속은 제외한다.
- 압축 파일 200 MiB, 압축 해제 총량 1 GiB, 파일 수 10,000개를 초기 상한으로 적용한다.
- 버전 1만 읽으며 알 수 없는 버전은 오류와 함께 거부한다.
- 기존 장착 조인트의 부모·타입·설정·변환을 교체 시 보존한다.
- 모듈 내부와 외부 조인트가 섞인 컨트롤러 그룹은 자동 분할하지 않는다.
- 실행 중 ROS 핫스왑, 이동 베이스/다중 포트, 중첩 모듈, TCP 자동 보정은 제외한다.
- 모듈 없는 프로젝트의 출력과 기존 기능을 유지한다. 새 기능의 설정을 기존 파일에 강제하지 않는다.
- GitHub push는 별도 요청 없이는 하지 않는다. `Ogre.log`와 프로젝트·라이브러리·익스포트 결과물을 커밋하지 않는다.

## Review Focus

- 이름 변경/자동 번호 변경 뒤 참조가 다른 링크를 가리키는 문제: Task 1/7에서 ID 보존과 이름 매핑 테스트.
- 회전된 CAD 프레임에서 두 번 변환되는 메시·무게중심·관성: Task 2/7에서 비대칭 관성과 비영점 장착 회전 테스트.
- 같은 모듈을 연속 두 번 장착해 부품·재질·mimic·컨트롤러 이름이 충돌하는 문제: Task 4에서 전체 참조 검사.
- 열어둔 편집기가 오래된 상태로 교체/저장을 덮어쓰는 문제: Task 4/5에서 revision 충돌과 롤백 테스트.
- 아카이브의 대소문자 경로 충돌·심볼릭 링크·과도한 압축 해제: Task 3에서 Windows 기준 경로 정규화 및 실제 바이트 상한 테스트.

## 작업 환경과 파일 책임

실행 시작 시 using-git-worktrees 절차로 작업 위치를 정하고, 경로를 명시해서 명령을 실행한다.
현재 `.venv/Scripts/python.exe`의 사용 가능 여부를 먼저 확인한다. 작업트리에 가상환경이 없다면
원본 저장소 가상환경 실행파일의 절대 경로를 사용하고 cwd를 작업트리로 지정한다.
아래 `$petasosPython`은 이때 확인한 실행파일 경로다. 테스트를 설치했다고 가정하지 않는다.

새 파일:

- `URDF_Exporter/standalone/robot_modules.py`: ID, 범위, 참조, 트리 작업의 순수 도메인 함수.
- `URDF_Exporter/standalone/module_geometry.py`: 모듈 기준 프레임과 부품 상태 변환.
- `URDF_Exporter/standalone/module_library.py`: ZIP와 로컬 라이브러리 읽기/저장.
- `URDF_Exporter/standalone/module_service.py`: 프로젝트 revision과 트랜잭션 적용.
- `URDF_Exporter/standalone/module_export.py`: ID 기반 출력 분할 및 Xacro 매크로 생성.
- `URDF_Exporter/core/module_selection.js`: DOM에 의존하지 않는 선택/영역 계산 함수.
- `schemas/petasos-module.schema.json`: 라이브러리 모듈 형식 1.
- `tests/test_robot_modules.py`, `test_module_geometry.py`, `test_module_library.py`,
  `test_module_service.py`, `test_module_api.py`, `test_module_export.py`.
- `tests/test_module_selection.cjs`: Node 내장 test/assert 기반 순수 선택 테스트.

기존 파일 수정은 아래 각 Task에 명시한다. `web_ui.py`의 다른 UI를 전면 재작성하지 않는다.

### Task 1: 영속 ID와 수동 범위 검증

**Files:** `robot_modules.py` 생성; `server.py`의 `ProjectStore.tree/save_workspace`,
`reimporter.py` 수정; `tests/test_robot_modules.py` 생성.

**Interfaces:**
- `ensure_module_ids(tree: dict) -> dict`: 복사본의 링크 `_link_id`, 자식 연결의 `_joint_id`를 보충.
- `validate_module_selection(tree: dict, link_ids: list[str], joint_ids: list[str], editing_id: str | None = None) -> dict`.
- 결과: `{valid, errors: [{code, ids, message}], root_link_id, attachment_joint_id}`.
- `create_module(tree: dict, link_ids: list[str], joint_ids: list[str], name: str) -> dict`:
  검증된 복사본에 `{version:1, id, name, color, link_ids, joint_ids, root_link_id, attachment_joint_id, prefix}` 추가.
- `validate_modules(tree: dict) -> list[dict]`: 프로젝트 내 모든 모듈을 같은 규칙으로 검사.

- [ ] 기존 트리 fixture 형식으로 base → wrist → palm → finger를 구성한다.
  `test_manual_selection_does_not_add_descendants`에서 palm만 선택하면 외부 연결 오류이고,
  입력 트리가 바뀌지 않았음을 `assertEqual(tree, before)`로 검사한다.
  `test_ids_survive_rename_and_reload`에서 이름 변경 전후 ID가 같고,
  `test_disconnected_or_missing_joint_is_rejected`에서 오류 ID가 누락 조인트를 가리키는지 검사한다.
  컨트롤러 경계, 양방향 mimic 참조, 루트 선택, 중복 ID/소속 거부 테스트도 추가한다.
- [ ] `& $petasosPython -m unittest tests.test_robot_modules -v` 실행: 새 함수 누락/미구현에 의한 FAIL 확인.
- [ ] 위 인터페이스 구현. 경계 연결은 소유권이 본체에 있는 장착 조인트로 판별하여 별도 표시한다.
  내부 조인트는 반드시 명시 선택돼야 한다. 로드/재가져오기에서 ID 보존을 연결한다.
- [ ] 같은 테스트를 실행해 PASS 확인. 기존 저장/재가져오기 테스트도 실행한다.
- [ ] 이 Task 파일만 커밋: `feat: validate manually selected robot module boundaries`.

### Task 2: 프레임 독립 모듈 스냅샷

**Files:** `module_geometry.py`, `tests/test_module_geometry.py` 생성;
`schemas/petasos-module.schema.json` 생성.

**Interfaces:**
- `capture_module(state: dict, tree: dict, module_id: str) -> dict`:
  `{format:'petasos-module', version:1, name, root_link_id, tree, parts, inertial, materials,
  colors, visual_transforms, snap_features, controllers, meshes}`를 반환한다.
- `place_module(payload: dict, root_world: list[float]) -> dict`: 모듈 기준 조립 배치를 목적 프레임으로 변환.
- 행렬 계약은 row-major 4×4, m 단위. Three.js column-major/mm 입력은 경계에서 한 번만 변환.
  로컬 조인트/visual/inertial 값은 같은 프레임 정의를 유지한다.
- `meshes`는 아카이브 상대 경로와 소스 부품 ID의 목록이며 절대 경로를 저장하지 않는다.

- [ ] `test_rotated_module_preserves_fk_and_inertia` 작성: root를 Z축 90도/XYZ=[0.1,0.2,0.3]에
  장착한 뒤 링크 상대 FK와 비대칭 관성이 원본과 `atol=1e-8`로 같은지 검사한다.
  `test_capture_is_independent_of_cad_world_origin`에서 원본 전체를 이동해도 캡처 결과의 로컬 값은 같다.
- [ ] `& $petasosPython -m unittest tests.test_module_geometry -v`: FAIL 확인.
- [ ] Task 1 검증을 사용해 캡처/배치 구현. 부품 단위 inertial/material override와 CAD 스냅 데이터를 포함한다.
- [ ] 위 테스트 및 `tests.test_structure` 실행: PASS 확인.
- [ ] 커밋: `feat: serialize reusable modules in root-local coordinates`.

### Task 3: 안전한 로컬 모듈 라이브러리

**Files:** `module_library.py`, `tests/test_module_library.py` 생성; `.gitignore` 수정.

**Interfaces:**
- `ModuleLibrary(root: Path)`.
- `save(payload: dict, mesh_root: Path) -> dict`, `load(module_id: str) -> tuple[dict, Path]`.
- `list_modules() -> list[dict]`, `import_archive(archive: Path) -> dict`,
  `export_archive(module_id: str, destination: Path) -> Path`.
- 반환 요약 필드: `{id, name, version, link_count, joint_count}`.
- 기본 저장소 `standalone_modules/`; 실행 환경/테스트에서 경로 주입 가능. 가져오기는 새 ID를 생성한다.

- [ ] `test_archive_roundtrip`에서 payload와 메시 해시가 왕복 후 동일한지 검사한다.
  `test_rejects_zip_slip_symlink_duplicate_and_case_collision`,
  `test_enforces_limits_during_streaming` 작성: 경로 이탈·중복·200 MiB/1 GiB/10,000 제한을 검사한다.
  제한 테스트는 작은 주입 한도도 사용하여 거대 임시 파일을 만들지 않는다.
- [ ] `& $petasosPython -m unittest tests.test_module_library -v`: FAIL 확인.
- [ ] ZIP 헤더와 실제 스트리밍 크기를 모두 검사하고 임시 디렉터리에서 검증 후 원자적 등록.
  허용 파일은 manifest JSON과 필요한 STL/OBJ/MTL/PNG/JPG로 한정하고,
  OBJ/MTL 외부 참조는 같은 아카이브 안의 검증된 상대 경로만 허용한다.
- [ ] 테스트 PASS 확인. 실패 후 라이브러리/프로젝트 외부에 파일이 생기지 않았는지 검사한다.
- [ ] 커밋: `feat: add safe local robot module library`.

### Task 4: 장착·교체 트랜잭션과 실행 취소 상태

**Files:** `module_service.py`, `tests/test_module_service.py` 생성;
`server.py`의 ProjectStore에 revision/state 적용 경계 추가.

**Interfaces:**
- `prepare_module_operation(state: dict, tree: dict, payload: dict, *, parent_link_id: str,
  prefix: str, xyz_m: list[float], rpy_rad: list[float], replace_id: str | None = None) -> dict`.
- 반환 `{state, tree, module_id, name_map, changes}`. 입력 객체 변경 금지; 모든 참조를 ID/이름 매핑으로 갱신.
- `ModuleService(store: ProjectStore, library: ModuleLibrary)`의
  `apply(request: dict, expected_revision: int) -> dict`, `restore(snapshot_id: str, expected_revision: int) -> dict`.
- 결과 `{tree, revision, undo_snapshot_id, changes}`. 서버 스냅샷은 전체 프로젝트 상태와 메시 참조를 보존한다.
  브라우저에는 전체 물성 데이터 대신 복원 토큰을 전달한다. 메시 파일은 즉시 지우지 않는다.

- [ ] `test_attach_twice_remaps_every_reference`에서 이름·ID 중복 0개, 모든 mimic/controller 참조가
  실제 조인트로 연결되는지 검사한다.
  `test_replace_preserves_body_and_attachment`에서 모듈 외 데이터와 mount 설정이 완전히 같은지 검사한다.
  `test_failed_replace_and_stale_revision_leave_state_unchanged`, `test_restore_recovers_previous_module` 추가.
- [ ] `& $petasosPython -m unittest tests.test_module_service -v`: FAIL 확인.
- [ ] Task 1–3 인터페이스를 조합해 미리 계산/검증하고, revision 비교 후 한 번에 저장한다.
  실패한 작업은 프로젝트 JSON과 활성 메시 참조를 변경하지 않는다.
- [ ] 테스트 PASS 확인. 저장/재로드 뒤 restore 토큰의 처리 정책도 검사한다:
  세션 종료 시 undo 기록은 비우되 저장된 현재 프로젝트와 모듈 데이터는 유지한다.
- [ ] 커밋: `feat: attach and replace modules atomically`.

### Task 5: 모듈 API와 편집 수명주기 보호

**Files:** `server.py`, `reimporter.py` 수정; `tests/test_module_api.py` 생성.

**Interfaces:**
- `POST /modules/validate`: `{tree, link_ids, joint_ids, editing_id}` → Task 1 검증 결과.
- `POST /modules/create`, `/modules/update`, `/modules/unassign`: tree와 revision을 받아 검증된 tree/revision 반환.
- `GET /modules/library`, `POST /modules/library/save`, `/modules/library/import`,
  `GET /modules/library/<id>/download` → Task 3 라이브러리.
- `POST /modules/preview`, `/modules/apply`, `/modules/restore` → Task 4 미리보기/적용/복원.
- 유효성 오류 400, 상태 충돌 409, 용량 초과 413. 오류는 `{error, details}` 구조.

- [ ] Flask client로 `test_create_save_import_attach_replace_restore_flow` 작성.
  `test_invalid_module_workspace_and_reimport_are_not_saved`에서 ID 소속을 깨뜨린 저장/재가져오기/익스포트가
  거부되고 원래 상태가 유지되는지 검사한다. 파일 업로드 에러 코드와 절대 경로 비노출도 검사한다.
- [ ] `& $petasosPython -m unittest tests.test_module_api -v`: FAIL 확인.
- [ ] 기존 Flask 패턴으로 endpoint를 연결한다. 기존 프로젝트의 revision 없는 요청은 모듈 기능
  미사용 경로에서 계속 지원하며, 모듈 편집 요청에는 revision을 요구한다.
- [ ] 모듈 API 및 기존 `tests.test_standalone` 실행: PASS 확인.
- [ ] 커밋: `feat: expose module lifecycle APIs with revision checks`.

### Task 6: 수동 선택 UI·속성·라이브러리

**Files:** `module_selection.js`, `tests/test_module_selection.cjs` 생성;
`web_ui.py`의 renderPatcher/saveState/undo/선택 속성 수정; `server.py`에 해당 JS 정적 경로 연결.

**Interfaces:**
- 순수 함수 `toggleModuleSelection(selection, kind, id)`,
  `selectModuleRect(selection, entries, rect, additive)` → `{linkIds, jointIds}`.
- 브라우저 연결 함수 `enterModuleSelection(moduleId = null)`, `submitModuleSelection()`,
  `renderModuleProperties(moduleId)`, `openModuleLibrary()`.
- entry 좌표는 트리 canvas 로컬 좌표. zoom/pan을 역변환한 뒤 카드/라벨 중심으로 판정한다.

- [ ] Node 내장 테스트에서 `ctrl toggles one ID`, `rectangle selects centers only`,
  `ctrl rectangle adds`, `zoom/pan does not change members`의 `deepStrictEqual` 기대값을 작성한다.
  joint 배선이 영역을 통과하되 라벨이 밖인 경우 미선택임을 검사한다.
- [ ] `node --test tests/test_module_selection.cjs`: FAIL 확인. Node 미발견 시 확인된 번들 실행파일 사용.
- [ ] 선택 모드, 목록 확인, 오류 항목 강조, 색상 배지, 외곽선, 컨트롤러와 분리된 라벨 배치 구현.
  속성 XYZ(mm)/RPY(deg), 범위 수정/해제, 라이브러리 저장·가져오기·장착·교체 미리보기를 연결한다.
  기존 undo는 모듈 상태 토큰을 포함한 기록 유형을 지원하고, 서버 실패 시 UI 기록을 되돌린다.
- [ ] Node 테스트 PASS 및 Python 전체 회귀 테스트. 브라우저에서 Ctrl/드래그/ESC/모드 전환/
  축소·확대/저장·복원/한 번의 undo를 수동 검증하고 결과를 기록한다.
- [ ] 커밋: `feat: add manual module selection and library UI`.

### Task 7: 모듈별 Xacro와 동일 형상 익스포트

**Files:** `module_export.py`, `tests/test_module_export.py` 생성;
`Structure.py` apply_tree_data/standardize_names, `Write.py`, `exporter.py` 수정.

**Interfaces:**
- `RobotStructure.export_name_map` = `{links: {id:name}, joints: {id:name}}`, 이름 표준화 후 완성.
- `resolve_module_exports(tree: dict, name_map: dict) -> list[dict]`.
- `write_module_xacros(description_dir: Path, modules: list[dict]) -> dict`:
  생성된 Xacro XML을 파싱해 소유 링크·내부 조인트를 매크로로 옮기고 include/호출로 대체한다.
  ros2_control 내부 조인트도 별도 매크로로 옮기되 블록 자체는 중복 생성하지 않는다.
- 모듈 내부 이름은 prefix 매크로 인자를 사용하고 모든 parent/child/mimic 참조가 이를 따른다.
  mount 조인트는 최상위에 남는다. meshes URI는 실제 설치 경로와 일치하도록 생성한다.

- [ ] `test_module_expansion_matches_flat_robot` 작성: fixture의 flat Xacro와 modular Xacro를
  실제 xacro로 확장 후 링크·조인트 집합, FK, 질량·관성, mesh URI, mimic, control interface를 비교한다.
  `test_renamed_and_twice_instanced_modules_have_no_duplicate_names`와
  `test_export_without_modules_remains_unchanged` 추가한다.
- [ ] `& $petasosPython -m unittest tests.test_module_export -v`: FAIL 확인.
  Xacro 의존성 부재를 PASS로 취급하지 않는다. Windows Python에 test용 xacro를 사용할지
  기존 WSL Humble 실행파일을 사용할지 환경 확인 후 지정한다.
- [ ] 기존 링크 직렬화 결과를 재사용해 모듈 분할 구현. export 디렉터리를 지우기 전에 모듈
  검증을 먼저 수행한다. visual/collision 메시 처리 정밀도는 변경하지 않는다.
- [ ] 위 테스트 PASS 및 기존 구조/익스포트 테스트. 각 mesh URI가 실제 파일로 해석되는지 검사한다.
- [ ] 커밋: `feat: export reusable Xacro modules without changing robot geometry`.

### Task 8: 컨트롤러·MoveIt 이름 및 제어 참조 일치

**Files:** `exporter.py`, `moveit/generate_smoke_config.py`, `moveit/validate_moveit_config.py`,
`moveit/validate_urdf.py`, `tests/test_module_export.py` 수정.

**Interfaces:** Task 7의 최종 이름 매핑과 기존 controller_groups 입력 계약을 사용한다.
모듈 여부가 아니라 controller type을 기준으로 MoveIt 액션 구성을 결정한다.

- [ ] `test_replaced_module_leaves_no_old_joint_references` 작성: YAML/SRDF/ros2_control에 이전
  모듈 이름이 없고 새 이름만 존재해야 한다.
  `test_position_only_module_does_not_request_velocity`와
  `test_unsupported_module_controller_fails_explicitly` 추가한다.
- [ ] `& $petasosPython -m unittest tests.test_module_export -v`: FAIL 확인.
- [ ] JTC와 Position/Effort GripperActionController의 이름·조인트·액션을 타입별로 생성한다.
  GripperCommand는 단일 구동 관절과 내부 mimic 구조를 사용하며, 여러 구동 관절을 단일
  GripperCommand로 임의 축약하지 않는다. 다른 타입은 지원하지 않는 MoveIt 제어 경로임을 명시한다.
  SRDF/컨트롤러 잔존 참조를 검증하고, 교체 후 Assistant 수동 설정 재검토 안내를 표시한다.
- [ ] 모듈 및 기존 MoveIt 테스트 PASS. position-only와 position+velocity 각각 생성 결과 검사.
- [ ] 커밋: `fix: keep module control and MoveIt references consistent`.

### Task 9: 전체 회귀·사용 흐름 검증과 문서

**Files:** `README.md`, `QUICKSTART_KO.md` 수정; 결과 기록
`docs/superpowers/verification/2026-09-28-reusable-robot-modules.md` 생성.

**Interfaces:** 앞 Task의 API·UI·출력만 사용한다. 제품 구조 변경을 이 단계에 추가하지 않는다.

- [ ] 기존 프로젝트 → 수동 모듈 지정 → 저장 → 새 프로젝트 장착 → 같은 모듈 재장착 → 교체 →
  undo → 저장/재로드 → 익스포트의 end-to-end 확인 항목과 기대 결과를 기록한다.
- [ ] `& $petasosPython -m unittest discover -s tests`와
  `node --test tests/test_module_selection.cjs` 실행. 테스트 수와 실패 0개를 기록한다.
- [ ] WSL 접근 가능 시 확장된 URDF를 RViz에서 확인하고 지원 그리퍼 구성으로 MoveIt 컨트롤러
  활성 상태/Plan/Execute를 각각 검사한다. 실물 로봇 구동은 하지 않는다.
  WSL 접근 불가면 정확한 제한을 기록하고 실행 성공을 주장하지 않는다.
- [ ] 문서에 선택 규칙, 라이브러리 위치, 단위, 끝단 제약, 교체 후 재익스포트/MoveIt 재실행,
  외부 참조 오류 해결법을 작성한다. `git diff --check`와 비밀정보/생성물 포함 여부를 점검한다.
- [ ] 변경 전체 리뷰에서 spec 누락과 회귀를 확인하고 커밋한다. 로컬 통합·PR·push 등은
  finishing-a-development-branch 절차에 따라 사용자의 선택을 받는다.

## 실행 전 검토 및 인계

- Spec 1–4 → Task 1, 4–6 / Spec 5–6 → Task 1–4 / Spec 7 → Task 7–8 /
  Spec 8 → Task 3–5 / Spec 9 → Task 1–9에 대응한다.
- 모든 신규 함수를 먼저 실패하는 테스트로 고정하고 구현한다.
- 사용자 계획 승인과 실행 방식 선택 전에는 제품 코드를 수정하지 않는다.
- 추천 실행 방식은 Native: 프로젝트 상태·UI undo·ID·출력이 순차 의존하므로 같은 작업자가
  구현을 이어가는 편이 적합하다. 대안은 Task별 구현/리뷰 에이전트를 분리하는 방식이다.
