from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path, PurePosixPath

from flask import Flask, jsonify, request, send_file, send_from_directory, g

from URDF_Exporter.core.web_ui import HTML_CONTENT
from URDF_Exporter.standalone.adapters import SUPPORTED_NATIVE_EXTENSIONS
from URDF_Exporter.standalone.adapters.inventor import (
    InventorAdapterError,
    convert_active_inventor,
    convert_with_inventor,
)
from URDF_Exporter.standalone.exporter import export_project
from URDF_Exporter.standalone.importers import (
    GEOMETRY_EXTENSIONS,
    MANIFEST_SUFFIX,
    ImportFailure,
    build_project,
    safe_name,
)
from URDF_Exporter.standalone.reimporter import merge_reimported_state
from URDF_Exporter.standalone.physical_materials import ensure_material_editor_data
from URDF_Exporter.standalone.physical_migration import repair_legacy_inventor_com
from URDF_Exporter.standalone.export_preflight import inspect_candidate
from URDF_Exporter.standalone.robot_modules import ensure_module_ids, validate_modules
from URDF_Exporter.standalone.module_api import register_module_api
from moveit.wsl_runner import WslMoveItRunner


APP_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_ROOT = APP_ROOT / "standalone_projects"
EXPORT_ROOT = Path(
    os.environ.get("PETASOS_EXPORT_ROOT", str(APP_ROOT / "export"))
).resolve()
LAST_PROJECT_FILE = PROJECTS_ROOT / ".last_project"
WSL_RVIZ_DISTRO = "Ubuntu-22.04"
WSL_RVIZ_MARKER = "PETASOS_RVIZ_LAUNCHING"


def _cleanup_wsl_gui_processes(distro: str = WSL_RVIZ_DISTRO) -> dict:
    """Stop stale Petasos RViz/MoveIt GUI processes without shutting WSL down."""
    if os.name != "nt":
        return {"status": "skipped", "stopped": 0}

    script = r"""
set +e
stopped=0

stop_name() {
    name="$1"
    pids="$(pgrep -x "$name" 2>/dev/null)"
    [ -n "$pids" ] || return 0
    count="$(printf '%s\n' "$pids" | wc -l)"
    pkill -TERM -x "$name" 2>/dev/null || true
    stopped=$((stopped + count))
}

stop_pattern() {
    pattern="$1"
    pids="$(pgrep -f "$pattern" 2>/dev/null)"
    [ -n "$pids" ] || return 0
    count="$(printf '%s\n' "$pids" | wc -l)"
    pkill -TERM -f "$pattern" 2>/dev/null || true
    stopped=$((stopped + count))
}

stop_name rviz2
stop_name moveit_setup_assistant
stop_name move_group
stop_name joint_state_publisher_gui
stop_name robot_state_publisher
stop_name ros2_control_node
stop_pattern '[r]os2 launch .*display\.launch\.py'
stop_pattern '[r]os2 launch .*demo\.launch\.py'
sleep 0.7

pkill -KILL -x rviz2 2>/dev/null || true
pkill -KILL -x moveit_setup_assistant 2>/dev/null || true
pkill -KILL -x move_group 2>/dev/null || true
pkill -KILL -x joint_state_publisher_gui 2>/dev/null || true
pkill -KILL -x robot_state_publisher 2>/dev/null || true
pkill -KILL -x ros2_control_node 2>/dev/null || true
pkill -KILL -f '[r]os2 launch .*display\.launch\.py' 2>/dev/null || true
pkill -KILL -f '[r]os2 launch .*demo\.launch\.py' 2>/dev/null || true

find "$HOME/petasos_ros2_ws/.petasos_runtime" -maxdepth 1 \
    -name '*.pid' -type f -delete 2>/dev/null || true
printf 'PETASOS_WSL_GUI_CLEANED:%s\n' "$stopped"
"""
    completed = subprocess.run(
        ["wsl.exe", "-d", distro, "--", "bash", "-s"],
        input=script.encode("utf-8"),
        check=False,
        capture_output=True,
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = completed.stdout.decode("utf-8", errors="replace")
    match = re.search(r"PETASOS_WSL_GUI_CLEANED:(\d+)", output)
    return {
        "status": "stopped" if completed.returncode == 0 else "warning",
        "stopped": int(match.group(1)) if match else 0,
    }


def _open_folder(path: Path) -> None:
    folder = Path(path).resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"내보내기 폴더를 찾을 수 없습니다: {folder}")
    if os.name == "nt":
        os.startfile(str(folder))
        return
    command = ["open", str(folder)] if os.sys.platform == "darwin" else ["xdg-open", str(folder)]
    subprocess.Popen(command)


def _windows_path_to_wsl(path: Path) -> str:
    windows_path = Path(path).resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", windows_path):
        raise ValueError(f"WSL로 전달할 수 없는 Windows 경로입니다: {path}")
    drive = windows_path[0].lower()
    return f"/mnt/{drive}/{windows_path[3:]}"


class WslRvizRunner:
    def __init__(self, distro: str = WSL_RVIZ_DISTRO):
        self.distro = distro
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._linux_pid: int | None = None
        self._stop_requested = False
        self._auto_recovery_attempted = False
        self._status = "idle"
        self._message = "RViz 실행 대기 중"
        self._output: list[str] = []

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "message": self._message,
                "output": self._output[-20:],
                "process_running": self._process is not None and self._process.poll() is None,
            }

    def _set_state(self, status: str, message: str) -> None:
        with self._lock:
            self._status = status
            self._message = message

    @staticmethod
    def _is_rviz_window_title(title: str) -> bool:
        normalized = str(title or "").strip().lower()
        return "rviz" in normalized

    @staticmethod
    def _is_wslg_copy_mode(title: str) -> bool:
        return "[WARN:COPY MODE]" in str(title or "").upper()

    def _ensure_ros_ready(self) -> None:
        result = subprocess.run(
            [
                "wsl.exe", "-d", self.distro, "--", "bash", "-lc",
                (
                    "test -f /opt/ros/humble/setup.bash && "
                    "source /opt/ros/humble/setup.bash && "
                    "command -v ros2 >/dev/null"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            message = (
                "Ubuntu-22.04에 ROS 2 Humble이 아직 준비되지 않았습니다. "
                "setup_petasos.cmd를 다시 실행해 ROS 설치를 완료하세요. "
                "확인 파일: /opt/ros/humble/setup.bash"
            )
            if detail:
                message += f" ({detail})"
            raise RuntimeError(message)

    def _stream_package(self, process: subprocess.Popen, package_dir: Path) -> None:
        try:
            assert process.stdin is not None
            with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                for child in sorted(package_dir.iterdir(), key=lambda item: item.name):
                    archive.add(child, arcname=child.name, recursive=True)
        except (BrokenPipeError, OSError, tarfile.TarError) as exc:
            with self._lock:
                self._output.append(f"Package transfer failed: {exc}")
            if process.poll() is None:
                process.terminate()
        finally:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass

    def _stage_wsl_script(self, script: str, package_name: str) -> str:
        linux_path = f"/tmp/petasos-rviz-{package_name}.sh"
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        stage_command = (
            "umask 077; printf '%s' '"
            + encoded
            + f"' | base64 -d > '{linux_path}'; chmod 700 '{linux_path}'"
        )
        result = subprocess.run(
            [
                "wsl.exe", "-d", self.distro, "--", "bash", "-lc",
                stage_command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                "RViz 실행 스크립트를 Ubuntu에 준비하지 못했습니다."
                + (f" ({detail})" if detail else "")
            )
        return linux_path

    def _read_output(self, process: subprocess.Popen) -> None:
        launched = False
        assert process.stdout is not None
        for raw_line in process.stdout:
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            line = raw_line.rstrip()
            if not line:
                continue
            with self._lock:
                self._output.append(line)
                del self._output[:-100]
            if WSL_RVIZ_MARKER in line:
                launched = True
                match = re.search(rf"{WSL_RVIZ_MARKER}:(\d+)", line)
                if match:
                    with self._lock:
                        self._linux_pid = int(match.group(1))
                self._set_state("launching", "RViz 창이 열리기를 기다리고 있습니다.")
                threading.Thread(target=self._bring_to_front, daemon=True).start()

        return_code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
            self._linux_pid = None
            if self._stop_requested or return_code == 0:
                self._status = "stopped"
                self._message = "RViz 실행이 종료되었습니다."
            else:
                self._status = "error"
                phase = "RViz 실행" if launched else "동기화 또는 빌드"
                self._message = f"{phase} 중 오류가 발생했습니다."

    def _bring_to_front(self) -> None:
        if os.name != "nt":
            return
        import time
        # ros2 launch starts joint_state_publisher_gui before RViz.  The old
        # implementation treated either window as success and stopped polling,
        # so RViz could remain minimized/behind the browser on the taskbar.
        # Wait specifically for the RViz top-level window instead.
        for _ in range(40):
            time.sleep(0.5)
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                found = []

                def enum_proc(hwnd, lParam):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        if self._is_rviz_window_title(buff.value):
                            found.append((hwnd, buff.value))
                    return True

                user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
                if found:
                    hwnd, title = found[0]
                    if self._is_wslg_copy_mode(title):
                        self._begin_wslg_recovery(
                            "WSLg 화면 연결 오류로 RViz 창이 투명하게 표시됩니다."
                        )
                        return
                    user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
                    # SetForegroundWindow alone may be rejected when the
                    # foreground belongs to a browser.  Briefly lifting the
                    # window in Z order reliably reveals a WSLg/Qt window,
                    # while immediately returning it to non-topmost state.
                    swp_flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE|NOMOVE|SHOWWINDOW
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, swp_flags)  # TOPMOST
                    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, swp_flags)  # NOTOPMOST
                    user32.SetForegroundWindow(hwnd)
                    self._set_state("running", "RViz 창을 Windows 화면에 표시했습니다.")
                    return
            except Exception:
                return

        with self._lock:
            process_running = self._process is not None and self._process.poll() is None
        if process_running:
            self._begin_wslg_recovery(
                "RViz 프로세스는 실행 중이지만 Windows 화면에서 창을 찾지 못했습니다."
            )

    def _begin_wslg_recovery(self, reason: str) -> None:
        with self._lock:
            if self._auto_recovery_attempted or self._stop_requested:
                return
            package_dir = getattr(self, "_package_dir", None)
            if package_dir is None:
                self._status = "error"
                self._message = reason + " WSLg 자동 복구에 필요한 패키지 경로가 없습니다."
                return
            self._auto_recovery_attempted = True
            self._status = "recovering"
            self._message = (
                reason
                + " WSLg 복구를 위해 모든 WSL 배포판을 종료한 뒤 RViz를 한 번 다시 실행합니다."
            )
        threading.Thread(
            target=self._recover_wslg,
            args=(package_dir,),
            daemon=True,
        ).start()

    def _recover_wslg(self, package_dir: Path) -> None:
        old_process = None
        try:
            result = subprocess.run(
                ["wsl.exe", "--shutdown"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(detail or f"wsl --shutdown 종료 코드 {result.returncode}")

            with self._lock:
                if self._stop_requested:
                    self._status = "stopped"
                    self._message = "사용자 요청으로 WSLg 자동 복구를 취소했습니다."
                    return
                old_process = self._process

            if old_process is not None and old_process.poll() is None:
                try:
                    old_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    old_process.terminate()
                    try:
                        old_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        old_process.kill()
                        old_process.wait(timeout=2)

            with self._lock:
                if self._stop_requested:
                    self._status = "stopped"
                    self._message = "사용자 요청으로 WSLg 자동 복구를 취소했습니다."
                    return
                if self._process is old_process:
                    self._process = None
                    self._linux_pid = None

            self.start(package_dir, _recovery_retry=True)
        except Exception as exc:
            with self._lock:
                if self._stop_requested:
                    self._status = "stopped"
                    self._message = "사용자 요청으로 WSLg 자동 복구를 취소했습니다."
                else:
                    self._status = "error"
                    self._message = f"WSLg 자동 복구 후 RViz 재실행에 실패했습니다: {exc}"

    def start(self, package_dir: Path, _recovery_retry: bool = False) -> dict:
        package_dir = Path(package_dir).resolve()
        package_name = package_dir.name
        if not re.fullmatch(r"[a-z][a-z0-9_]*", package_name):
            raise ValueError(f"ROS 2 패키지 이름이 올바르지 않습니다: {package_name}")
        if not (package_dir / "package.xml").is_file():
            raise ValueError("내보낸 ROS 2 package.xml을 찾을 수 없습니다.")

        self._ensure_ros_ready()

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("이미 RViz가 실행 중입니다.")
            self._status = "preparing"
            self._message = "WSL로 패키지를 복사하고 ROS 2 빌드를 준비하고 있습니다."
            self._output = []
            self._linux_pid = None
            self._stop_requested = False
            self._package_dir = package_dir
            if not _recovery_retry:
                self._auto_recovery_attempted = False

        quoted_package = shlex.quote(package_name)
        script = f"""
set -eo pipefail
trap 'rm -f -- "$0"' EXIT
source /opt/ros/humble/setup.bash
export LIBGL_ALWAYS_SOFTWARE=1
export OGRE_RTT_MODE=Copy
workspace="$HOME/petasos_ros2_ws"
target="$workspace/src/{package_name}"
runtime_dir="$workspace/.petasos_runtime"
pid_file="$runtime_dir/{package_name}.pid"
mkdir -p "$workspace/src"
mkdir -p "$runtime_dir"
rm -rf -- "$workspace/build/{package_name}" "$workspace/install/{package_name}"
if [ -s "$pid_file" ]; then
    previous_pid="$(cat "$pid_file")"
    if [ "$previous_pid" != "$$" ] && kill -0 "$previous_pid" 2>/dev/null; then
        kill -TERM "$previous_pid" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            kill -0 "$previous_pid" 2>/dev/null || break
            sleep 0.2
        done
    fi
fi
rm -rf -- "$target"
mkdir -p "$target"
tar -xpf - -C "$target"
cd "$workspace"
colcon build --symlink-install --packages-select {quoted_package}
source "$workspace/install/setup.bash"
printf '%s\\n' "$$" > "$pid_file"
printf '{WSL_RVIZ_MARKER}:%s\\n' "$$"
rm -f -- "$0"
exec ros2 launch {quoted_package} display.launch.py
"""
        linux_script = self._stage_wsl_script(script, package_name)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            ["wsl.exe", "-d", self.distro, "--", "bash", linux_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        with self._lock:
            self._process = process
        threading.Thread(
            target=self._stream_package,
            args=(process, package_dir),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_output,
            args=(process,),
            daemon=True,
        ).start()
        return self.snapshot()

    def stop(self) -> dict:
        already_stopped = False
        with self._lock:
            process = self._process
            linux_pid = self._linux_pid
            if process is None or process.poll() is not None:
                self._status = "stopped"
                self._message = "실행 중인 RViz가 없습니다."
                already_stopped = True
            else:
                self._stop_requested = True
                self._status = "stopping"
                self._message = "RViz와 ROS 2 표시 노드를 종료하고 있습니다."

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


def _safe_upload_name(filename: str) -> str:
    name = os.path.basename(filename.replace("\\", "/"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name


def _safe_upload_path(filename: str) -> Path:
    parts = []
    for raw_part in PurePosixPath(filename.replace("\\", "/")).parts:
        if raw_part in {"", ".", "..", "/"}:
            continue
        safe_part = _safe_upload_name(raw_part)
        if safe_part:
            parts.append(safe_part)
    return Path(*parts) if parts else Path()


def _choose_inventor_file() -> Path | None:
    if os.name != "nt":
        raise ImportFailure("원본 IAM 파일 선택은 Windows에서 지원됩니다.")
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise ImportFailure("Windows 파일 선택창을 사용할 수 없습니다.") from exc
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askopenfilename(
            parent=root,
            title="Petasos - 원본 Inventor 조립품 선택",
            filetypes=[
                ("Inventor Assembly", "*.iam"),
                ("CAD Assembly", "*.iam;*.sldasm;*.asm;*.CATProduct;*.jt;*.3dxml"),
                ("All Files", "*.*"),
            ],
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


class ProjectStore:
    def __init__(
        self,
        projects_root: Path = PROJECTS_ROOT,
        export_root: Path | None = None,
    ):
        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)
        if export_root is not None:
            self.export_root = Path(export_root)
        elif self.projects_root.resolve() == PROJECTS_ROOT.resolve():
            self.export_root = EXPORT_ROOT
        else:
            self.export_root = self.projects_root.parent / "export"
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.last_project_file = self.projects_root / ".last_project"
        self.project_dir: Path | None = None
        self.state: dict | None = None
        self.revision = 0
        self.module_epoch = 0
        self.module_lock = threading.RLock()
        self.archive_path: Path | None = None
        self.description_dir: Path | None = None
        self.bundle_dir: Path | None = None
        self.physical_migration_diagnostics: list[dict] = []
        self._pending_export: dict | None = None
        self._cleanup_export_leftovers()
        self._load_last()

    def _load_last(self) -> None:
        if not self.last_project_file.exists():
            return
        try:
            project_dir = Path(self.last_project_file.read_text(encoding="utf-8").strip())
            state_path = project_dir / "project_state.json"
            if project_dir.is_dir() and state_path.is_file():
                self.project_dir = project_dir
                self.state = json.loads(state_path.read_text(encoding="utf-8"))
                repaired, diagnostics = repair_legacy_inventor_com(self.state, project_dir)
                self.physical_migration_diagnostics = diagnostics
                if not diagnostics:
                    self.state = repaired
        except (OSError, json.JSONDecodeError):
            self.project_dir = None
            self.state = None

    def empty_tree(self) -> dict:
        return {
            "name": "base_link",
            "components": [],
            "children": [],
            "_standalone": True,
            "_empty": True,
            "_project_name": "new_robot",
            "_preview_transforms": {},
            "_preview_units_per_meter": 1000.0,
            "_cad_snap_features": {},
            "_import_report": {
                "source_application": "아직 가져온 조립품 없음",
                "parts": 0,
                "joints": 0,
                "warnings": [],
                "has_errors": False,
            },
        }

    def tree(self) -> dict:
        if not self.state:
            return self.empty_tree()
        self.state["tree"] = ensure_module_ids(ensure_material_editor_data(self.state))
        self.state["tree"]["_module_revision"] = self.revision
        return self.state["tree"]

    def _write_current_state(self) -> Path:
        assert self.state is not None
        assert self.project_dir is not None
        state_path = self.project_dir / "project_state.json"
        temporary_path = state_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_path, state_path)
        self.revision += 1
        self.last_project_file.write_text(str(self.project_dir), encoding="utf-8")
        return state_path

    def _workspace_save_path(self, save_name: str) -> tuple[str, Path]:
        if not self.project_dir:
            raise ImportFailure("먼저 조립품을 불러와야 합니다.")
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(save_name or "").strip())
        cleaned = cleaned.rstrip(" .")[:80]
        if not cleaned:
            raise ImportFailure("저장 작업 이름을 입력하세요.")
        save_dir = self.project_dir / "editor_saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        return cleaned, save_dir / f"{cleaned}.petasos-work.json"

    def save_workspace(
        self,
        tree: dict,
        editor_settings: dict | None = None,
        save_name: str = "",
    ) -> dict:
        if not self.state or not self.project_dir:
            raise ImportFailure("먼저 조립품을 불러와야 합니다.")
        if not isinstance(tree, dict) or not tree.get("name"):
            raise ImportFailure("저장할 프리뷰 편집 데이터가 올바르지 않습니다.")
        tree = ensure_module_ids(tree)
        from .sensor_frames import validate_sensors
        sensor_errors = validate_sensors(tree)
        if sensor_errors:
            raise ImportFailure(" / ".join(error["message"] for error in sensor_errors))
        module_errors = validate_modules(tree)
        if module_errors:
            raise ImportFailure(" / ".join(error["message"] for error in module_errors))
        if isinstance(editor_settings, dict):
            tree["_editor_settings"] = {
                "fix_to_world": bool(editor_settings.get("fix_to_world", True)),
                "root_joint_mode": (
                    editor_settings.get("root_joint_mode")
                    if editor_settings.get("root_joint_mode")
                    in {"world", "base_footprint", "none"}
                    else (
                        "world"
                        if editor_settings.get("fix_to_world", True)
                        else "none"
                    )
                ),
                "export_mode": (
                    "moveit"
                    if editor_settings.get("export_mode") == "moveit"
                    else "description"
                ),
            }
        stored_name = ""
        named_path = None
        if str(save_name or "").strip():
            stored_name, named_path = self._workspace_save_path(save_name)
            tree["_active_workspace_name"] = stored_name
            self.state["active_workspace_name"] = stored_name
        elif self.state.get("active_workspace_name"):
            tree["_active_workspace_name"] = self.state["active_workspace_name"]
        elif tree.get("_active_workspace_name"):
            self.state["active_workspace_name"] = tree["_active_workspace_name"]
        self.state["tree"] = tree
        state_path = self._write_current_state()
        if stored_name and named_path is not None:
            named_temporary = named_path.with_suffix(named_path.suffix + ".tmp")
            named_temporary.write_text(
                json.dumps(
                    {"save_name": stored_name, "state": self.state},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(named_temporary, named_path)
        return {
            "project_name": self.state.get("project_name") or tree.get("_project_name"),
            "revision": self.revision,
            "path": str(state_path),
            "save_name": stored_name,
            "active_workspace_name": (
                self.state.get("active_workspace_name")
                or tree.get("_active_workspace_name")
                or ""
            ),
        }

    def list_workspaces(self) -> list[dict]:
        if not self.project_dir:
            return []
        return self._list_workspaces_in_project(self.project_dir)

    def _list_workspaces_in_project(self, project_dir: Path) -> list[dict]:
        save_dir = project_dir / "editor_saves"
        if not save_dir.is_dir():
            return []
        result = []
        for path in save_dir.glob("*.petasos-work.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                name = str(payload.get("save_name") or path.name.removesuffix(".petasos-work.json"))
                state = payload.get("state") if isinstance(payload, dict) else {}
                tree = state.get("tree") if isinstance(state, dict) else {}
                result.append({
                    "name": name,
                    "project_id": project_dir.name,
                    "project_name": (
                        state.get("project_name")
                        if isinstance(state, dict)
                        else None
                    ) or (
                        tree.get("_project_name")
                        if isinstance(tree, dict)
                        else None
                    ) or project_dir.name,
                    "modified_at": path.stat().st_mtime,
                })
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item["modified_at"], reverse=True)

    def list_all_workspaces(self) -> list[dict]:
        result = []
        for project_dir in self.projects_root.iterdir():
            if project_dir.is_dir():
                result.extend(self._list_workspaces_in_project(project_dir))
        return sorted(result, key=lambda item: item["modified_at"], reverse=True)

    def reload_workspace(self, save_name: str = "", project_id: str = "") -> dict:
        target_project_dir = self.project_dir
        requested_project = str(project_id or "").strip()
        if requested_project:
            if (
                requested_project in {".", ".."}
                or Path(requested_project).name != requested_project
            ):
                raise ImportFailure("불러올 프로젝트 경로가 올바르지 않습니다.")
            candidate = (self.projects_root / requested_project).resolve()
            if candidate.parent != self.projects_root.resolve() or not candidate.is_dir():
                raise ImportFailure("불러올 프로젝트를 찾을 수 없습니다.")
            target_project_dir = candidate
        if not target_project_dir:
            raise ImportFailure("다시 불러올 프로젝트가 없습니다.")
        if str(save_name or "").strip():
            cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(save_name).strip())
            cleaned = cleaned.rstrip(" .")[:80]
            if not cleaned:
                raise ImportFailure("불러올 저장 작업 이름이 올바르지 않습니다.")
            stored_name = cleaned
            state_path = (
                target_project_dir
                / "editor_saves"
                / f"{stored_name}.petasos-work.json"
            )
        else:
            stored_name = ""
            state_path = target_project_dir / "project_state.json"
        if not state_path.is_file():
            target = f"'{stored_name}'" if stored_name else "마지막 자동 저장"
            raise ImportFailure(f"{target} 작업 파일을 찾을 수 없습니다.")
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportFailure(f"저장된 프리뷰 편집 파일을 읽지 못했습니다: {exc}") from exc
        state = payload.get("state") if stored_name and isinstance(payload, dict) else payload
        if not isinstance(state, dict) or not isinstance(state.get("tree"), dict):
            raise ImportFailure("저장된 프리뷰 편집 데이터가 올바르지 않습니다.")
        if stored_name:
            state["active_workspace_name"] = stored_name
            state["tree"]["_active_workspace_name"] = stored_name
        self.project_dir = target_project_dir
        self.module_epoch += 1
        self.state = state
        self.archive_path = None
        self.description_dir = None
        self.bundle_dir = None
        self._write_current_state()
        return self.state["tree"]

    def _begin_import(self, project_name: str) -> tuple[str, Path, Path, Path, Path]:
        project_name = safe_name(project_name or "robot", "robot")
        project_dir = self.projects_root / project_name
        staging_dir = project_dir / ".import_staging"
        if staging_dir.is_dir():
            shutil.rmtree(staging_dir)
        source_dir = staging_dir / "sources"
        mesh_dir = staging_dir / "meshes"
        source_dir.mkdir(parents=True, exist_ok=True)
        mesh_dir.mkdir(parents=True, exist_ok=True)
        return project_name, project_dir, staging_dir, source_dir, mesh_dir

    def _commit_import(
        self,
        state: dict,
        project_dir: Path,
        staging_dir: Path,
    ) -> dict:
        self.revision += 1
        self.module_epoch += 1
        source_dir = project_dir / "sources"
        mesh_dir = project_dir / "meshes"
        if source_dir.is_dir():
            shutil.rmtree(source_dir)
        if mesh_dir.is_dir():
            shutil.rmtree(mesh_dir)
        shutil.move(str(staging_dir / "sources"), str(source_dir))
        shutil.move(str(staging_dir / "meshes"), str(mesh_dir))
        shutil.rmtree(staging_dir, ignore_errors=True)
        self.project_dir = project_dir
        self.state = state
        self.archive_path = None
        self.description_dir = None
        self.bundle_dir = None
        (project_dir / "project_state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.last_project_file.write_text(str(project_dir), encoding="utf-8")
        return state

    def _save_import_uploads(self, source_dir: Path, uploads, relative_uploads=None) -> int:
        saved = 0
        upload_groups = [
            (uploads, False),
            (relative_uploads or [], True),
        ]
        for group, preserve_tree in upload_groups:
            for upload in group:
                raw_path = _safe_upload_path(upload.filename or "")
                if preserve_tree and len(raw_path.parts) > 1:
                    # webkitRelativePath starts with the selected folder name.
                    relative_path = Path(*raw_path.parts[1:])
                else:
                    relative_path = Path(raw_path.name)
                filename = relative_path.name
                lower = filename.lower()
                extension = os.path.splitext(lower)[1]
                if not filename or (
                    extension not in GEOMETRY_EXTENSIONS
                    and extension not in SUPPORTED_NATIVE_EXTENSIONS
                    and not lower.endswith(MANIFEST_SUFFIX)
                ):
                    continue
                target = source_dir / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                upload.save(target)
                saved += 1
        return saved

    def import_files(self, project_name: str, uploads, relative_uploads=None) -> dict:
        project_name, project_dir, staging_dir, source_dir, mesh_dir = self._begin_import(
            project_name
        )

        saved = self._save_import_uploads(source_dir, uploads, relative_uploads)
        if saved == 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportFailure("지원되는 파일이 선택되지 않았습니다.")

        try:
            state = build_project(str(source_dir), str(mesh_dir), project_name)
            return self._commit_import(state, project_dir, staging_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    def reimport_files(self, uploads, edited_tree: dict, relative_uploads=None) -> dict:
        if not self.state or not self.project_dir:
            raise ImportFailure("먼저 업데이트할 CAD 조립품을 불러와야 합니다.")
        if not isinstance(edited_tree, dict) or not edited_tree.get("name"):
            raise ImportFailure("보존할 현재 편집 데이터가 올바르지 않습니다.")

        previous_state = copy.deepcopy(self.state)
        project_name = str(
            previous_state.get("project_name")
            or edited_tree.get("_project_name")
            or self.project_dir.name
        )
        project_dir = self.project_dir
        staging_dir = project_dir / ".reimport_staging"
        if staging_dir.is_dir():
            shutil.rmtree(staging_dir)
        source_dir = staging_dir / "sources"
        mesh_dir = staging_dir / "meshes"
        source_dir.mkdir(parents=True, exist_ok=True)
        mesh_dir.mkdir(parents=True, exist_ok=True)

        saved = self._save_import_uploads(source_dir, uploads, relative_uploads)
        if saved == 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportFailure("업데이트할 STEP 또는 CAD 파일이 선택되지 않았습니다.")

        try:
            fresh_state = build_project(str(source_dir), str(mesh_dir), project_name)
            merged_state = merge_reimported_state(
                previous_state,
                fresh_state,
                edited_tree,
            )
            return self._commit_import(merged_state, project_dir, staging_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    def import_inventor_path(self, project_name: str, assembly_path: Path) -> dict:
        assembly_path = Path(assembly_path)
        if not assembly_path.is_file():
            raise ImportFailure(f"원본 조립품 파일을 찾을 수 없습니다: {assembly_path}")
        project_name, project_dir, staging_dir, source_dir, mesh_dir = self._begin_import(
            project_name
        )
        try:
            convert_with_inventor(assembly_path, source_dir, project_name)
            state = build_project(str(source_dir), str(mesh_dir), project_name)
            return self._commit_import(state, project_dir, staging_dir)
        except InventorAdapterError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportFailure(str(exc)) from exc
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    def import_active_inventor(self, project_name: str) -> dict:
        project_name, project_dir, staging_dir, source_dir, mesh_dir = self._begin_import(
            project_name
        )
        try:
            convert_active_inventor(source_dir, project_name)
            state = build_project(str(source_dir), str(mesh_dir), project_name)
            return self._commit_import(state, project_dir, staging_dir)
        except InventorAdapterError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportFailure(str(exc)) from exc
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    def _reimport_from_inventor(self, edited_tree: dict, converter) -> dict:
        if not self.state or not self.project_dir:
            raise ImportFailure("먼저 업데이트할 Inventor 조립품을 불러와야 합니다.")
        if not isinstance(edited_tree, dict) or not edited_tree.get("name"):
            raise ImportFailure("보존할 현재 편집 데이터가 올바르지 않습니다.")

        previous_state = copy.deepcopy(self.state)
        project_name = str(
            previous_state.get("project_name")
            or edited_tree.get("_project_name")
            or self.project_dir.name
        )
        project_dir = self.project_dir
        staging_dir = project_dir / ".reimport_staging"
        if staging_dir.is_dir():
            shutil.rmtree(staging_dir)
        source_dir = staging_dir / "sources"
        mesh_dir = staging_dir / "meshes"
        source_dir.mkdir(parents=True, exist_ok=True)
        mesh_dir.mkdir(parents=True, exist_ok=True)

        try:
            converter(source_dir, project_name)
            fresh_state = build_project(str(source_dir), str(mesh_dir), project_name)
            merged_state = merge_reimported_state(
                previous_state,
                fresh_state,
                edited_tree,
            )
            return self._commit_import(merged_state, project_dir, staging_dir)
        except InventorAdapterError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportFailure(str(exc)) from exc
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    def reimport_active_inventor(self, edited_tree: dict) -> dict:
        return self._reimport_from_inventor(
            edited_tree,
            lambda source_dir, project_name: convert_active_inventor(
                source_dir,
                project_name,
            ),
        )

    def reimport_inventor_path(
        self,
        assembly_path: Path,
        edited_tree: dict,
    ) -> dict:
        assembly_path = Path(assembly_path)
        if not assembly_path.is_file():
            raise ImportFailure(f"원본 조립품 파일을 찾을 수 없습니다: {assembly_path}")
        return self._reimport_from_inventor(
            edited_tree,
            lambda source_dir, project_name: convert_with_inventor(
                assembly_path,
                source_dir,
                project_name,
            ),
        )

    def _export_fingerprint(self) -> str:
        payload = json.dumps(self.state, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _owned_export_stage(self, path: Path) -> Path:
        root = self.export_root.resolve()
        target = Path(path).resolve()
        if target.parent != root or not target.name.startswith(".petasos-stage-"):
            raise ValueError(f"Export stage is outside the selected export root: {target}")
        return target

    def _prune_export_backups(self, keep: Path | None = None) -> None:
        """Keep at most one previous-export backup (``keep`` or the newest)."""
        try:
            root = self.export_root.resolve()
            backups = [
                path for path in root.glob(".petasos-backup-*")
                if path.is_dir() and path.parent == root
            ]
            if not backups:
                return
            if keep is None or Path(keep).resolve() not in {b.resolve() for b in backups}:
                keep = max(backups, key=lambda path: path.stat().st_mtime)
            keep = Path(keep).resolve()
            for path in backups:
                if path.resolve() != keep:
                    shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass

    def _cleanup_export_leftovers(self) -> None:
        """Remove stage folders orphaned by an interrupted export and old backups."""
        try:
            root = self.export_root.resolve()
            for path in root.glob(".petasos-stage-*"):
                if path.is_dir() and path.parent == root:
                    shutil.rmtree(path, ignore_errors=True)
            self._prune_export_backups()
        except OSError:
            pass

    def cancel_export(self, token: str) -> None:
        pending = self._pending_export
        if pending is None or pending["token"] != token:
            raise ValueError("Export token is no longer valid")
        stage = self._owned_export_stage(pending["stage"])
        if stage.is_dir():
            shutil.rmtree(stage)
        self._pending_export = None

    def prepare_export(
        self,
        tree: dict,
        fix_to_world: bool,
        include_moveit: bool = False,
        root_joint_mode: str | None = None,
    ) -> dict:
        if not self.state or not self.project_dir:
            raise ImportFailure("먼저 조립품을 불러와야 합니다.")
        if self._pending_export is not None:
            self.cancel_export(self._pending_export["token"])
        export_state, physical_diagnostics = repair_legacy_inventor_com(
            self.state, self.project_dir
        )
        if physical_diagnostics:
            raise ImportFailure(" / ".join(item["message"] for item in physical_diagnostics))
        export_tree = copy.deepcopy(tree)
        if root_joint_mode == "base_footprint" and not export_tree.get("_base_footprint_frame"):
            export_tree["_base_footprint_frame"] = {
                "world_xyz": [0.0, 0.0, 0.0],
                "rpy": [0.0, 0.0, 0.0],
                "yaw": 0.0,
            }
        token = secrets.token_urlsafe(18)
        stage = self._owned_export_stage(self.export_root / f".petasos-stage-{token}")
        stage.mkdir()
        try:
            result = export_project(
                export_state, export_tree, fix_to_world, str(self.project_dir),
                include_moveit=include_moveit, output_root=str(stage),
                root_joint_mode=root_joint_mode,
            )
            description = Path(result["save_dir"]).resolve()
            description.relative_to(stage)
            moveit_dir = None
            if result.get("bundle_dir"):
                moveit_candidates = sorted((Path(result["bundle_dir"]) / "src").glob("*_moveit_config"))
                moveit_dir = moveit_candidates[0] if moveit_candidates else None
            if moveit_dir is not None:
                from .moveit_groups import preserve_assistant_config
                previous = self.export_root / 'ros_ws' / 'src' / moveit_dir.name
                settings_report = preserve_assistant_config(previous, moveit_dir, Path(result['bundle_dir']), description)
                if settings_report:
                    result['moveit_settings'] = settings_report
            preflight = inspect_candidate(description, moveit_dir)
            if result.get('moveit_settings', {}).get('review_files'):
                preflight['diagnostics'].append({
                    'code': 'moveit_settings_review_required', 'severity': 'warning', 'targets': [moveit_dir.name],
                    'observed': result['moveit_settings']['review_files'], 'expected': '현재 컨트롤러·모듈 설정과 일치',
                    'action': result['moveit_settings']['message'] + ' (' + result['moveit_settings']['previous_relative_path'] + ')'})
                preflight['status'] = 'error' if preflight['status'] == 'error' else 'warning'
                preflight['summary']['warnings'] = preflight['summary'].get('warnings', 0) + 1
            analysis = description / "analysis"
            analysis.mkdir(exist_ok=True)
            (analysis / "export_preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._pending_export = {
                "token": token, "stage": stage, "result": result,
                "report": preflight, "state": export_state, "tree": export_tree,
                "revision": self.revision, "fingerprint": self._export_fingerprint(),
                "prepared_at": time.monotonic(),
            }
            return {"token": token, "preflight": preflight,
                    "link_count": result.get("link_count"), "joint_count": result.get("joint_count")}
        except Exception:
            if stage.is_dir():
                shutil.rmtree(self._owned_export_stage(stage))
            raise

    def commit_export(self, token: str, acknowledge_warnings: bool) -> dict:
        pending = self._pending_export
        if pending is None or pending["token"] != token:
            raise ValueError("Export token is no longer valid")
        if (self.revision != pending["revision"] or
                self._export_fingerprint() != pending["fingerprint"] or
                time.monotonic() - pending["prepared_at"] > 600):
            raise ValueError("프로젝트가 변경됐거나 준비 시간이 만료됐습니다. 다시 익스포트해 주세요.")
        report = pending["report"]
        if any(item["severity"] == "error" for item in report["diagnostics"]):
            raise ValueError("Preflight error: 물성 오류를 수정한 뒤 다시 익스포트해 주세요.")
        if not acknowledge_warnings and any(
            item["severity"] in {"warning", "not_checked"} for item in report["diagnostics"]
        ):
            raise ValueError("Preflight warning: 경고와 미검사 항목을 확인해 주세요.")
        stage = self._owned_export_stage(pending["stage"])
        result = pending["result"]
        staged_payload = Path(result["bundle_dir"] or result["save_dir"]).resolve()
        if staged_payload.parent != stage:
            raise ValueError("Prepared export payload is outside its stage")
        target = self.export_root.resolve() / staged_payload.name
        if target.parent != self.export_root.resolve():
            raise ValueError("Export destination is outside the selected root")
        backup = self.export_root.resolve() / f".petasos-backup-{token}"
        if backup.exists():
            raise ValueError("Export backup path already exists")
        state_path = self.project_dir / "project_state.json"
        state_temp = self.project_dir / f".project_state-{token}.json"
        saved_state = copy.deepcopy(pending["state"])
        saved_state["tree"] = pending["tree"]
        state_temp.write_text(json.dumps(saved_state, ensure_ascii=False, indent=2), encoding="utf-8")
        moved_old = False
        moved_new = False
        try:
            if target.exists():
                os.replace(target, backup)
                moved_old = True
            os.replace(staged_payload, target)
            moved_new = True
            os.replace(state_temp, state_path)
        except Exception:
            if moved_new and target.exists():
                os.replace(target, staged_payload)
            if moved_old and backup.exists():
                os.replace(backup, target)
            state_temp.unlink(missing_ok=True)
            raise
        self.state = saved_state
        self.archive_path = None
        relative_description = Path(result["save_dir"]).resolve().relative_to(staged_payload)
        self.description_dir = target / relative_description
        self.bundle_dir = target if result.get("bundle_dir") else None
        self._pending_export = None
        if stage.is_dir():
            shutil.rmtree(stage, ignore_errors=True)
        self._prune_export_backups(keep=backup if moved_old else None)
        return {**result, "save_dir": str(self.description_dir),
                "bundle_dir": str(self.bundle_dir) if self.bundle_dir else None,
                "preflight": report,
                "previous_export_backup": str(backup) if moved_old else None}

    def export(
        self, tree: dict, fix_to_world: bool, include_moveit: bool = False,
        root_joint_mode: str | None = None, acknowledge_warnings: bool = False,
    ) -> dict:
        prepared = self.prepare_export(tree, fix_to_world, include_moveit, root_joint_mode)
        return self.commit_export(prepared["token"], acknowledge_warnings)


def create_app(store: ProjectStore | None = None) -> Flask:
    app = Flask(__name__)
    project_store = store or ProjectStore()
    register_module_api(app, project_store)

    @app.before_request
    def lock_editor_mutations():
        if request.method == 'POST' and request.is_json:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify(error='Request body must be a JSON object.'), 400
            if 'tree' in payload and not isinstance(payload['tree'], dict):
                return jsonify(error='Robot tree must be a JSON object.'), 400
        if request.method == 'POST' or request.path == '/data':
            project_store.module_lock.acquire()
            g.module_lock_held = True
        if request.path in {'/workspace/save', '/save', '/export/prepare'}:
            payload = request.get_json(silent=True) or {}
            tree = payload.get('tree') or payload
            if (tree.get('_modules') or (project_store.state or {}).get('tree', {}).get('_modules')):
                if tree.get('_module_revision') != project_store.revision:
                    return jsonify(error='프로젝트가 변경됐습니다. 새로 불러온 후 다시 저장하세요.'), 409

    @app.teardown_request
    def unlock_editor_mutations(error=None):
        if getattr(g, 'module_lock_held', False):
            g.module_lock_held = False
            project_store.module_lock.release()
    wsl_rviz_runner = WslRvizRunner()
    wsl_moveit_runner = WslMoveItRunner(
        APP_ROOT / "moveit" / "validate_moveit_config.py"
    )

    @app.get("/")
    def index():
        return HTML_CONTENT

    @app.get("/health")
    def health():
        return jsonify({
            "application": "petasos-a2",
            "status": "ok",
            "pid": os.getpid(),
        })

    @app.get("/data")
    def data():
        return jsonify(project_store.tree())

    @app.post("/workspace/save")
    def save_workspace():
        payload = request.get_json(silent=True) or {}
        try:
            result = project_store.save_workspace(
                payload.get("tree") or {},
                payload.get("editor_settings") or {},
                payload.get("save_name") or "",
            )
            return jsonify({"status": "saved", **result})
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"프리뷰 작업 저장 실패: {exc}"}), 500

    @app.get("/workspace/list")
    def list_workspaces():
        if request.args.get("all_projects") == "1":
            return jsonify({"items": project_store.list_all_workspaces()})
        return jsonify({"items": project_store.list_workspaces()})

    @app.post("/workspace/reload")
    def reload_workspace():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "status": "loaded",
                "tree": project_store.reload_workspace(
                    payload.get("save_name") or "",
                    payload.get("project_id") or "",
                ),
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"프리뷰 작업 불러오기 실패: {exc}"}), 500

    @app.get("/static/three/<path:filename>")
    def static_three(filename: str):
        vendor = APP_ROOT / "URDF_Exporter" / "vendor" / "three"
        return send_from_directory(vendor, filename)

    @app.get("/static/modules/<filename>")
    def static_modules(filename: str):
        if filename not in {
            "module_selection.js", "module_ui.js", "sensor_ui.js",
            "mimic_preview.js", "face_alignment.js", "joint_zero_frame.js",
            "joint_mate_alignment.js", "controller_interfaces.js",
        }:
            return "", 404
        return send_from_directory(APP_ROOT / "URDF_Exporter" / "core", filename)

    @app.get("/meshes/<path:filename>")
    def mesh(filename: str):
        if not project_store.project_dir:
            return "", 404
        return send_from_directory(project_store.project_dir / "meshes", filename)

    @app.post("/import")
    def import_files():
        try:
            state = project_store.import_files(
                request.form.get("project_name", "robot"),
                request.files.getlist("files"),
                request.files.getlist("relative_files"),
            )
            return jsonify({
                "status": "imported",
                "project_name": state["project_name"],
                "report": state["report"],
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"가져오기 실패: {exc}"}), 500

    @app.post("/reimport")
    def reimport_files():
        try:
            raw_tree = request.form.get("tree", "")
            try:
                edited_tree = json.loads(raw_tree)
            except json.JSONDecodeError as exc:
                raise ImportFailure("보존할 현재 편집 데이터를 읽지 못했습니다.") from exc
            state = project_store.reimport_files(
                request.files.getlist("files"),
                edited_tree,
                request.files.getlist("relative_files"),
            )
            return jsonify({
                "status": "reimported",
                "project_name": state["project_name"],
                "report": state["report"],
                "reimport": state["report"].get("reimport", {}),
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"CAD 업데이트 실패: {exc}"}), 500

    @app.post("/import/inventor-active")
    def import_inventor_active():
        payload = request.get_json(silent=True) or {}
        try:
            state = project_store.import_active_inventor(
                payload.get("project_name", "robot")
            )
            return jsonify({
                "status": "imported",
                "project_name": state["project_name"],
                "report": state["report"],
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"현재 Inventor 가져오기 실패: {exc}"}), 500

    @app.post("/import/inventor-file")
    def import_inventor_file():
        payload = request.get_json(silent=True) or {}
        try:
            assembly_path = _choose_inventor_file()
            if assembly_path is None:
                return jsonify({"status": "cancelled"})
            state = project_store.import_inventor_path(
                payload.get("project_name", assembly_path.stem),
                assembly_path,
            )
            return jsonify({
                "status": "imported",
                "project_name": state["project_name"],
                "source_path": str(assembly_path),
                "report": state["report"],
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"원본 IAM 가져오기 실패: {exc}"}), 500

    @app.post("/reimport/inventor-active")
    def reimport_inventor_active():
        payload = request.get_json(silent=True) or {}
        try:
            state = project_store.reimport_active_inventor(payload.get("tree") or {})
            return jsonify({
                "status": "reimported",
                "project_name": state["project_name"],
                "report": state["report"],
                "reimport": state["report"].get("reimport", {}),
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"현재 Inventor 업데이트 실패: {exc}"}), 500

    @app.post("/reimport/inventor-file")
    def reimport_inventor_file():
        payload = request.get_json(silent=True) or {}
        try:
            assembly_path = _choose_inventor_file()
            if assembly_path is None:
                return jsonify({"status": "cancelled"})
            state = project_store.reimport_inventor_path(
                assembly_path,
                payload.get("tree") or {},
            )
            return jsonify({
                "status": "reimported",
                "project_name": state["project_name"],
                "source_path": str(assembly_path),
                "report": state["report"],
                "reimport": state["report"].get("reimport", {}),
            })
        except ImportFailure as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"원본 IAM 업데이트 실패: {exc}"}), 500

    def _export_payload():
        payload = request.get_json(silent=True) or {}
        return payload, payload.get("tree") or {}, bool(payload.get("fix_to_world", True)), bool(payload.get("include_moveit", False)), payload.get("root_joint_mode")

    @app.post("/export/prepare")
    def export_prepare():
        _payload, tree, fixed, moveit, root_mode = _export_payload()
        try:
            return jsonify(project_store.prepare_export(tree, fixed, moveit, root_mode))
        except (ImportFailure, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"익스포트 검사 실패: {exc}"}), 500

    @app.post("/export/commit")
    def export_commit():
        payload = request.get_json(silent=True) or {}
        try:
            result = project_store.commit_export(
                str(payload.get("token") or ""), bool(payload.get("acknowledge_warnings", False)),
            )
            return jsonify({"status": "ok", **result, "download_url": None})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"error": f"익스포트 반영 실패: {exc}"}), 500

    @app.post("/export/cancel")
    def export_cancel():
        payload = request.get_json(silent=True) or {}
        try:
            project_store.cancel_export(str(payload.get("token") or ""))
            return jsonify({"status": "cancelled"})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/save")
    def save():
        payload, tree, fixed, moveit, root_mode = _export_payload()
        try:
            prepared = project_store.prepare_export(tree, fixed, moveit, root_mode)
            report = prepared["preflight"]
            # The editor uses prepare/commit and requires an explicit checkbox.
            # Older /save integrations have no review step; retain their API
            # behavior while returning the full diagnostic report to callers.
            acknowledged = bool(payload.get("acknowledge_warnings", True))
            if any(item["severity"] == "error" for item in report["diagnostics"]):
                project_store.cancel_export(prepared["token"])
                return jsonify({"error": "익스포트 전 물성 오류를 수정해 주세요.", **prepared}), 422
            if not acknowledged and any(
                item["severity"] in {"warning", "not_checked"} for item in report["diagnostics"]
            ):
                return jsonify({"error": "경고·미검사 항목을 확인하고 승인해 주세요.", **prepared}), 409
            result = project_store.commit_export(prepared["token"], acknowledged)
            return jsonify({"status": "ok", **result, "download_url": None})
        except (ImportFailure, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"URDF 생성 실패: {exc}"}), 500

    @app.get("/download")
    def download():
        return jsonify({
            "error": "ZIP 내보내기는 사용하지 않습니다. export/ros_ws 폴더를 직접 사용하세요."
        }), 410

    @app.post("/open-export-folder")
    def open_export_folder():
        if project_store.description_dir is None:
            return jsonify({"error": "먼저 ROS 2 패키지를 생성해 주세요."}), 404
        package_dir = project_store.bundle_dir or project_store.description_dir
        try:
            _open_folder(package_dir)
            return jsonify({"status": "opened", "path": str(package_dir)})
        except (OSError, FileNotFoundError) as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/rviz/wsl")
    def launch_wsl_rviz():
        package_dir = project_store.description_dir
        if package_dir is None:
            return jsonify({"error": "내보낸 description 패키지를 찾지 못했습니다."}), 404
        try:
            return jsonify(wsl_rviz_runner.start(package_dir))
        except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
            wsl_rviz_runner._set_state("error", str(exc))
            return jsonify({"error": str(exc)}), 409

    @app.get("/rviz/wsl/status")
    def wsl_rviz_status():
        return jsonify(wsl_rviz_runner.snapshot())

    @app.post("/rviz/wsl/stop")
    def stop_wsl_rviz():
        try:
            return jsonify(wsl_rviz_runner.stop())
        except (subprocess.SubprocessError, OSError) as exc:
            wsl_rviz_runner._set_state("error", str(exc))
            return jsonify({"error": str(exc)}), 500

    @app.post("/moveit/wsl/assistant")
    def launch_wsl_moveit_assistant():
        if project_store.description_dir is None:
            return jsonify({"error": "먼저 ROS 2 패키지를 생성해 주세요."}), 404
        if project_store.bundle_dir is None:
            return jsonify({
                "error": "기본 ROS 2 패키지로 익스포트했습니다. MoveIt 단일 ros_ws를 선택해 다시 생성하세요."
            }), 409
        package_dir = project_store.description_dir
        if package_dir is None:
            return jsonify({"error": "내보낸 description 패키지를 찾지 못했습니다."}), 404
        try:
            return jsonify(wsl_moveit_runner.start_assistant(package_dir))
        except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
            wsl_moveit_runner._set_state("error", str(exc))
            return jsonify({"error": str(exc)}), 409

    @app.post("/moveit/wsl/demo")
    def launch_wsl_moveit_demo():
        if project_store.description_dir is None:
            return jsonify({"error": "먼저 ROS 2 패키지를 생성해 주세요."}), 404
        if project_store.bundle_dir is None:
            return jsonify({
                "error": "기본 ROS 2 패키지에는 MoveIt 설정이 없습니다."
            }), 409
        package_dir = project_store.description_dir
        if package_dir is None:
            return jsonify({"error": "내보낸 description 패키지를 찾지 못했습니다."}), 404
        try:
            return jsonify(wsl_moveit_runner.start_demo(package_dir))
        except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
            wsl_moveit_runner._set_state("error", str(exc))
            return jsonify({"error": str(exc)}), 409

    @app.get("/moveit/wsl/status")
    def wsl_moveit_status():
        return jsonify(wsl_moveit_runner.snapshot())

    @app.post("/moveit/wsl/smoke")
    def run_wsl_moveit_smoke():
        try:
            return jsonify(wsl_moveit_runner.run_smoke())
        except (
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
            OSError,
        ) as exc:
            return jsonify({"error": str(exc)}), 409

    @app.post("/moveit/wsl/stop")
    def stop_wsl_moveit():
        try:
            return jsonify(wsl_moveit_runner.stop())
        except (subprocess.SubprocessError, OSError) as exc:
            wsl_moveit_runner._set_state("error", str(exc))
            return jsonify({"error": str(exc)}), 500

    @app.post("/wsl/gui/stop")
    def stop_all_wsl_gui_sessions():
        """Used by browser refresh/close so the next GUI launch is clean."""
        errors = []
        for name, runner in (
            ("RViz", wsl_rviz_runner),
            ("MoveIt", wsl_moveit_runner),
        ):
            try:
                runner.stop()
            except (subprocess.SubprocessError, OSError) as exc:
                errors.append(f"{name}: {exc}")
        try:
            cleanup = app.config["PETASOS_WSL_GUI_CLEANUP"]()
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"WSL cleanup: {exc}")
            cleanup = {"status": "warning", "stopped": 0}

        wsl_rviz_runner._set_state("stopped", "RViz가 종료되었습니다.")
        wsl_moveit_runner._set_state("stopped", "MoveIt 작업이 종료되었습니다.")
        payload = {
            "status": "stopped" if not errors else "warning",
            "message": "RViz와 MoveIt 세션을 정리했습니다.",
            "stopped": cleanup.get("stopped", 0),
        }
        if errors:
            payload["warnings"] = errors
        return jsonify(payload)

    app.config["PETASOS_STORE"] = project_store
    app.config["PETASOS_WSL_RVIZ"] = wsl_rviz_runner
    app.config["PETASOS_WSL_MOVEIT"] = wsl_moveit_runner
    app.config["PETASOS_WSL_GUI_CLEANUP"] = _cleanup_wsl_gui_processes
    return app


def _petasos_server_is_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health",
            timeout=0.7,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return (
            response.status == 200
            and payload.get("application") == "petasos-a2"
            and payload.get("status") == "ok"
        )
    except (
        OSError,
        ValueError,
        urllib.error.HTTPError,
        urllib.error.URLError,
    ):
        return False


def _open_browser_when_ready(port: int, url: str) -> None:
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if _petasos_server_is_healthy(port):
            webbrowser.open(url)
            return
        time.sleep(0.1)


def run() -> bool:
    port = int(os.environ.get("PETASOS_PORT", "5050"))
    url = f"http://127.0.0.1:{port}/"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            if not _petasos_server_is_healthy(port):
                raise RuntimeError(
                    f"Port {port} is occupied by another program. "
                    "Close that program and run start_petasos.cmd again."
                )
            print(
                "Petasos is already running in another CMD window. "
                "That window owns the server."
            )
            if os.environ.get("PETASOS_NO_BROWSER") != "1":
                webbrowser.open(url)
            return False

    app = create_app()
    if os.environ.get("PETASOS_NO_BROWSER") != "1":
        threading.Thread(
            target=_open_browser_when_ready, args=(port, url), daemon=True
        ).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    return True
