from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import load_joint_map
from .ws_manager import WebSocketManager


MOVE_TO_POSE_GOAL_EXAMPLE: dict[str, Any] = {
    "target_pose": {
        "header": {
            "frame_id": "world",
        },
        "pose": {
            "position": {
                "x": 0.33128309872740647,
                "y": 0.008654711230646865,
                "z": 0.15,
            },
            "orientation": {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "w": 1.0,
            },
        },
    },
    "velocity_scale": 0.2,
    "plan_only": False,
}

ACTION_GOAL_EXAMPLES: dict[str, dict[str, Any]] = {
    "/omx/move_to_pose": MOVE_TO_POSE_GOAL_EXAMPLE,
    "omx_interfaces/action/MoveToPose": MOVE_TO_POSE_GOAL_EXAMPLE,
    "omx_interfaces/action/MoveToJoints": {
        "joint_names": ["joint1", "joint2", "joint3", "joint4", "joint5"],
        "positions": [0.0, -1.0, 1.0, 0.5, 0.0],
        "velocity_scale": 0.2,
    },
    "omx_interfaces/action/MoveToNamed": {
        "name": "home",
    },
    "omx_interfaces/action/GripperCommand": {
        "position": 1.0,
        "max_effort": 0.0,
    },
    "omx_interfaces/action/PickDetected": {
        "object_color": "red",
        "retry_on_fail": True,
    },
    "omx_interfaces/action/PickPlace": {
        "object_color": "red",
        "retry_on_fail": False,
    },
}

SERVICE_REQUEST_EXAMPLES: dict[str, dict[str, Any]] = {
    "omx_interfaces/srv/PlanToJoints": {
        "joint_names": ["joint1", "joint2", "joint3", "joint4", "joint5"],
        "positions": [0.0, -1.0, 1.0, 0.5, 0.0],
        "velocity_scale": 0.2,
    },
    "omx_interfaces/srv/ExecutePlan": {
        "plan_id": "paste_plan_id_from_plan_to_joints",
    },
    "omx_interfaces/srv/ClearPlan": {},
    "omx_interfaces/srv/GetBlockPoses": { },
    "omx_interfaces/srv/GetTop4Keypoints": {
        "publish_debug": True,
    },
}

CHART_TOPIC_TYPES = {
    "/gripper/grasp_force_estimate": ["std_msgs/msg/Float32"],
}
CHART_TOPIC_NAMES = set(CHART_TOPIC_TYPES)


rclpy = None
get_action_names_and_types = None
ActionClient = None
SingleThreadedExecutor = None
HistoryPolicy = None
QoSProfile = None
ReliabilityPolicy = None
RobotState = None
GetStateValidity = None
JointState = None
GripperCommand = None
MoveToJoints = None
MoveToNamed = None
ClearPlan = None
ExecutePlan = None
PlanToJoints = None
message_to_ordereddict = None
set_message_fields = None
get_action = None
get_message = None
get_service = None
ROS_IMPORT_ERROR: str | None = None


def _import_ros_runtime() -> bool:
    global rclpy
    global get_action_names_and_types
    global ActionClient
    global SingleThreadedExecutor
    global HistoryPolicy
    global QoSProfile
    global ReliabilityPolicy
    global RobotState
    global GetStateValidity
    global JointState
    global GripperCommand
    global MoveToJoints
    global MoveToNamed
    global ClearPlan
    global ExecutePlan
    global PlanToJoints
    global message_to_ordereddict
    global set_message_fields
    global get_action
    global get_message
    global get_service
    global ROS_IMPORT_ERROR

    if rclpy is not None:
        return True

    try:
        import rclpy as imported_rclpy
        from rclpy.action import ActionClient as ImportedActionClient
        from rclpy.action import get_action_names_and_types as imported_get_action_names_and_types
        from rclpy.executors import SingleThreadedExecutor as ImportedSingleThreadedExecutor
        from rclpy.qos import HistoryPolicy as ImportedHistoryPolicy
        from rclpy.qos import QoSProfile as ImportedQoSProfile
        from rclpy.qos import ReliabilityPolicy as ImportedReliabilityPolicy
        from moveit_msgs.msg import RobotState as ImportedRobotState
        from moveit_msgs.srv import GetStateValidity as ImportedGetStateValidity
        from sensor_msgs.msg import JointState as ImportedJointState
        from omx_interfaces.action import GripperCommand as ImportedGripperCommand
        from omx_interfaces.action import MoveToJoints as ImportedMoveToJoints
        from omx_interfaces.action import MoveToNamed as ImportedMoveToNamed
        from rosidl_runtime_py.convert import message_to_ordereddict as imported_message_to_ordereddict
        from rosidl_runtime_py.set_message import set_message_fields as imported_set_message_fields
        from rosidl_runtime_py.utilities import get_action as imported_get_action
        from rosidl_runtime_py.utilities import get_message as imported_get_message
        from rosidl_runtime_py.utilities import get_service as imported_get_service
    except Exception as exc:  # Allows /health to explain missing ROS environment.
        ROS_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
        return False

    rclpy = imported_rclpy
    get_action_names_and_types = imported_get_action_names_and_types
    ActionClient = ImportedActionClient
    SingleThreadedExecutor = ImportedSingleThreadedExecutor
    HistoryPolicy = ImportedHistoryPolicy
    QoSProfile = ImportedQoSProfile
    ReliabilityPolicy = ImportedReliabilityPolicy
    RobotState = ImportedRobotState
    GetStateValidity = ImportedGetStateValidity
    JointState = ImportedJointState
    GripperCommand = ImportedGripperCommand
    MoveToJoints = ImportedMoveToJoints
    MoveToNamed = ImportedMoveToNamed
    message_to_ordereddict = imported_message_to_ordereddict
    set_message_fields = imported_set_message_fields
    get_action = imported_get_action
    get_message = imported_get_message
    get_service = imported_get_service

    try:
        from omx_interfaces.srv import ClearPlan as ImportedClearPlan
    except ImportError:
        ImportedClearPlan = None
    try:
        from omx_interfaces.srv import ExecutePlan as ImportedExecutePlan
    except ImportError:
        ImportedExecutePlan = None
    try:
        from omx_interfaces.srv import PlanToJoints as ImportedPlanToJoints
    except ImportError:
        ImportedPlanToJoints = None

    ClearPlan = ImportedClearPlan
    ExecutePlan = ImportedExecutePlan
    PlanToJoints = ImportedPlanToJoints
    ROS_IMPORT_ERROR = None
    return True


_import_ros_runtime()


@dataclass
class RosStatus:
    rclpy_available: bool
    rclpy_initialized: bool
    node_started: bool
    joint_states_seen: bool
    last_joint_state_age_sec: float | None
    last_joint_state_stamp: float | None
    joint_state_topic: str
    error: str | None = None


class RosBridge:
    def __init__(self, ws_manager: WebSocketManager) -> None:
        self._ws_manager = ws_manager
        self._loop: asyncio.AbstractEventLoop | None = None
        self._node = None
        self._executor = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_joint_state: dict[str, Any] | None = None
        self._latest_monotonic: float | None = None
        self._started = False
        self._error: str | None = None
        self._move_to_joints_client = None
        self._move_to_named_client = None
        self._gripper_client = None
        self._plan_to_joints_client = None
        self._execute_plan_client = None
        self._clear_plan_client = None
        self._state_validity_client = None
        self._active_goal_handles: list[Any] = []
        self._image_streams: dict[str, dict[str, Any]] = {}
        self._image_last_sent: dict[str, float] = {}
        self._numeric_streams: dict[str, dict[str, Any]] = {}
        self._cached_plan_id: str | None = None
        self._cached_plan_signature: tuple[tuple[str, float], ...] | None = None
        self._joint_map = load_joint_map()
        self._joint_state_topic = (
            self._joint_map.get("joint_states_observed", {}).get("topic")
            or "/joint_states"
        )

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if self._started:
            return
        _import_ros_runtime()
        if (
            rclpy is None
            or ActionClient is None
            or SingleThreadedExecutor is None
            or RobotState is None
            or GetStateValidity is None
            or JointState is None
            or MoveToJoints is None
            or MoveToNamed is None
            or GripperCommand is None
        ):
            detail = f" ({ROS_IMPORT_ERROR})" if ROS_IMPORT_ERROR else ""
            self._error = (
                "ROS2 Python packages are not available. "
                "Source the ROS2 workspace before starting the backend."
                f"{detail}"
            )
            return

        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = rclpy.create_node("omx_web_bridge")
            self._node.create_subscription(
                JointState,
                self._joint_state_topic,
                self._on_joint_state,
                10,
            )
            self._move_to_joints_client = ActionClient(
                self._node,
                MoveToJoints,
                "/omx/move_to_joints",
            )
            self._move_to_named_client = ActionClient(
                self._node,
                MoveToNamed,
                "/omx/move_to_named",
            )
            self._gripper_client = ActionClient(
                self._node,
                GripperCommand,
                "/omx/gripper_command",
            )
            if PlanToJoints is not None:
                self._plan_to_joints_client = self._node.create_client(
                    PlanToJoints,
                    "/omx/plan_to_joints",
                )
            if ExecutePlan is not None:
                self._execute_plan_client = self._node.create_client(
                    ExecutePlan,
                    "/omx/execute_plan",
                )
            if ClearPlan is not None:
                self._clear_plan_client = self._node.create_client(
                    ClearPlan,
                    "/omx/clear_plan",
                )
            self._state_validity_client = self._node.create_client(
                GetStateValidity,
                "/check_state_validity",
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._thread = threading.Thread(
                target=self._spin,
                name="omx-web-ros-spin",
                daemon=True,
            )
            self._thread.start()
            self._started = True
            self._error = None
        except Exception as exc:
            self._error = str(exc)

    def stop(self) -> None:
        if self._executor is not None:
            try:
                self._executor.shutdown()
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass
        if rclpy is not None and rclpy.ok():
            try:
                rclpy.shutdown()
            except Exception:
                pass
        self._node = None
        self._executor = None
        self._thread = None
        self._move_to_joints_client = None
        self._move_to_named_client = None
        self._gripper_client = None
        self._plan_to_joints_client = None
        self._execute_plan_client = None
        self._clear_plan_client = None
        self._state_validity_client = None
        with self._lock:
            self._latest_joint_state = None
            self._latest_monotonic = None
            self._active_goal_handles.clear()
            self._image_streams.clear()
            self._image_last_sent.clear()
            self._numeric_streams.clear()
            self._cached_plan_id = None
            self._cached_plan_signature = None
        self._started = False

    def validate_joint_target(self, joint_names: list[str], positions: list[float]) -> dict[str, Any]:
        if not self._started:
            return {"ok": False, "message": "ROS bridge is not started.", "invalid_joints": []}

        if len(joint_names) != len(positions):
            return {
                "ok": False,
                "message": "joint_names and positions length mismatch.",
                "invalid_joints": [],
            }

        limits = self._joint_map.get("limits", {}).get("joints", {})
        for joint_name, position in zip(joint_names, positions, strict=False):
            limit = limits.get(joint_name, {})
            lower = limit.get("lower")
            upper = limit.get("upper")
            if lower is not None and position < float(lower):
                return {
                    "ok": False,
                    "message": f"{joint_name} is below lower limit.",
                    "invalid_joints": [joint_name],
                }
            if upper is not None and position > float(upper):
                return {
                    "ok": False,
                    "message": f"{joint_name} is above upper limit.",
                    "invalid_joints": [joint_name],
                }

        if not self._action_server_ready(self._move_to_joints_client, timeout_sec=1.0):
            return {
                "ok": False,
                "message": "/omx/move_to_joints action server is not ready.",
                "invalid_joints": [],
            }

        return {
            "ok": True,
            "plan_id": f"validated-target-{int(time.time() * 1000)}",
            "mode": "validation_only",
            "message": "Target is valid. Execute will call /omx/move_to_joints.",
        }

    def plan_joints(
        self,
        joint_names: list[str],
        positions: list[float],
        velocity_scale: float = 0.3,
    ) -> dict[str, Any]:
        validation = self._validate_joint_limits(joint_names, positions)
        if not validation.get("ok"):
            return validation

        state_validity = self._check_joint_state_validity(joint_names, positions)
        if not state_validity.get("ok"):
            return state_validity

        if self._plan_to_joints_client is None:
            return self.validate_joint_target(joint_names, positions)
        if not self._service_ready(self._plan_to_joints_client, timeout_sec=1.0):
            return {
                "ok": False,
                "message": "/omx/plan_to_joints service is not ready.",
                "invalid_joints": [],
            }

        request = PlanToJoints.Request()
        request.joint_names = joint_names
        request.positions = [float(position) for position in positions]
        request.velocity_scale = float(velocity_scale)
        response = self._call_service(self._plan_to_joints_client, request, timeout_sec=30.0)
        if response is None:
            self._clear_cached_plan_reference()
            return {"ok": False, "message": "/omx/plan_to_joints request timed out."}

        ok = bool(response.success)
        if ok and response.plan_id:
            self._set_cached_plan_reference(
                str(response.plan_id),
                joint_names,
                positions,
            )
        else:
            self._clear_cached_plan_reference()

        return {
            "ok": ok,
            "message": str(response.message),
            "plan_id": str(response.plan_id),
            "mode": "moveit_trajectory",
            "duration": float(response.duration),
            "point_count": int(response.point_count),
            "invalid_joints": list(response.invalid_joints),
            "trajectory": {
                "joint_names": list(response.trajectory_joint_names),
                "positions": [float(value) for value in response.trajectory_positions],
                "times": [float(value) for value in response.trajectory_times],
            },
        }

    def execute_joints(
        self,
        joint_names: list[str],
        positions: list[float],
        velocity_scale: float = 0.3,
        timeout_sec: float = 120.0,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        state_validity = self._check_joint_state_validity(joint_names, positions)
        if not state_validity.get("ok"):
            return state_validity

        if self._execute_plan_client is not None and self._service_ready(self._execute_plan_client, timeout_sec=1.0):
            resolved_plan_id = plan_id or self._cached_plan_id_for_target(joint_names, positions)
            if resolved_plan_id:
                request = ExecutePlan.Request()
                request.plan_id = resolved_plan_id
                response = self._call_service(self._execute_plan_client, request, timeout_sec=timeout_sec)
                if response is not None and bool(response.success):
                    return {
                        "ok": True,
                        "message": str(response.message),
                        "plan_id": str(response.plan_id),
                        "mode": "cached_plan",
                    }
                self._clear_cached_plan_reference()

        if not self._action_server_ready(self._move_to_joints_client, timeout_sec=1.0):
            return {
                "ok": False,
                "message": "/omx/move_to_joints action server is not ready.",
                "invalid_joints": [],
            }

        goal = MoveToJoints.Goal()
        goal.joint_names = joint_names
        goal.positions = [float(position) for position in positions]
        goal.velocity_scale = float(velocity_scale)
        return self._send_action_goal(self._move_to_joints_client, goal, timeout_sec, "move_to_joints")

    def execute_named(
        self,
        name: str,
        timeout_sec: float = 120.0,
    ) -> dict[str, Any]:
        if not self._started:
            return {"ok": False, "message": "ROS bridge is not started."}
        if not self._action_server_ready(self._move_to_named_client, timeout_sec=1.0):
            return {"ok": False, "message": "/omx/move_to_named action server is not ready."}

        goal = MoveToNamed.Goal()
        goal.name = name
        return self._send_action_goal(self._move_to_named_client, goal, timeout_sec, "move_to_named")

    def execute_gripper(
        self,
        position: float,
        max_effort: float = 0.0,
        timeout_sec: float = 60.0,
    ) -> dict[str, Any]:
        if not self._started:
            return {"ok": False, "message": "ROS bridge is not started."}

        position = max(0.0, min(1.0, float(position)))
        if not self._action_server_ready(self._gripper_client, timeout_sec=1.0):
            return {"ok": False, "message": "/omx/gripper_command action server is not ready."}

        goal = GripperCommand.Goal()
        goal.position = float(position)
        goal.max_effort = float(max_effort)
        return self._send_action_goal(self._gripper_client, goal, timeout_sec, "gripper_command")

    def clear_plan(self) -> dict[str, Any]:
        self._clear_cached_plan_reference()
        if self._clear_plan_client is None:
            return {"ok": True, "message": "No plan cache service is available."}
        if not self._service_ready(self._clear_plan_client, timeout_sec=1.0):
            return {"ok": False, "message": "/omx/clear_plan service is not ready."}
        response = self._call_service(self._clear_plan_client, ClearPlan.Request(), timeout_sec=5.0)
        if response is None:
            return {"ok": False, "message": "/omx/clear_plan request timed out."}
        return {"ok": bool(response.success), "message": str(response.message)}

    def cancel_active_goals(self) -> dict[str, Any]:
        handles: list[Any]
        with self._lock:
            handles = [handle for handle in self._active_goal_handles if handle is not None]
            self._active_goal_handles.clear()

        cancelled = 0
        for goal_handle in handles:
            future = goal_handle.cancel_goal_async()
            cancel_response = self._wait_for_future(future, 5.0)
            if cancel_response is not None:
                cancelled += 1

        return {
            "ok": True,
            "cancelled_goals": cancelled,
            "message": f"Cancel requested for {cancelled} active goal(s).",
        }

    def status(self) -> RosStatus:
        with self._lock:
            latest = self._latest_joint_state
            latest_monotonic = self._latest_monotonic

        age = None
        stamp = None
        if latest is not None and latest_monotonic is not None:
            age = max(0.0, time.monotonic() - latest_monotonic)
            stamp = latest.get("stamp")

        return RosStatus(
            rclpy_available=rclpy is not None,
            rclpy_initialized=bool(rclpy is not None and rclpy.ok()),
            node_started=self._started,
            joint_states_seen=latest is not None,
            last_joint_state_age_sec=age,
            last_joint_state_stamp=stamp,
            joint_state_topic=self._joint_state_topic,
            error=self._error,
        )

    def latest_joint_state(self) -> dict[str, Any] | None:
        with self._lock:
            if self._latest_joint_state is None:
                return None
            return dict(self._latest_joint_state)

    def ros_domain(self) -> dict[str, Any]:
        return {
            "ok": True,
            "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
        }

    def set_ros_domain(self, value: str) -> dict[str, Any]:
        domain = str(value).strip()
        if domain and (not domain.isdigit() or not 0 <= int(domain) <= 232):
            return {"ok": False, "message": "ROS_DOMAIN_ID must be empty or an integer from 0 to 232."}

        was_started = self._started
        loop = self._loop
        if was_started:
            self.stop()

        os.environ["ROS_DOMAIN_ID"] = domain

        if loop is not None:
            self.start(loop)
            if not self._started:
                return {
                    "ok": False,
                    "ros_domain_id": domain,
                    "message": self._error or "ROS bridge failed to start after ROS_DOMAIN_ID change.",
                }

        return {
            "ok": True,
            "ros_domain_id": domain,
            "message": "ROS_DOMAIN_ID applied and ROS bridge restarted." if was_started else "ROS_DOMAIN_ID applied and ROS bridge started.",
        }

    def graph_snapshot(self) -> dict[str, Any]:
        if not self._started or self._node is None:
            return {"ok": False, "message": "ROS bridge is not started.", "topics": [], "services": [], "actions": []}

        try:
            topics = self._typed_names_to_entries(self._node.get_topic_names_and_types())
            services = self._with_request_examples(
                self._filter_available_services(
                    self._typed_names_to_entries(self._node.get_service_names_and_types())
                )
            )
            raw_actions = (
                self._typed_names_to_entries(get_action_names_and_types(self._node))
                if get_action_names_and_types is not None
                else []
            )
            actions = self._with_goal_examples(self._filter_available_actions(raw_actions))
            visible_topics = self._with_configured_chart_topics(
                [entry for entry in topics if self._is_visible_topic(entry)]
            )
            return {
                "ok": True,
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
                "topics": visible_topics,
                "services": services,
                "actions": actions,
            }
        except Exception as exc:
            self._error = str(exc)
            return {"ok": False, "message": str(exc), "topics": [], "services": [], "actions": []}

    def call_dynamic_service(
        self,
        name: str,
        service_type: str,
        request_payload: dict[str, Any],
        timeout_sec: float = 10.0,
    ) -> dict[str, Any]:
        if not self._started or self._node is None:
            return {"ok": False, "message": "ROS bridge is not started."}
        if get_service is None or set_message_fields is None or message_to_ordereddict is None:
            return {"ok": False, "message": "ROS message runtime helpers are not available."}

        try:
            srv_type = get_service(service_type)
            client = self._node.create_client(srv_type, name)
            try:
                if not self._service_ready(client, timeout_sec=1.0):
                    return {"ok": False, "message": f"{name} service is not ready."}
                request = srv_type.Request()
                set_message_fields(request, request_payload)
                response = self._call_service(client, request, timeout_sec=timeout_sec)
                if response is None:
                    return {"ok": False, "message": f"{name} request timed out."}
                return {
                    "ok": True,
                    "message": f"{name} completed.",
                    "response": self._json_ready(message_to_ordereddict(response)),
                }
            finally:
                self._node.destroy_client(client)
        except Exception as exc:
            self._error = str(exc)
            return {"ok": False, "message": str(exc)}

    def send_dynamic_action_goal(
        self,
        name: str,
        action_type_name: str,
        goal_payload: dict[str, Any],
        timeout_sec: float = 120.0,
    ) -> dict[str, Any]:
        if not self._started or self._node is None:
            return {"ok": False, "message": "ROS bridge is not started."}
        if get_action is None or set_message_fields is None:
            return {"ok": False, "message": "ROS action runtime helpers are not available."}

        client = None
        try:
            action_type = get_action(action_type_name)
            client = ActionClient(self._node, action_type, name)
            if not self._action_server_ready(client, timeout_sec=1.0):
                return {"ok": False, "message": f"{name} action server is not ready."}
            goal = action_type.Goal()
            set_message_fields(goal, goal_payload)
            return self._send_action_goal(client, goal, timeout_sec, name)
        except Exception as exc:
            self._error = str(exc)
            return {"ok": False, "message": str(exc)}
        finally:
            if client is not None:
                try:
                    client.destroy()
                except Exception:
                    pass

    def add_image_listener(
        self,
        topic: str,
        topic_type: str,
        callback: Any,
    ) -> dict[str, Any]:
        if not self._started or self._node is None:
            return {"ok": False, "message": "ROS bridge is not started."}
        if get_message is None:
            return {"ok": False, "message": "ROS message runtime helpers are not available."}

        with self._lock:
            stream = self._image_streams.get(topic)
            if stream is not None:
                stream["listeners"].append(callback)
                return {"ok": True, "message": "Image listener attached."}

        try:
            msg_type = get_message(topic_type)
            subscription = self._node.create_subscription(
                msg_type,
                topic,
                lambda msg: self._on_image_message(topic, msg),
                10,
            )
            with self._lock:
                self._image_streams[topic] = {
                    "type": topic_type,
                    "subscription": subscription,
                    "listeners": [callback],
                }
            return {"ok": True, "message": "Image stream started."}
        except Exception as exc:
            self._error = str(exc)
            return {"ok": False, "message": str(exc)}

    def remove_image_listener(self, topic: str, callback: Any) -> None:
        subscription = None
        with self._lock:
            stream = self._image_streams.get(topic)
            if stream is None:
                return
            stream["listeners"] = [listener for listener in stream["listeners"] if listener is not callback]
            if stream["listeners"]:
                return
            subscription = stream.get("subscription")
            self._image_streams.pop(topic, None)
            self._image_last_sent.pop(topic, None)

        if subscription is not None and self._node is not None:
            try:
                self._node.destroy_subscription(subscription)
            except Exception:
                pass

    def add_numeric_listener(
        self,
        topic: str,
        topic_type: str,
        callback: Any,
    ) -> dict[str, Any]:
        if not self._started or self._node is None:
            return {"ok": False, "message": "ROS bridge is not started."}
        if get_message is None:
            return {"ok": False, "message": "ROS message runtime helpers are not available."}

        with self._lock:
            stream = self._numeric_streams.get(topic)
            if stream is not None:
                stream["listeners"].append(callback)
                return {"ok": True, "message": "Numeric listener attached."}

        try:
            msg_type = get_message(topic_type)
            subscription = self._node.create_subscription(
                msg_type,
                topic,
                lambda msg: self._on_numeric_message(topic, msg),
                self._numeric_qos_profile(),
            )
            with self._lock:
                self._numeric_streams[topic] = {
                    "type": topic_type,
                    "subscription": subscription,
                    "listeners": [callback],
                }
            return {"ok": True, "message": "Numeric stream started."}
        except Exception as exc:
            self._error = str(exc)
            return {"ok": False, "message": str(exc)}

    def remove_numeric_listener(self, topic: str, callback: Any) -> None:
        subscription = None
        with self._lock:
            stream = self._numeric_streams.get(topic)
            if stream is None:
                return
            stream["listeners"] = [listener for listener in stream["listeners"] if listener is not callback]
            if stream["listeners"]:
                return
            subscription = stream.get("subscription")
            self._numeric_streams.pop(topic, None)

        if subscription is not None and self._node is not None:
            try:
                self._node.destroy_subscription(subscription)
            except Exception:
                pass

    def _spin(self) -> None:
        if self._executor is None:
            return
        try:
            self._executor.spin()
        except Exception as exc:
            self._error = str(exc)

    def _on_joint_state(self, msg: Any) -> None:
        message = self._joint_state_to_message(msg)
        with self._lock:
            self._latest_joint_state = message
            self._latest_monotonic = time.monotonic()
        self._ws_manager.broadcast_threadsafe(self._loop, message)

    def _on_image_message(self, topic: str, msg: Any) -> None:
        now = time.monotonic()
        with self._lock:
            previous = self._image_last_sent.get(topic, 0.0)
            if now - previous < 0.08:
                return
            self._image_last_sent[topic] = now
            stream = self._image_streams.get(topic)
            listeners = list(stream.get("listeners", [])) if stream else []
            topic_type = str(stream.get("type", "")) if stream else ""

        if not listeners:
            return

        frame = self._image_message_to_frame(topic, topic_type, msg)
        for listener in listeners:
            try:
                listener(frame)
            except Exception:
                pass

    def _on_numeric_message(self, topic: str, msg: Any) -> None:
        with self._lock:
            stream = self._numeric_streams.get(topic)
            listeners = list(stream.get("listeners", [])) if stream else []
            topic_type = str(stream.get("type", "")) if stream else ""

        if not listeners:
            return

        sample = self._numeric_message_to_sample(topic, topic_type, msg)
        for listener in listeners:
            try:
                listener(sample)
            except Exception:
                pass

    def _action_server_ready(self, client: Any, timeout_sec: float) -> bool:
        if client is None:
            return False
        try:
            return bool(client.wait_for_server(timeout_sec=timeout_sec))
        except Exception as exc:
            self._error = str(exc)
            return False

    def _service_ready(self, client: Any, timeout_sec: float) -> bool:
        if client is None:
            return False
        try:
            return bool(client.wait_for_service(timeout_sec=timeout_sec))
        except Exception as exc:
            self._error = str(exc)
            return False

    def _call_service(self, client: Any, request: Any, timeout_sec: float) -> Any | None:
        future = client.call_async(request)
        return self._wait_for_future(future, timeout_sec)

    def _validate_joint_limits(self, joint_names: list[str], positions: list[float]) -> dict[str, Any]:
        if not self._started:
            return {"ok": False, "message": "ROS bridge is not started.", "invalid_joints": []}

        if len(joint_names) != len(positions):
            return {
                "ok": False,
                "message": "joint_names and positions length mismatch.",
                "invalid_joints": [],
            }

        limits = self._joint_map.get("limits", {}).get("joints", {})
        for joint_name, position in zip(joint_names, positions, strict=False):
            limit = limits.get(joint_name, {})
            lower = limit.get("lower")
            upper = limit.get("upper")
            if lower is not None and position < float(lower):
                return {
                    "ok": False,
                    "message": f"{joint_name} is below lower limit.",
                    "invalid_joints": [joint_name],
                }
            if upper is not None and position > float(upper):
                return {
                    "ok": False,
                    "message": f"{joint_name} is above upper limit.",
                    "invalid_joints": [joint_name],
                }

        return {"ok": True, "invalid_joints": []}

    def _check_joint_state_validity(
        self,
        joint_names: list[str],
        positions: list[float],
    ) -> dict[str, Any]:
        if self._state_validity_client is None:
            return {
                "ok": False,
                "message": "/check_state_validity client is not available.",
                "invalid_joints": [],
            }
        if not self._service_ready(self._state_validity_client, timeout_sec=1.0):
            return {
                "ok": False,
                "message": "/check_state_validity service is not ready.",
                "invalid_joints": [],
            }

        state = RobotState()
        with self._lock:
            latest = dict(self._latest_joint_state or {})

        joints: dict[str, float] = {}
        latest_joints = latest.get("joints")
        if isinstance(latest_joints, dict):
            joints.update(
                {
                    str(name): float(value)
                    for name, value in latest_joints.items()
                    if isinstance(value, (int, float))
                }
            )

        joints.update(
            {
                str(name): float(position)
                for name, position in zip(joint_names, positions, strict=False)
            }
        )
        state.joint_state.name = list(joints.keys())
        state.joint_state.position = list(joints.values())
        state.is_diff = False

        request = GetStateValidity.Request()
        request.robot_state = state
        request.group_name = "arm"
        response = self._call_service(self._state_validity_client, request, timeout_sec=5.0)
        if response is None:
            return {
                "ok": False,
                "message": "/check_state_validity request timed out.",
                "invalid_joints": [],
            }

        if response.valid:
            return {"ok": True, "invalid_joints": []}

        contact_pairs: list[str] = []
        invalid_joints: set[str] = set()
        for contact in response.contacts:
            body_1 = self._normalize_collision_body(str(contact.contact_body_1))
            body_2 = self._normalize_collision_body(str(contact.contact_body_2))
            contact_pairs.append(f"{body_1}<->{body_2}")
            invalid_joints.update(self._joints_for_collision_body(body_1))
            invalid_joints.update(self._joints_for_collision_body(body_2))

        message = "Target state violates MoveIt validity constraints"
        if contact_pairs:
            message += f" ({', '.join(contact_pairs[:4])})"
            if len(contact_pairs) > 4:
                message += f" +{len(contact_pairs) - 4} more"

        return {
            "ok": False,
            "message": message,
            "invalid_joints": sorted(invalid_joints) or list(joint_names),
            "contacts": contact_pairs,
        }

    @staticmethod
    def _normalize_collision_body(body: str) -> str:
        body = body.split("::")[-1]
        body = body.split("/")[-1]
        return body

    @staticmethod
    def _joints_for_collision_body(body: str) -> list[str]:
        body_to_joints = {
            "link0": ["joint1"],
            "link1": ["joint1"],
            "link2": ["joint2"],
            "link3": ["joint3"],
            "link4": ["joint4"],
            "link5": ["joint5"],
            "end_effector_link": ["joint5"],
            "link6": ["gripper_joint_1"],
            "link7": ["gripper_joint_2"],
        }
        return body_to_joints.get(body, [])

    def _set_cached_plan_reference(
        self,
        plan_id: str,
        joint_names: list[str],
        positions: list[float],
    ) -> None:
        with self._lock:
            self._cached_plan_id = plan_id
            self._cached_plan_signature = self._joint_target_signature(joint_names, positions)

    def _clear_cached_plan_reference(self) -> None:
        with self._lock:
            self._cached_plan_id = None
            self._cached_plan_signature = None

    def _cached_plan_id_for_target(
        self,
        joint_names: list[str],
        positions: list[float],
    ) -> str | None:
        signature = self._joint_target_signature(joint_names, positions)
        with self._lock:
            if self._cached_plan_signature != signature:
                return None
            return self._cached_plan_id

    @staticmethod
    def _joint_target_signature(
        joint_names: list[str],
        positions: list[float],
    ) -> tuple[tuple[str, float], ...]:
        return tuple(
            sorted(
                (str(name), round(float(position), 5))
                for name, position in zip(joint_names, positions, strict=False)
            )
        )

    def _send_action_goal(
        self,
        client: Any,
        goal: Any,
        timeout_sec: float,
        action_name: str,
    ) -> dict[str, Any]:
        self._broadcast_motion_event(
            "action_goal",
            action_name,
            {"status": "sending", "progress": 0.0},
        )

        send_future = client.send_goal_async(
            goal,
            feedback_callback=lambda feedback: self._on_action_feedback(action_name, feedback),
        )
        goal_handle = self._wait_for_future(send_future, timeout_sec=10.0)
        if goal_handle is None:
            self._broadcast_motion_event(
                "action_result",
                action_name,
                {"ok": False, "message": "Action goal request timed out."},
            )
            return {"ok": False, "message": "Action goal request timed out."}
        if not goal_handle.accepted:
            self._broadcast_motion_event(
                "action_result",
                action_name,
                {"ok": False, "message": "Action goal was rejected."},
            )
            return {"ok": False, "message": "Action goal was rejected."}

        with self._lock:
            self._active_goal_handles.append(goal_handle)

        result_future = goal_handle.get_result_async()
        result_response = self._wait_for_future(result_future, timeout_sec=timeout_sec)

        with self._lock:
            self._active_goal_handles = [
                handle for handle in self._active_goal_handles if handle is not goal_handle
            ]

        if result_response is None:
            self._broadcast_motion_event(
                "action_result",
                action_name,
                {"ok": False, "message": "Action result timed out."},
            )
            return {"ok": False, "message": "Action result timed out."}

        result = result_response.result
        response = {
            "ok": bool(getattr(result, "success", False)),
            "message": str(getattr(result, "message", "")),
            "status": int(result_response.status),
            "result": self._message_to_dict(result),
        }
        self._broadcast_motion_event("action_result", action_name, response)
        return response

    def _on_action_feedback(self, action_name: str, feedback_message: Any) -> None:
        feedback = getattr(feedback_message, "feedback", feedback_message)
        self._broadcast_motion_event(
            "action_feedback",
            action_name,
            self._message_to_dict(feedback),
        )

    def _broadcast_motion_event(self, event_type: str, action_name: str, payload: dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "action": action_name,
            "stamp": time.time(),
            **payload,
        }
        self._ws_manager.broadcast_threadsafe(self._loop, message)

    @staticmethod
    def _wait_for_future(future: Any, timeout_sec: float) -> Any | None:
        done = threading.Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=timeout_sec):
            return None
        try:
            return future.result()
        except Exception:
            return None

    @staticmethod
    def _message_to_dict(message: Any) -> dict[str, Any]:
        if hasattr(message, "get_fields_and_field_types"):
            return {
                field_name: getattr(message, field_name)
                for field_name in message.get_fields_and_field_types().keys()
            }
        return {
            name: value
            for name, value in vars(message).items()
            if not name.startswith("_")
        }

    def _joint_state_to_message(self, msg: Any) -> dict[str, Any]:
        joints = {
            name: float(position)
            for name, position in zip(msg.name, msg.position, strict=False)
        }
        mimic = self._joint_map.get("gripper_mimic_joint") or {}
        mimic_name = mimic.get("name")
        mimic_source = mimic.get("source")
        multiplier = float(mimic.get("multiplier", 1.0))
        if mimic_name and mimic_source in joints and mimic_name not in joints:
            joints[mimic_name] = joints[mimic_source] * multiplier

        stamp = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
        return {
            "type": "joint_state",
            "stamp": stamp,
            "frame_id": msg.header.frame_id,
            "joints": joints,
            "source": self._joint_state_topic,
        }

    @staticmethod
    def _image_message_to_frame(topic: str, topic_type: str, msg: Any) -> dict[str, Any]:
        stamp = None
        header = getattr(msg, "header", None)
        if header is not None:
            stamp = float(header.stamp.sec) + float(header.stamp.nanosec) * 1e-9

        if topic_type == "sensor_msgs/msg/CompressedImage" or hasattr(msg, "format"):
            fmt = str(getattr(msg, "format", "jpeg")).lower()
            mime = "jpeg" if "jpeg" in fmt or "jpg" in fmt else "png" if "png" in fmt else "jpeg"
            encoded = base64.b64encode(bytes(getattr(msg, "data", b""))).decode("ascii")
            return {
                "type": "image_frame",
                "topic": topic,
                "topic_type": topic_type,
                "stamp": stamp,
                "format": fmt,
                "data_url": f"data:image/{mime};base64,{encoded}",
            }

        data = bytes(getattr(msg, "data", b""))
        return {
            "type": "image_frame",
            "topic": topic,
            "topic_type": topic_type,
            "stamp": stamp,
            "width": int(getattr(msg, "width", 0)),
            "height": int(getattr(msg, "height", 0)),
            "encoding": str(getattr(msg, "encoding", "")),
            "step": int(getattr(msg, "step", 0)),
            "data": base64.b64encode(data).decode("ascii"),
        }

    @staticmethod
    def _numeric_message_to_sample(topic: str, topic_type: str, msg: Any) -> dict[str, Any]:
        stamp = None
        header = getattr(msg, "header", None)
        if header is not None:
            stamp = float(header.stamp.sec) + float(header.stamp.nanosec) * 1e-9

        field = "data"
        value = getattr(msg, field, None)
        if not isinstance(value, (int, float)):
            for name, candidate in vars(msg).items():
                if name.startswith("_") or not isinstance(candidate, (int, float)):
                    continue
                field = name
                value = candidate
                break

        if not isinstance(value, (int, float)):
            return {
                "type": "numeric_error",
                "topic": topic,
                "topic_type": topic_type,
                "message": f"{topic} does not expose a numeric field.",
            }

        return {
            "type": "numeric_sample",
            "topic": topic,
            "topic_type": topic_type,
            "stamp": stamp if stamp is not None else time.time(),
            "field": field,
            "value": float(value),
        }

    @staticmethod
    def _typed_names_to_entries(items: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
        entries = []
        for name, types in items:
            entries.append({"name": str(name), "types": [str(type_name) for type_name in types]})
        return sorted(entries, key=lambda entry: entry["name"])

    @staticmethod
    def _with_configured_chart_topics(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_name = {str(entry.get("name", "")): entry for entry in entries}
        for name, types in CHART_TOPIC_TYPES.items():
            by_name.setdefault(name, {"name": name, "types": types})
        return sorted(by_name.values(), key=lambda entry: str(entry.get("name", "")))

    @staticmethod
    def _numeric_qos_profile() -> Any:
        if QoSProfile is None or ReliabilityPolicy is None or HistoryPolicy is None:
            return 10
        return QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

    @classmethod
    def _is_visible_topic(cls, entry: dict[str, Any]) -> bool:
        return cls._is_image_topic(entry) or cls._is_chart_topic(entry)

    @staticmethod
    def _is_image_topic(entry: dict[str, Any]) -> bool:
        types = entry.get("types") or []
        return any(
            type_name in {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
            or type_name.endswith("/Image")
            or type_name.endswith("/CompressedImage")
            for type_name in types
        )

    @staticmethod
    def _is_chart_topic(entry: dict[str, Any]) -> bool:
        return str(entry.get("name", "")) in CHART_TOPIC_NAMES

    def _filter_available_services(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = []
        for entry in entries:
            name = str(entry.get("name", ""))
            if name.startswith("/omx_web_bridge/") or "/_action/" in name:
                continue
            try:
                if self._node is not None and self._node.count_services(name) <= 0:
                    continue
            except Exception:
                pass
            filtered.append(entry)
        return filtered

    def _filter_available_actions(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return entries

    def _with_request_examples(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **entry,
                "request_example": self._service_request_example(
                    str(entry.get("name", "")),
                    str((entry.get("types") or [""])[0]),
                ),
            }
            for entry in entries
        ]

    def _with_goal_examples(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **entry,
                "goal_example": self._action_goal_example(
                    str(entry.get("name", "")),
                    str((entry.get("types") or [""])[0]),
                ),
            }
            for entry in entries
        ]

    def _service_request_example(self, name: str, service_type_name: str) -> dict[str, Any]:
        example = self._known_example(SERVICE_REQUEST_EXAMPLES, name, service_type_name)
        if example is not None:
            return example
        if get_service is None or message_to_ordereddict is None:
            return {}

        try:
            service_type = get_service(service_type_name)
            return self._json_ready(message_to_ordereddict(service_type.Request()))
        except Exception:
            return {}

    def _action_goal_example(self, name: str, action_type_name: str) -> dict[str, Any]:
        example = self._known_example(ACTION_GOAL_EXAMPLES, name, action_type_name)
        if example is not None:
            return example
        if get_action is None or message_to_ordereddict is None:
            return {}

        try:
            action_type = get_action(action_type_name)
            return self._json_ready(message_to_ordereddict(action_type.Goal()))
        except Exception:
            return {}

    @staticmethod
    def _known_example(
        examples: dict[str, dict[str, Any]],
        name: str,
        type_name: str,
    ) -> dict[str, Any] | None:
        example = examples.get(name) or examples.get(type_name)
        if example is None:
            return None
        return json.loads(json.dumps(example))

    @staticmethod
    def _json_ready(value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except TypeError:
            if isinstance(value, dict):
                return {key: RosBridge._json_ready(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [RosBridge._json_ready(item) for item in value]
            return str(value)
