# A4 실행 흐름 재점검 — 2026-10-04

대상은 현재 사용 중인 A4와 `new_robot` 프로젝트다. 기존 테스트 통과에 더해 실제 서버, 브라우저 UI 및 현재 프로젝트의 패키지 생성을 확인했다.

## 확인 및 수정

1. 실행 중인 서버의 `/` 응답에 이전 수정의 mimic 버튼 코드가 없었다. 디스크 수정이 실행 프로세스에 반영되지 않은 상태였다. 저장된 트리와 서버 트리가 일치함을 확인하고 프로젝트 JSON을 백업한 뒤, 해당 A4 서버만 재시작했다. `/health` 정상, 최신 UI 코드 제공 및 재시작 전후 트리 동일성을 확인했다. 브라우저의 기존 화면은 새로고침해야 최신 스크립트를 읽는다.
2. JSON 배열·문자열·숫자·boolean 및 잘못된 `tree` 형식이 일부 저장/익스포트/모듈 경로에서 `AttributeError`와 HTTP 500을 발생시켰다. 요청 진입점에서 JSON 객체 형식을 확인하고 HTTP 400 JSON 오류를 반환하도록 수정했다. 깨진 JSON도 같은 방식으로 처리한다. 정상 JSON 객체, multipart 업로드 및 본문 없는 GUI 요청의 동작은 유지한다.

추가한 `test_api_input_validation.py`의 2개 테스트는 수정 전 실패와 예외를 재현했으며, 수정 후 통과했다. 여러 경로·입력을 subtest로 검사한다. 별도 코드 검토에서는 이 수정으로 인한 추가 문제를 찾지 못했다.

## 브라우저 실행 검증

별도 headless Edge에서 실제 Three.js 화면을 로드하고 언어 전환, 9개 조인트 라벨 선택, 2개 컨트롤러 라벨 선택, 구조 노드 선택, 재질 선반, 컨트롤러·모듈 지정/취소 및 자동 정렬을 실행했다. 선택·툴바 동작 52개와 언어 전환을 점검했고 JavaScript 오류는 없었다.

검사용 브라우저의 모든 POST는 가상 응답으로 처리해 실제 작업과 파일을 변경하지 않았다. 따라서 이 UI 점검 자체가 서버 저장·익스포트 성공을 입증하지는 않는다. 해당 경로는 별도의 API 회귀 테스트와 아래 실제 익스포트 점검으로 검증했다.

## 실제 프로젝트 익스포트

원본 `project_state.json`, 57개 부품 및 서버에서 읽은 현재 트리로 실제 `prepare_export`를 실행했다. 임시 export root에만 패키지를 만들었고 완료 후 후보를 취소했다. 최종 사용자 export는 덮어쓰지 않았다.

| 결과 | 검사 링크 | 차단 오류 | 경고 |
|---|---:|---:|---:|
| 기본 description | 13 | 0 | 13 |
| MoveIt 포함 | 13 | 0 | 5 |

두 결과 모두 정밀 충돌 검사 미검증 항목은 0개다. 기본 패키지의 추가 경고 8개는 연결된 가동 링크 간 영점 접촉이며, MoveIt 결과에서는 SRDF의 충돌 제외 설정이 적용된다.

두 결과에 남는 5개 경고는 원본 형상 문제다.

- `link_1`: 열린 면 경계 107개.
- `link_6`: 열린 면 경계 232개, 비다양체 모서리 7개.
- `link_7`, `link_8`: 각각 열린 면 경계 296개, 비다양체 모서리 101개.
- `Camera_link`: 비다양체 모서리 160개.

이 경고를 없애기 위해 CAD 형상을 임의로 메우거나 충돌 검사를 비활성화하지 않았다. 원본 CAD의 중복 면·겹침·구멍 및 충돌용 형상을 검토할 필요가 있다.

## 최종 검증 기록

- Python 전체: **235개 통과** — `.test-tmp/debug2-final-python.log`.
- JavaScript 전체: **34개 통과** — `.test-tmp/debug2-final-js.log`.
- 실제 프로젝트 검사: `.test-tmp/debug2-real-description-report.json`, `.test-tmp/debug2-real-moveit-report.json`.
- 최신 코드 및 실제 재시작 서버 UI: `.test-tmp/debug2-latest-browser-report.json`, `.test-tmp/debug2-live-browser-report.json`.
- 프로젝트 백업: `.test-tmp/debug2-project-state-backup.json`.
- 재시작 서버 로그: `.test-tmp/debug2-server.stdout.log`, `.test-tmp/debug2-server.stderr.log`.
- `git diff --check` 통과.

실제 Inventor COM 재연결, WSL MoveIt 경로 계획·실행 및 실제 로봇 구동은 이번 점검에 포함하지 않았다. 브라우저 UI 점검은 사용자가 열어둔 브라우저를 조작하지 않고 별도 세션에서 수행했다.
