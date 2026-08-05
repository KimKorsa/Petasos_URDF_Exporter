# Petasos A2 빠른 시작

## 처음 설치

압축 파일 안에서 직접 실행하지 말고 프로젝트 폴더를 먼저 완전히 압축 해제합니다. 이후 프로젝트 루트에서 다음 파일을 실행합니다.

```text
setup_petasos.cmd
```

설치 도우미는 다음 항목을 검사하고, 필요한 경우 사용자 확인을 받은 뒤 설치를 진행합니다.

- Python과 프로젝트 전용 `.venv`
- Autodesk Inventor 직접 연결
- WSL2와 Ubuntu 22.04
- ROS 2 Humble, RViz, MoveIt, ros2_control, Gazebo
- colcon, rosdep, xacro

Windows 기능을 처음 활성화한 경우 재부팅이 필요할 수 있습니다. Ubuntu를 처음 설치한 경우 Linux 사용자명과 비밀번호를 한 번 생성한 뒤 `setup_petasos.cmd`를 다시 실행합니다.

## 편집기 실행

```text
start_petasos.cmd
```

명령 창이 실행 중인 동안 `http://127.0.0.1:5050/`에서 편집기를 사용할 수 있습니다. 명령 창을 닫으면 서버도 종료됩니다.

## 조립품 불러오기

- Inventor에서 IAM을 열어 둔 경우 `현재 열린 Inventor 조립품`을 사용합니다.
- IAM 파일을 직접 지정하려면 `원본 IAM 경로 선택`을 사용합니다.
- 다른 CAD에서는 조립 구조를 유지한 STEP 파일을 권장합니다.
- STL, BREP, IGES 또는 `*.petasos.json`도 가져올 수 있습니다.

IAM이 참조 IPT를 찾지 못하면 Inventor의 Resolve 또는 Pack and Go로 참조를 정상화한 뒤 다시 가져옵니다.

## URDF 생성

1. 바닥면과 원점을 지정합니다.
2. 부품을 링크로 그룹화합니다.
3. 링크 사이 조인트와 부모·자식 연결점을 설정합니다.
4. 조인트 종류, 축, 제한값과 동역학 값을 확인합니다.
5. 출력 유형을 선택하고 `URDF 생성`을 누릅니다.
6. 결과 화면에서 RViz 또는 MoveIt 검사를 실행합니다.

생성 결과는 `export/ros_ws/src`에 정리됩니다.
