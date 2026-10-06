# Petasos Export Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 충돌 원인, 내보낸 값의 일치 여부, 모듈별 MoveIt 그룹을 정확하게 생성·검사한다.

**Architecture:** 기존 exporter의 트랜잭션과 analysis 출력에 세 가지 작은 검사/설정 모듈을 연결한다. URDF 해석·순기구학은 공유하고, ROS 실동작 검증은 별도 도구로 실행한다.

**Tech Stack:** Python, numpy, trimesh, ElementTree, pytest/unittest; 선택적 xacro·ROS 2 Humble rclpy/MoveIt 서비스.

**Spec:** `docs/superpowers/specs/2026-10-03-export-integrity-design.md`

## Global Constraints

- 기존 UI 디자인과 버튼 크기는 유지한다.
- 현재 폴더의 미커밋 변경과 사용자가 지정한 모듈 범위를 보존한다.
- ROS 2 Humble의 현재 실행 경로를 유지하며 Gazebo 버전 이전은 포함하지 않는다.
- XYZ/COM은 미터, 각도는 라디안이다. 비교는 절대 오차 1e-8, 상대 오차 1e-6을 기본으로 한다.
- 기존 Assistant 작성 설정은 재생성 시 덮어쓰지 않는다.
- 단순 경고와 실제 판정, 정적 검사와 실동작 검사를 구분한다.
- 현재 폴더에서 직접 구현한다. 기존 변경과 혼합되는 자동 커밋은 하지 않는다.

## Review Focus

1. mesh 경로의 package URI, scale 및 collision origin을 반영하지 않으면 월드 bounds가 틀린다.
2. mimic 순환·체인·offset 및 제한 밖 영점을 조용히 다른 값으로 대체하면 안 된다.
3. 모듈 외부 부착 조인트와 고정 센서를 구동 그룹에 잘못 넣으면 안 된다.
4. xacro/ROS/정밀 충돌 라이브러리 부재는 성공이나 비충돌이 아니라 미검증이다.
5. export 재실행 및 이름 정규화 충돌이 기존 Assistant 설정을 손상시키면 안 된다.

## Task 1: 정적 충돌 진단 및 공유 URDF 해석

**Files:**
- Create: `URDF_Exporter/standalone/urdf_analysis.py`
- Create: `URDF_Exporter/standalone/collision_diagnostics.py`
- Modify: `URDF_Exporter/standalone/exporter.py`
- Test: `tests/test_collision_diagnostics.py`, `tests/test_export_transaction.py`

**Interfaces:**
- `load_robot(path: Path) -> Element`: plain URDF는 직접 해석, xacro는 펼침. 펼치기 실패는 명시적 오류.
- `zero_positions(robot: Element) -> dict[str, float]`: 독립축 0과 mimic 식을 계산, 순환·제한 오류 검출.
- `world_transforms(robot: Element, positions: dict[str, float]) -> dict[str, ndarray]`: origin 및 가동 변환 포함.
- `diagnose_collision_meshes(robot: Element, package_dir: Path, srdf: Element | None = None) -> dict`: mesh 정보, 월드 bounds, 의심 링크 쌍, 제외 이유, 정밀 검사 상태.

- [ ] 정적 테스트 작성: 분리된 box의 의심 쌍 없음; 겹치는 AABB의 상태 `suspected_overlap`; AABB가 겹쳐도 정밀 검사 없으면 실제 충돌 확정 없음.
- [ ] 경로/scale/origin 반영, 빈 mesh, NaN 좌표, 누락 mesh, 폐곡면 여부 테스트 작성. mimic 체인·순환·offset·제한 위반 테스트도 공유 해석기에 포함.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_collision_diagnostics.py -q` 실행해 새 구현 부재로 실패 확인.
- [ ] 위 인터페이스 구현. 제외 대상도 보고하고 AABB 결과로 SRDF를 변경하지 않는다. optional FCL 미설치는 `unverified`로 처리한다.
- [ ] exporter에서 최종 생성 로봇을 해석해 `analysis/collision_diagnostics.json` 저장. 보고서 경로를 export 결과에 추가하며 오류를 기존 결과 표시 흐름에 전달한다.
- [ ] 같은 테스트와 트랜잭션 테스트 실행: 진단 실패 시 기존 export 보존, 의심만으로 정상 export 차단 안 함 확인.

## Task 2: 익스포트 일치 및 ROS 실동작 검증

**Files:**
- Create: `URDF_Exporter/standalone/export_consistency.py`
- Create: `moveit/check_export_runtime.py`
- Modify: `URDF_Exporter/standalone/exporter.py`, `moveit/generate_smoke_config.py`
- Modify: `moveit/check_mimic_runtime.py` (공통 순수 검증 함수 재사용만)
- Test: `tests/test_export_consistency.py`, `tests/test_export_runtime.py`, `tests/test_mimic_control_export.py`

**Interfaces:**
- Consumes: Task 1의 `load_robot`, `zero_positions`, `world_transforms`.
- `compare_export(expected: dict, robot: Element, atol: float = 1e-8, rtol: float = 1e-6) -> dict`: 정규화 기준과 생성 모델의 항목별 차이, 허용 오차, 정적 상태 반환.
- `check_observed_positions(robot: Element, observed: dict[str, float], atol: float = 1e-6) -> dict`: 누락 축·영점·mimic 값 검사. 누락을 0으로 채우지 않음.
- `check_state_validity(robot: Element, srdf: Element | None, positions: dict[str, float], timeout: float = 10.0) -> dict`: ROS 서비스의 actual contact 또는 미검증 반환.

- [ ] 동일 모델 통과, Euler 표현만 다른 동일 회전 통과, COM/관성/축/limit/mimic 차이 검출 테스트 작성. 예상 모델은 출력 파일을 재읽어 만드는 것이 아니라 exporter의 정규화 구조에서 생성한다.
- [ ] 관측 joint_states 누락, mimic offset, 실제 충돌 contact, ROS import 실패, 서비스 timeout 테스트 작성. ROS 경계는 mock으로 검사한다.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_export_consistency.py tests/test_export_runtime.py -q` 실패 확인.
- [ ] compare_export 구현; 조인트 위치·회전행렬·월드 축·영점 FK와 link 물성을 모두 비교. 최종 xacro 펼침 미검증 시 일치 통과로 처리하지 않는다.
- [ ] `analysis/export_consistency.json` 출력과 구조 불일치 차단을 트랜잭션 내 연결. zero_positions를 사용해 초기값 중간값 대체 경로 제거.
- [ ] ROS 도구 구현: bounded service wait, contacts와 검사 자세 기록, joint_states 비교, 미검증 exit code 2. 기본 진단은 실제 로봇 제어 명령을 보내지 않는다.
- [ ] portable helper에 도구 포함. 실행 보고서의 정적 검사와 runtime 상태를 분리하고 한국어 요약 제공.
- [ ] 새 테스트, mimic 기존 테스트, `tests/test_export_preflight.py`, `tests/test_export_transaction.py` 실행.

## Task 3: 모듈별 MoveIt 설정과 사용자 설정 보존

**Files:**
- Create: `URDF_Exporter/standalone/moveit_groups.py`
- Modify: `URDF_Exporter/standalone/exporter.py`, `moveit/generate_smoke_config.py`, `moveit/smoke_plan.py`
- Modify: `moveit/validate_moveit_config.py`
- Test: `tests/test_moveit_groups.py`, `tests/test_standalone.py`, `tests/test_export_transaction.py`

**Interfaces:**
- `resolve_planning_groups(tree: dict, name_map: dict, joints: dict, controllers: list[dict]) -> list[dict]`: 각 항목은 name, joints, driven_joints, role, chain_supported, warnings 포함.
- generate_smoke_config에 `planning_groups: list[dict] | None = None` optional 인자 추가. None일 때 기존 arm/home 호환 유지.
- Consumes: Task 1 zero_positions와 Task 2 보고서. 외부 attachment joint는 내부 조인트 목록에서 제외.

- [ ] 팔+그리퍼 분리, mimic 직접 제어 제외, fixed 센서 제외, 모듈 없음 arm 유지 테스트 작성.
- [ ] 정규화 이름 충돌, 외부 부착축, 분기 구조 KDL 비활성, 빈 arm, 기존 Assistant 파일 바이트 보존 테스트 작성.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_moveit_groups.py -q` 실패 확인.
- [ ] 그룹 해석 구현: 안정 ID를 name_map으로 매핑하고 컨트롤러로 그리퍼 역할 판별. 그룹에 제어가 불가능한 이동 모듈은 제외 이유 명시.
- [ ] SRDF groups/home, kinematics, controller mapping, smoke 검사 대상 목록을 동일 그룹 명세에서 생성. 분기 및 그리퍼에는 일괄 KDL 적용하지 않는다.
- [ ] 기존 설정이 있으면 새 생성 결과는 별도 sibling staging 패키지와 차이 보고서로 출력하고 기존 설정 유지. 트랜잭션이 기존 패키지를 삭제하지 않도록 통합 테스트로 확인.
- [ ] 단일 기본 smoke 그룹 선택은 arm 우선, 없으면 지원되는 그룹 선택; 여러 그룹은 명시적 대상 목록으로 검사. 기존 명령 옵션 유지.
- [ ] 그룹 테스트와 standalone/export/mimic 회귀 테스트 실행.

## Final Verification

- [ ] `.venv\Scripts\python.exe -m pytest tests -q` 및 기존 Node 테스트 실행. 기존 실패와 신규 회귀를 구분해 기록한다.
- [ ] `git diff --check` 및 변경 Python 파일 컴파일 검사.
- [ ] 합성 팔+그리퍼 프로젝트 익스포트 결과에서 보고서와 SRDF/controller/kinematics 실제 파일 확인.
- [ ] WSL ROS 환경이 사용 가능하면 생성 모델의 state validity와 joint_states를 검사. 불가능하면 실제 ROS 검증은 미검증으로 보고한다.
- [ ] 사용자 변경 보존과 UI 디자인 무변경을 diff로 확인하고 잔여 한계를 명시한다.
