<img width="1024" height="531" alt="image" src="https://github.com/user-attachments/assets/bf6df849-92bf-4627-af39-4d254a0eda39" />


사용법: https://youtu.be/H9movJFO4Fs

# Petasos URDF Exporter

Petasos는 CAD 조립품을 불러와 로봇의 링크와 조인트 구조를 편집하고, ROS 2용 URDF 패키지로 내보내는 도구입니다.


## 주요 기능

- Autodesk Inventor IAM/IPT 직접 연결 및 파일 가져오기
- STEP, BREP, IGES, STL 형식 가져오기
- 3D 부품 선택, 링크 그룹화, 조인트 연결 및 재설정
- 바닥면과 월드 원점 지정
- ROS 2 Humble용 description 패키지 생성
- 선택형 MoveIt 설정, 검사 및 실행 지원
- WSL2 환경에서 RViz 동기화 및 실행
- 이름별 편집 작업 저장과 복원

## 실행

처음 사용하는 컴퓨터에서는 다음 파일을 실행해 필요한 환경을 점검하고 설치합니다.

```text
setup_petasos.cmd
```

설정이 끝난 뒤 편집기를 실행합니다.

```text
start_petasos.cmd
```

브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:5050/`에 접속하세요. 명령 창을 닫으면 Petasos 서버도 종료됩니다.

## 기본 작업 순서

1. CAD 조립품 또는 이전 편집 작업을 불러옵니다.
2. 3D 뷰어에서 모델 방향과 바닥면·원점을 확인합니다.
3. 구조 트리에서 부품을 링크로 그룹화합니다.
4. 부모 링크와 자식 링크의 연결점을 지정하고 조인트를 연결합니다.
5. 조인트 종류, 축, 제한값과 동역학 값을 설정합니다.
6. 출력 유형을 선택하고 `URDF 생성`을 누릅니다.
7. 결과 화면에서 RViz 또는 MoveIt 검사를 실행합니다.

## 지원 입력

- Autodesk Inventor: IAM/IPT 직접 연결
- 범용 CAD 교환 형식: STEP, STP, BREP, IGES, IGS
- 메시: STL
- Petasos 조립 교환 형식: `*.petasos.json`

다른 CAD의 전용 조립품 형식은 해당 CAD에서 조립 구조를 유지한 STEP 파일로 내보낸 뒤 가져오는 방식을 권장합니다.

## 출력 구조

ROS 2 출력은 기본적으로 다음 위치에 생성됩니다.

```text
export/ros_ws/src/
```

description 패키지는 RViz에서 확인할 수 있습니다. MoveIt 출력을 선택하면 같은 작업공간에 MoveIt 설정 패키지가 함께 생성됩니다.

## 프로젝트 구성

- `URDF_Exporter/standalone`: 로컬 서버, CAD 변환 및 URDF 출력
- `URDF_Exporter/core`: Fusion 360 내보내기 기반 코드와 공통 구조 처리
- `moveit`: MoveIt 설정 검사와 WSL 실행 지원
- `tools`: Windows, WSL2, ROS 2 설치 도우미
- `tests`: 자동 회귀 테스트
- `examples`: Petasos 조립 교환 형식 예제
- `schemas`: Petasos 조립 교환 형식 스키마

## 원본 프로젝트 고지

이 프로젝트의 일부 Fusion 360 내보내기 코드는 Toshinori Kitamura가 제작한 [syuntoku14/fusion2urdf](https://github.com/syuntoku14/fusion2urdf)를 기반으로 수정되었습니다. 해당 원본 코드는 MIT License로 배포됩니다.

Petasos에서 새로 작성되거나 확장된 부분의 저작권은 Petasos contributors에게 있습니다. 자세한 라이선스 조건은 [LICENSE](LICENSE)를 확인하세요.
