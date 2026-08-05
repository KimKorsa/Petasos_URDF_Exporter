# Petasos A2 MoveIt 시험 영역

A2는 일반 URDF 익스포터인 A1과 분리하여 다음 흐름을 시험합니다.

1. Petasos에서 ROS 2 description 패키지를 익스포트합니다.
2. `WSL Humble에서 MoveIt Assistant 열기`를 누릅니다.
3. Assistant에서 planning group, self-collision matrix와 controller를 설정합니다.
4. 패키지 생성 위치는 아래 형식을 사용합니다.

   `~/petasos_moveit_ws/src/<robot_name>_moveit_config`

5. Assistant를 닫고 Petasos에서 `2. 생성 결과 검사·실행`을 누릅니다.
6. RViz와 MoveGroup이 준비되면 `3. 움직임 자동검사`를 누릅니다.

실행 단계에서는 Humble 2.5 계열 Setup Assistant가 `1.0`을 YAML 정수 `1`로
기록하는 문제를 검사합니다. `joint_limits.yaml`의 MoveIt 실수 파라미터만
안전하게 `1.0` 형식으로 보정한 뒤 패키지를 빌드하고 `demo.launch.py`를
실행합니다. 자동검사는 첫 planning group과 현재 관절 상태를 읽고, 각 관절
리밋 안에서 작은 목표를 만든 뒤 OMPL 계획과 가상 컨트롤러 실행을 모두
확인합니다.

URDF의 0 rad가 관절 리밋 밖인 경우에는 `ros2_control` 초기값을 해당 범위의
중앙으로 자동 지정합니다. 이를 통해 MoveIt이 시작하자마자
`START_STATE_INVALID`가 되는 문제를 방지합니다.

## 자동 방어

- 익스포트 단계에서 단일 루트, 링크 연결, 사이클, 중복 부모를 검사합니다.
- 가동 조인트의 축, lower/upper, effort, velocity를 검사합니다.
- `continuous` 조인트에도 URDF 필수 limit 정보를 생성합니다.
- 모든 `ros2_control` 초기값이 해당 관절 리밋 안에 들어가도록 보정합니다.
- 기본 속도·가속도는 `1.0`, 기본 effort는 `100.0`의 실수형으로 기록합니다.
- `analysis/moveit_readiness.json`에 검사 결과를 함께 저장합니다.
- Assistant 실행 직전 xacro를 실제 URDF로 확장해 다시 검사합니다.
- Assistant 결과에서 SRDF Planning Group, FollowJointTrajectory,
  JointTrajectoryController와 joint_state_broadcaster를 검사합니다.
- MoveIt YAML의 실수형 필드가 정수로 저장되면 실행 전에 `.0` 형식으로
  자동 보정합니다.
