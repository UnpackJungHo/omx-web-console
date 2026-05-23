from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .ws_manager import WebSocketManager


LAUNCH_EVENT_PREFIX = "__OMX_LAUNCH_EVENT__"


@dataclass
class LaunchStatus:
    running: bool
    mode: str | None
    pid: int | None
    started_at: float | None
    command: list[str] | None
    hardware_port: str | None
    error: str | None = None


class LaunchManager:
    def __init__(self, ws_manager: WebSocketManager | None = None) -> None:
        self._workspace = Path(os.getenv("OMX_ROS_WS", "/home/kjhz/omx_ws"))
        self._ros_setup_script = Path(
            os.getenv(
                "OMX_ROS_DISTRO_SETUP",
                f"/opt/ros/{os.getenv('ROS_DISTRO', 'jazzy')}/setup.bash",
            )
        )
        self._setup_script = Path(
            os.getenv("OMX_ROS_SETUP", str(self._workspace / "install" / "setup.bash"))
        )
        self._launch_log = Path(
            os.getenv(
                "OMX_LAUNCH_LOG",
                str(Path.home() / ".ros" / "log" / "omx_web_bridge_launch.log"),
            )
        )
        self._hardware_port = os.getenv("OMX_HARDWARE_PORT")
        self._process: subprocess.Popen[str] | None = None
        self._output_thread: threading.Thread | None = None
        self._mode: str | None = None
        self._started_at: float | None = None
        self._command: list[str] | None = None
        self._active_port: str | None = None
        self._error: str | None = None
        self._motion_process: subprocess.Popen[str] | None = None
        self._motion_error: str | None = None
        self._ws_manager = ws_manager
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def start(self, mode: str) -> dict:
        if mode not in {"mock", "real"}:
            return {
                "ok": False,
                "code": "invalid_mode",
                "message": "mode must be 'mock' or 'real'.",
                "status": asdict(self.status()),
            }

        self._refresh_process_state()

        hardware_port = None
        if mode == "real":
            hardware_port = self.detect_hardware_port()
            if hardware_port is None:
                return {
                    "ok": False,
                    "code": "hardware_disconnected",
                    "message": "실기기 연결을 확인해주세요.",
                    "status": asdict(self.status()),
                }

        if self._process is not None and self._mode == mode:
            return {
                "ok": True,
                "code": "already_running",
                "message": "이미 해당 하드웨어 모드로 실행 중입니다.",
                "status": asdict(self.status()),
            }

        self.stop()
        self.stop_motion_server()

        if not self._setup_script.exists():
            self._error = f"ROS setup script not found: {self._setup_script}"
            return {
                "ok": False,
                "code": "setup_missing",
                "message": self._error,
                "status": asdict(self.status()),
            }

        command = self._build_command(mode, hardware_port)
        try:
            self._process = subprocess.Popen(
                command,
                cwd=str(self._workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                start_new_session=True,
                text=True,
            )
            self._output_thread = threading.Thread(
                target=self._stream_process_output,
                args=(self._process,),
                name="omx-web-launch-output",
                daemon=True,
            )
            self._output_thread.start()
        except Exception as exc:
            self._error = str(exc)
            self._process = None
            return {
                "ok": False,
                "code": "launch_failed",
                "message": self._error,
                "status": asdict(self.status()),
            }

        self._mode = mode
        self._started_at = time.time()
        self._command = command
        self._active_port = hardware_port
        self._error = None
        return {
            "ok": True,
            "code": "started",
            "message": "ROS launch를 시작했습니다.",
            "status": asdict(self.status()),
        }

    def stop(self) -> None:
        self._refresh_process_state()
        if self._process is None:
            return

        self._terminate_process()
        self._clear_process()

    def stop_response(self) -> dict:
        self.stop()
        self.stop_motion_server()
        return {
            "ok": True,
            "code": "stopped",
            "message": "ROS launch를 종료했습니다.",
            "status": asdict(self.status()),
        }

    def _terminate_process(self) -> None:
        if self._process is None:
            return

        self._terminate_popen(self._process)
        if self._output_thread is not None and self._output_thread.is_alive():
            self._output_thread.join(timeout=1.0)

    def _terminate_popen(self, process: subprocess.Popen[str]) -> None:
        session_id = process.pid
        for sig, timeout in (
            (signal.SIGINT, 8.0),
            (signal.SIGTERM, 4.0),
            (signal.SIGKILL, 2.0),
        ):
            self._signal_session(session_id, sig)
            if self._wait_for_session_exit(process, session_id, timeout):
                return

    def _signal_session(self, session_id: int, sig: signal.Signals) -> None:
        try:
            os.killpg(session_id, sig)
        except ProcessLookupError:
            pass
        except Exception:
            pass

        for pid in self._session_member_pids(session_id):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except Exception:
                pass

    def _wait_for_session_exit(
        self,
        process: subprocess.Popen[str],
        session_id: int,
        timeout: float,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                try:
                    process.wait(timeout=0)
                except Exception:
                    pass
            if not self._session_member_pids(session_id):
                return True
            time.sleep(0.1)
        return False

    def _session_member_pids(self, session_id: int) -> list[int]:
        pids: list[int] = []
        for stat_path in Path("/proc").glob("[0-9]*/stat"):
            try:
                pid = int(stat_path.parent.name)
                stat = stat_path.read_text(encoding="utf-8")
                fields = stat.rsplit(") ", 1)[1].split()
                if int(fields[3]) == session_id:
                    pids.append(pid)
            except Exception:
                continue
        return pids

    def _clear_process(self) -> None:
        self._process = None
        self._output_thread = None
        self._mode = None
        self._started_at = None
        self._command = None
        self._active_port = None

    def status(self) -> LaunchStatus:
        self._refresh_process_state()
        return LaunchStatus(
            running=self._process is not None,
            mode=self._mode,
            pid=self._process.pid if self._process is not None else None,
            started_at=self._started_at,
            command=self._command,
            hardware_port=self._active_port,
            error=self._error,
        )

    def detect_hardware_port(self) -> str | None:
        candidates: list[str] = []
        if self._hardware_port:
            candidates.append(self._hardware_port)
        candidates.extend(str(path) for path in sorted(Path("/dev").glob("ttyACM*")))
        candidates.extend(str(path) for path in sorted(Path("/dev").glob("ttyUSB*")))

        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def _build_command(self, mode: str, hardware_port: str | None) -> list[str]:
        control_args = self._control_launch_args(mode, hardware_port)
        control_command = shlex.join(control_args)
        moveit_command = "ros2 launch omx_bringup omx_moveit.launch.py start_rviz:=false"
        motion_command = "ros2 launch omx_motion_server motion_server.launch.py"
        perception_command = "ros2 launch omx_perception perception.launch.py"
        control_timeout = self._readiness_timeout("OMX_CONTROL_READY_TIMEOUT", 90)
        moveit_timeout = self._readiness_timeout("OMX_MOVEIT_READY_TIMEOUT", 90)
        motion_timeout = self._readiness_timeout("OMX_MOTION_READY_TIMEOUT", 90)
        perception_timeout = self._readiness_timeout("OMX_PERCEPTION_READY_TIMEOUT", 75)

        shell_command = (
            "set -e\n"
            f"{self._shell_log_setup_command('robot_launch')}"
            f"{self._source_script_command(self._ros_setup_script)}"
            f"source {shlex.quote(str(self._setup_script))}\n"
            "pids=()\n"
            "emit_event() {\n"
            "  python3 -c 'import json,sys,time; print(\"__OMX_LAUNCH_EVENT__\" + json.dumps({\"type\":\"launch_event\",\"stage\":sys.argv[1],\"state\":sys.argv[2],\"message\":sys.argv[3],\"command\":sys.argv[4],\"at\":time.time()}, ensure_ascii=False), flush=True)' \"$1\" \"$2\" \"$3\" \"${4:-}\"\n"
            "}\n"
            "cleanup() {\n"
            "  trap - INT TERM EXIT\n"
            "  for pid in \"${pids[@]}\"; do\n"
            "    kill -INT \"-$pid\" 2>/dev/null || kill -INT \"$pid\" 2>/dev/null || true\n"
            "  done\n"
            "  sleep 2\n"
            "  for pid in \"${pids[@]}\"; do\n"
            "    kill -TERM \"-$pid\" 2>/dev/null || kill -TERM \"$pid\" 2>/dev/null || true\n"
            "  done\n"
            "}\n"
            "check_stage_processes() {\n"
            "  local stage=\"$1\"\n"
            "  for pid in \"${pids[@]}\"; do\n"
            "    if ! kill -0 \"$pid\" 2>/dev/null; then\n"
            "      local code=0\n"
            "      wait \"$pid\" || code=\"$?\"\n"
            "      emit_event \"$stage\" error \"process exited before readiness (pid=$pid code=$code)\" \"\"\n"
            "      return 1\n"
            "    fi\n"
            "  done\n"
            "}\n"
            "wait_for_condition() {\n"
            "  local stage=\"$1\"\n"
            "  local timeout_sec=\"$2\"\n"
            "  local description=\"$3\"\n"
            "  shift 3\n"
            "  local deadline=$((SECONDS + timeout_sec))\n"
            "  emit_event \"$stage\" idle \"waiting for $description\" \"$description\"\n"
            "  until \"$@\"; do\n"
            "    check_stage_processes \"$stage\"\n"
            "    if [ \"$SECONDS\" -ge \"$deadline\" ]; then\n"
            "      emit_event \"$stage\" error \"readiness timeout after ${timeout_sec}s: $description\" \"$description\"\n"
            "      return 1\n"
            "    fi\n"
            "    sleep 1\n"
            "  done\n"
            "  emit_event \"$stage\" valid \"ready: $description\" \"$description\"\n"
            "}\n"
            "start_stage() {\n"
            "  local stage=\"$1\"\n"
            "  local command_label=\"$2\"\n"
            "  shift 2\n"
            "  emit_event \"$stage\" idle \"starting: $command_label\" \"$command_label\"\n"
            "  \"$@\" &\n"
            "  local pid=\"$!\"\n"
            "  pids+=(\"$pid\")\n"
            "  emit_event \"$stage\" idle \"process started pid=$pid\" \"$command_label\"\n"
            "}\n"
            "has_topic() { ros2 topic list 2>/dev/null | grep -Fxq \"$1\"; }\n"
            "has_service() { ros2 service list 2>/dev/null | grep -Fxq \"$1\"; }\n"
            "has_action() { ros2 action list 2>/dev/null | grep -Fxq \"$1\"; }\n"
            "has_node() { ros2 node list 2>/dev/null | grep -Fxq \"$1\"; }\n"
            "controller_active() { ros2 control list_controllers 2>/dev/null | awk -v name=\"$1\" '$1 == name && $NF == \"active\" { found=1 } END { exit !found }'; }\n"
            "joint_state_sample() { timeout 3 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState >/dev/null 2>&1; }\n"
            "control_ready() { controller_active joint_state_broadcaster && controller_active arm_controller && controller_active gripper_controller && has_topic /joint_states && joint_state_sample; }\n"
            "moveit_ready() { has_node /move_group && has_service /check_state_validity; }\n"
            "motion_ready() { has_action /omx/move_to_named && has_action /omx/move_to_pose && has_action /omx/move_to_joints && has_action /omx/gripper_command; }\n"
            "perception_ready() { has_service /perception/get_box_cup_keypoints && has_service /perception/get_box_cup_world_poses; }\n"
            "trap cleanup INT TERM EXIT\n"
            f"start_stage control {shlex.quote(control_command)} {control_command}\n"
            f"wait_for_condition control {control_timeout} 'controllers active and /joint_states sample received' control_ready\n"
            f"start_stage moveit {shlex.quote(moveit_command)} ros2 launch omx_bringup omx_moveit.launch.py start_rviz:=false\n"
            f"wait_for_condition moveit {moveit_timeout} '/move_group and /check_state_validity available' moveit_ready\n"
            f"start_stage motion_server {shlex.quote(motion_command)} ros2 launch omx_motion_server motion_server.launch.py\n"
            f"wait_for_condition motion_server {motion_timeout} '/omx motion action servers available' motion_ready\n"
            f"start_stage perception {shlex.quote(perception_command)} ros2 launch omx_perception perception.launch.py\n"
            "perception_status=0\n"
            f"wait_for_condition perception {perception_timeout} '/perception services available' perception_ready || perception_status=\"$?\"\n"
            "if [ \"$perception_status\" -eq 0 ]; then\n"
            "  emit_event all valid 'all launch stages ready' ''\n"
            "else\n"
            "  emit_event all error 'core launch stages ready; perception not ready' ''\n"
            "fi\n"
            "wait"
        )
        return [
            "/bin/bash",
            "-lc",
            shell_command,
        ]

    def _control_launch_args(self, mode: str, hardware_port: str | None) -> list[str]:
        control_args = [
            "ros2",
            "launch",
            "omx_bringup",
            "omx_control.launch.py",
            "start_rviz:=false",
        ]
        if mode == "mock":
            control_args.append("use_mock_hardware:=true")
        else:
            control_args.append("use_mock_hardware:=false")
            if hardware_port:
                control_args.append(f"port_name:={hardware_port}")

        return control_args

    def _refresh_process_state(self) -> None:
        if self._process is None:
            return
        return_code = self._process.poll()
        if return_code is not None:
            self._error = f"ROS launch exited with code {return_code}."
            self._clear_process()
            return

    def start_motion_server(self) -> dict:
        if self._motion_process is not None and self._motion_process.poll() is None:
            return {"ok": True, "code": "already_running"}

        if not self._setup_script.exists():
            self._motion_error = f"ROS setup script not found: {self._setup_script}"
            return {"ok": False, "code": "setup_missing", "message": self._motion_error}

        shell_command = (
            "set -e\n"
            f"{self._shell_log_setup_command('motion_server')}"
            f"{self._source_script_command(self._ros_setup_script)}"
            f"source {shlex.quote(str(self._setup_script))}\n"
            "pid=\n"
            "cleanup() {\n"
            "  trap - INT TERM EXIT\n"
            "  if [ -n \"$pid\" ]; then\n"
            "    kill -INT \"-$pid\" 2>/dev/null || kill -INT \"$pid\" 2>/dev/null || true\n"
            "    sleep 2\n"
            "    kill -TERM \"-$pid\" 2>/dev/null || kill -TERM \"$pid\" 2>/dev/null || true\n"
            "  fi\n"
            "}\n"
            "trap cleanup INT TERM EXIT\n"
            "ros2 launch omx_motion_server motion_server.launch.py &\n"
            "pid=\"$!\"\n"
            "wait \"$pid\""
        )
        try:
            self._motion_process = subprocess.Popen(
                ["/bin/bash", "-lc", shell_command],
                cwd=str(self._workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
            )
            self._motion_error = None
            return {"ok": True, "code": "started"}
        except Exception as exc:
            self._motion_error = str(exc)
            self._motion_process = None
            return {"ok": False, "code": "launch_failed", "message": self._motion_error}

    def stop_motion_server(self) -> None:
        if self._motion_process is None:
            return
        self._terminate_popen(self._motion_process)
        self._motion_process = None

    def _source_script_command(self, script: Path) -> str:
        if not script.exists():
            return ""
        return f"source {shlex.quote(str(script))}\n"

    def _shell_log_setup_command(self, label: str) -> str:
        return (
            f"mkdir -p {shlex.quote(str(self._launch_log.parent))}\n"
            f"printf '\\n--- omx_web_bridge {label} %s ---\\n' \"$(date --iso-8601=seconds)\"\n"
        )

    def _stream_process_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return

        try:
            self._launch_log.parent.mkdir(parents=True, exist_ok=True)
            with self._launch_log.open("a", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    self._handle_process_output_line(line)
        except Exception as exc:
            self._error = f"Launch output reader failed: {exc}"

    def _handle_process_output_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped.startswith(LAUNCH_EVENT_PREFIX):
            return
        raw = stripped[len(LAUNCH_EVENT_PREFIX):]
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(event, dict):
            self._broadcast_launch_event(event)

    def _broadcast_launch_event(self, event: dict[str, Any]) -> None:
        if self._ws_manager is None:
            return
        event.setdefault("type", "launch_event")
        self._ws_manager.broadcast_threadsafe(self._loop, event)

    @staticmethod
    def _readiness_timeout(env_name: str, default: int) -> int:
        raw = os.getenv(env_name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(1, value)
