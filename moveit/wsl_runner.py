from __future__ import annotations

import re
import shlex
import subprocess
import threading
import json
from pathlib import Path


WSL_MOVEIT_DISTRO = "Ubuntu-22.04"
WSL_MOVEIT_DOMAIN_ID = 42
MOVEIT_ASSISTANT_MARKER = "PETASOS_MOVEIT_ASSISTANT"
MOVEIT_DEMO_MARKER = "PETASOS_MOVEIT_DEMO"


def _windows_path_to_wsl(path: Path) -> str:
    windows_path = Path(path).resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", windows_path):
        raise ValueError(f"WSL로 전달할 수 없는 Windows 경로입니다: {path}")
    return f"/mnt/{windows_path[0].lower()}/{windows_path[3:]}"


def _validate_ros_package(package_dir: Path) -> str:
    package_name = package_dir.name
    if not re.fullmatch(r"[a-z][a-z0-9_]*", package_name):
        raise ValueError(f"올바르지 않은 ROS 2 패키지 이름입니다: {package_name}")
    if not (package_dir / "package.xml").is_file():
        raise ValueError("내보낸 ROS 2 패키지에서 package.xml을 찾지 못했습니다.")
    return package_name


def _robot_details(package_dir: Path) -> tuple[str, Path]:
    package_name = _validate_ros_package(package_dir)
    robot_name = (
        package_name[:-len("_description")]
        if package_name.endswith("_description")
        else package_name
    )
    xacro_dir = package_dir / "urdf"
    preferred = xacro_dir / f"{robot_name}.xacro"
    if preferred.is_file():
        return robot_name, preferred.relative_to(package_dir)
    candidates = sorted(
        path
        for path in xacro_dir.glob("*.xacro")
        if not path.name.endswith(".gazebo.xacro")
    )
    if not candidates:
        raise ValueError("MoveIt Assistant에 전달할 로봇 xacro 파일을 찾지 못했습니다.")
    return candidates[0].stem, candidates[0].relative_to(package_dir)


class WslMoveItRunner:
    """Runs the A2 MoveIt Assistant and generated demo inside WSL Humble."""

    def __init__(
        self,
        helper_path: Path,
        distro: str = WSL_MOVEIT_DISTRO,
    ):
        self.distro = distro
        self.helper_path = Path(helper_path).resolve()
        self.smoke_helper_path = self.helper_path.with_name("smoke_plan.py")
        self.urdf_helper_path = self.helper_path.with_name("validate_urdf.py")
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._linux_pid: int | None = None
        self._stop_requested = False
        self._mode: str | None = None
        self._expected_config_path: str | None = None
        self._robot_name: str | None = None
        self._description_package: str | None = None
        self._config_package: str | None = None
        self._workspace_dir: Path | None = None
        self._workspace_wsl_path: str | None = None
        self._smoke_result: dict | None = None
        self._assistant_validation: dict | None = None
        self._status = "idle"
        self._message = "MoveIt 테스트 대기 중"
        self._output: list[str] = []

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "message": self._message,
                "mode": self._mode,
                "expected_config_path": self._expected_config_path,
                "smoke_result": self._smoke_result,
                "assistant_validation": self._assistant_validation,
                "output": self._output[-30:],
            }

    def _set_state(self, status: str, message: str) -> None:
        with self._lock:
            self._status = status
            self._message = message

    def _ensure_available(self) -> None:
        result = subprocess.run(
            [
                "wsl.exe",
                "-d",
                self.distro,
                "--",
                "bash",
                "-lc",
                (
                    "source /opt/ros/humble/setup.bash && "
                    "test -x /opt/ros/humble/lib/moveit_setup_assistant/"
                    "moveit_setup_assistant && "
                    "ros2 pkg prefix moveit_ros_move_group >/dev/null"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                "Ubuntu 22.04에 MoveIt 또는 MoveIt Setup Assistant가 없습니다."
                + (f" ({detail})" if detail else "")
            )

    def _spawn(
        self,
        script: str,
        *,
        mode: str,
        preparing_message: str,
    ) -> dict:
        self._ensure_available()
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("이미 MoveIt 작업이 실행 중입니다.")
            self._status = "preparing"
            self._message = preparing_message
            self._output = []
            self._linux_pid = None
            self._stop_requested = False
            self._mode = mode
            self._smoke_result = None
            self._assistant_validation = None

        process = subprocess.Popen(
            ["wsl.exe", "-d", self.distro, "--", "bash", "-s"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdin is not None
        process.stdin.reconfigure(newline="\n")
        process.stdin.write(script)
        process.stdin.close()
        with self._lock:
            self._process = process
        threading.Thread(
            target=self._read_output,
            args=(process, mode),
            daemon=True,
        ).start()
        return self.snapshot()

    def _read_output(self, process: subprocess.Popen, mode: str) -> None:
        launched = False
        failure_message: str | None = None
        marker = (
            MOVEIT_ASSISTANT_MARKER
            if mode == "assistant"
            else MOVEIT_DEMO_MARKER
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            with self._lock:
                self._output.append(line)
                del self._output[:-150]
            if line.startswith("MOVEIT_CONFIG_SAVE_PATH:"):
                config_path = line.split(":", 1)[1]
                with self._lock:
                    self._expected_config_path = config_path
            elif line.startswith("MOVEIT_CONFIG_NOT_FOUND:"):
                config_path = line.split(":", 1)[1]
                failure_message = (
                    "MoveIt 설정 패키지를 찾지 못했습니다. Assistant에서 "
                    f"{config_path} 경로로 생성한 뒤 다시 실행하세요."
                )
            elif line.startswith("PETASOS_ASSISTANT_VALIDATION:"):
                try:
                    validation = json.loads(line.split(":", 1)[1])
                except json.JSONDecodeError:
                    validation = None
                with self._lock:
                    self._assistant_validation = validation
                if validation and not validation.get("valid"):
                    errors = validation.get("errors") or []
                    failure_message = (
                        "Assistant 저장 결과에서 실행 전 문제가 발견됐습니다: "
                        + (" / ".join(errors) if errors else "상세 로그를 확인하세요.")
                    )
            elif (
                "YAML::InvalidNode" in line
                or 'invalid key: "package_settings"' in line
            ):
                failure_message = (
                    "MoveIt Assistant 메타데이터가 불완전합니다. "
                    "MoveIt 단일 ros_ws를 다시 내보낸 뒤 실행하세요."
                )
            if marker in line:
                launched = True
                match = re.search(rf"{marker}:(\d+)", line)
                if match:
                    with self._lock:
                        self._linux_pid = int(match.group(1))
                if mode == "assistant":
                    self._set_state(
                        "assistant_running",
                        "페타소스 MoveIt 시작 설정을 열었습니다. 그룹·충돌·포즈를 "
                        "편집하고 저장한 뒤 창을 닫으세요.",
                    )
                else:
                    self._set_state(
                        "demo_running",
                        "MoveIt demo.launch.py가 실행 중입니다.",
                    )

        return_code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
            self._linux_pid = None
            if self._stop_requested:
                self._status = "stopped"
                self._message = "MoveIt 작업을 종료했습니다."
            elif return_code == 0 and mode == "assistant":
                self._status = "assistant_done"
                if self._assistant_validation:
                    groups = self._assistant_validation.get("planning_groups") or []
                    self._message = (
                        "Assistant 저장 결과 검사 및 ros_ws 익스포트 완료"
                        + (f" · planning group: {', '.join(groups)}" if groups else "")
                        + ". 이제 ‘생성 결과 실행’을 누르세요."
                    )
                else:
                    self._message = "Assistant를 닫았습니다. ros_ws 저장 결과를 확인하세요."
            elif return_code == 0:
                self._status = "stopped"
                self._message = "MoveIt 데모가 종료되었습니다."
            else:
                self._status = "error"
                if failure_message:
                    self._message = failure_message
                else:
                    phase = "MoveIt 실행" if launched else "WSL 복사·빌드"
                    self._message = f"{phase} 중 오류가 발생했습니다."

    def start_assistant(self, package_dir: Path) -> dict:
        package_dir = Path(package_dir).resolve()
        package_name = _validate_ros_package(package_dir)
        robot_name, xacro_relative = _robot_details(package_dir)
        config_package = f"{robot_name}_moveit_config"
        source_dir = package_dir.parent
        workspace_dir = source_dir.parent if source_dir.name == "src" else source_dir
        config_source_dir = source_dir / config_package
        if not (config_source_dir / "package.xml").is_file():
            raise ValueError(
                "같은 ros_ws 폴더에서 MoveIt 설정 패키지를 찾지 못했습니다. "
                "MoveIt 단일 ros_ws를 다시 익스포트하세요."
            )
        workspace_wsl = _windows_path_to_wsl(workspace_dir)
        with self._lock:
            self._expected_config_path = str(config_source_dir)
            self._robot_name = robot_name
            self._description_package = package_name
            self._config_package = config_package
            self._workspace_dir = workspace_dir
            self._workspace_wsl_path = workspace_wsl
        workspace = shlex.quote(workspace_wsl)
        quoted_package = shlex.quote(package_name)
        quoted_config = shlex.quote(config_package)
        quoted_xacro = shlex.quote(xacro_relative.as_posix())
        plain_urdf = shlex.quote(f"urdf/{robot_name}.urdf")
        urdf_helper = shlex.quote(_windows_path_to_wsl(self.urdf_helper_path))
        validator = shlex.quote(_windows_path_to_wsl(self.helper_path))
        script = f"""
set -eo pipefail
source /opt/ros/humble/setup.bash
workspace={workspace}
target="$workspace/src/{package_name}"
config_target="$workspace/src/{config_package}"
runtime_root="$workspace/.petasos_runtime"
rm -rf -- \
  "$runtime_root/build/{package_name}" \
  "$runtime_root/install/{package_name}" \
  "$runtime_root/build/{config_package}" \
  "$runtime_root/install/{config_package}"
cd "$workspace"
colcon --log-base "$runtime_root/log" build \
  --build-base "$runtime_root/build" \
  --install-base "$runtime_root/install" \
  --packages-up-to \
  {quoted_package} {quoted_config}
source "$runtime_root/install/setup.bash"
xacro "$target"/{quoted_xacro} > "$target"/{plain_urdf}
python3 {urdf_helper} "$target"/{plain_urdf}
python3 {validator} "$config_target" --urdf "$target"/{plain_urdf}
printf 'MOVEIT_CONFIG_SAVE_PATH:%s\\n' "$config_target"
printf '{MOVEIT_ASSISTANT_MARKER}:%s\\n' "$$"
assistant_pid=0
terminate_assistant() {{
    if [ "$assistant_pid" -gt 0 ]; then
        kill -TERM "$assistant_pid" 2>/dev/null || true
    fi
    rm -rf "$runtime_root"
}}
trap terminate_assistant TERM INT
ros2 run moveit_setup_assistant moveit_setup_assistant \
  -c "$config_target" &
assistant_pid=$!
set +e
wait "$assistant_pid"
assistant_run_status=$?
trap - TERM INT
if [ "$assistant_run_status" -ne 0 ]; then
    exit "$assistant_run_status"
fi
mkdir -p "$workspace/.petasos_backups"
cp -a "$config_target/config" \
  "$workspace/.petasos_backups/{config_package}_$(date +%Y%m%d_%H%M%S_%N)"
assistant_json="$(python3 {validator} "$config_target" \
  --urdf "$target"/{plain_urdf} --fix)"
assistant_status=$?
set -e
printf 'PETASOS_ASSISTANT_VALIDATION:%s\\n' "$assistant_json"
if [ "$assistant_status" -eq 0 ]; then
    python3 {validator} "$config_target" --urdf "$target"/{plain_urdf}
fi
rm -rf "$runtime_root"
exit "$assistant_status"
"""
        return self._spawn(
            script,
            mode="assistant",
            preparing_message=(
                "내보낸 ros_ws의 Xacro와 MoveIt 설정을 직접 검사한 뒤 "
                "MoveIt Setup Assistant를 준비하고 있습니다. "
                f"설정 위치: {config_source_dir}"
            ),
        )

    def start_demo(self, package_dir: Path) -> dict:
        package_dir = Path(package_dir).resolve()
        package_name = _validate_ros_package(package_dir)
        robot_name, xacro_relative = _robot_details(package_dir)
        config_package = f"{robot_name}_moveit_config"
        source_dir = package_dir.parent
        workspace_dir = source_dir.parent if source_dir.name == "src" else source_dir
        config_source_dir = source_dir / config_package
        workspace_wsl = _windows_path_to_wsl(workspace_dir)
        with self._lock:
            self._expected_config_path = str(config_source_dir)
            self._robot_name = robot_name
            self._description_package = package_name
            self._config_package = config_package
            self._workspace_dir = workspace_dir
            self._workspace_wsl_path = workspace_wsl
        workspace = shlex.quote(workspace_wsl)
        helper = shlex.quote(_windows_path_to_wsl(self.helper_path))
        urdf_helper = shlex.quote(_windows_path_to_wsl(self.urdf_helper_path))
        quoted_description = shlex.quote(package_name)
        quoted_config = shlex.quote(config_package)
        quoted_xacro = shlex.quote(xacro_relative.as_posix())
        script = f"""
set -eo pipefail
source /opt/ros/humble/setup.bash
workspace={workspace}
description_target="$workspace/src/{package_name}"
config_target="$workspace/src/{config_package}"
runtime_root="$workspace/.petasos_runtime"
rm -rf -- \
  "$runtime_root/build/{package_name}" \
  "$runtime_root/install/{package_name}" \
  "$runtime_root/build/{config_package}" \
  "$runtime_root/install/{config_package}"
if [ ! -f "$config_target/package.xml" ]; then
    printf 'MOVEIT_CONFIG_NOT_FOUND:%s\\n' "$config_target"
    exit 24
fi
xacro "$description_target"/{quoted_xacro} \
  > "$description_target/urdf/{robot_name}.urdf"
python3 {urdf_helper} "$description_target/urdf/{robot_name}.urdf"
mkdir -p "$workspace/.petasos_backups"
cp -a "$config_target/config" \
  "$workspace/.petasos_backups/{config_package}_$(date +%Y%m%d_%H%M%S_%N)"
python3 {helper} "$config_target" \
  --urdf "$description_target/urdf/{robot_name}.urdf" --fix
python3 {helper} "$config_target" \
  --urdf "$description_target/urdf/{robot_name}.urdf"
cd "$workspace"
colcon --log-base "$runtime_root/log" build \
  --build-base "$runtime_root/build" \
  --install-base "$runtime_root/install" \
  --packages-up-to \
  {quoted_description} {quoted_config}
source "$runtime_root/install/setup.bash"
export ROS_DOMAIN_ID={WSL_MOVEIT_DOMAIN_ID}
printf '{MOVEIT_DEMO_MARKER}:%s\\n' "$$"
demo_pid=0
cleanup_demo() {{
    if [ "$demo_pid" -gt 0 ]; then
        kill -TERM "$demo_pid" 2>/dev/null || true
    fi
    rm -rf "$runtime_root"
}}
trap cleanup_demo TERM INT EXIT
ros2 launch {quoted_config} demo.launch.py &
demo_pid=$!
wait "$demo_pid"
demo_status=$?
demo_pid=0
exit "$demo_status"
"""
        return self._spawn(
            script,
            mode="demo",
            preparing_message=(
                "Assistant 결과를 백업·정규화한 뒤 "
                "ROS 2 작업공간을 빌드하고 있습니다."
            ),
        )

    def run_smoke(self) -> dict:
        with self._lock:
            process = self._process
            robot_name = self._robot_name
            description_package = self._description_package
            config_package = self._config_package
            workspace_wsl = self._workspace_wsl_path
            if (
                process is None
                or process.poll() is not None
                or self._mode != "demo"
                or self._status != "demo_running"
            ):
                raise RuntimeError(
                    "먼저 MoveIt 생성 결과를 실행해 demo를 켜 주세요."
                )
        if not all((
            robot_name,
            description_package,
            config_package,
            workspace_wsl,
        )):
            raise RuntimeError("MoveIt 자동검사에 필요한 패키지 정보를 찾지 못했습니다.")

        helper = shlex.quote(_windows_path_to_wsl(self.smoke_helper_path))
        workspace = shlex.quote(workspace_wsl)
        script = f"""
set -eo pipefail
source /opt/ros/humble/setup.bash
workspace={workspace}
source "$workspace/.petasos_runtime/install/setup.bash"
export ROS_DOMAIN_ID={WSL_MOVEIT_DOMAIN_ID}
python3 {helper} \
  --srdf "$workspace/src/{config_package}/config/{robot_name}.srdf" \
  --urdf "$workspace/src/{description_package}/urdf/{robot_name}.urdf"
"""
        completed = subprocess.run(
            ["wsl.exe", "-d", self.distro, "--", "bash", "-s"],
            input=script.replace("\r\n", "\n").encode("utf-8"),
            check=False,
            capture_output=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        combined = "\n".join(
            item for item in (stdout, stderr) if item
        )
        with self._lock:
            self._output.extend(
                line for line in combined.splitlines() if line.strip()
            )
            del self._output[:-150]
        match = re.search(
            r"PETASOS_MOVEIT_SMOKE_RESULT=(\{.*\})",
            combined,
        )
        if completed.returncode != 0 or not match:
            detail = combined.strip().splitlines()
            raise RuntimeError(
                "MoveIt 자동 움직임 검사에 실패했습니다."
                + (f" ({detail[-1]})" if detail else "")
            )
        result = json.loads(match.group(1))
        if not result.get("success"):
            raise RuntimeError(
                f"MoveIt 계획/실행 실패: error_code={result.get('error_code')}"
            )
        with self._lock:
            self._smoke_result = result
            self._message = (
                "움직임 검사 성공: OMPL 계획과 가상 컨트롤러 실행 후 "
                f"최대 관절 오차 {result.get('max_target_error', 0.0):.6f} rad"
            )
        return self.snapshot()

    def stop(self) -> dict:
        already_stopped = False
        with self._lock:
            process = self._process
            linux_pid = self._linux_pid
            if process is None or process.poll() is not None:
                self._status = "stopped"
                self._message = "실행 중인 MoveIt 작업이 없습니다."
                already_stopped = True
            else:
                self._stop_requested = True
                self._status = "stopping"
                self._message = "MoveIt 작업을 종료하고 있습니다."

        if already_stopped:
            return self.snapshot()
        if linux_pid is not None:
            subprocess.run(
                [
                    "wsl.exe",
                    "-d",
                    self.distro,
                    "--",
                    "kill",
                    "-TERM",
                    str(linux_pid),
                ],
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        return self.snapshot()
