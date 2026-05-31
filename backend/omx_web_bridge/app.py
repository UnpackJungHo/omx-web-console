from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import robot_info
from .launch_manager import LaunchManager
from .llm_client import call_ollama_chat, ollama_model
from .ros_bridge import RosBridge
from .ws_manager import WebSocketManager

ws_manager = WebSocketManager()
ros_bridge = RosBridge(ws_manager)
launch_manager = LaunchManager(ws_manager)


def cors_origins() -> list[str]:
    raw = os.getenv("OMX_CORS_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


class LaunchRequest(BaseModel):
    mode: str
    namespace: str | None = None


class JointTargetRequest(BaseModel):
    joint_names: list[str]
    positions: list[float]
    velocity_scale: float = 0.3
    plan_id: str | None = None
    namespace: str | None = None


class GripperRequest(BaseModel):
    position: float
    max_effort: float = 0.0
    namespace: str | None = None


class NamedMotionRequest(BaseModel):
    name: str
    namespace: str | None = None


class RosDomainRequest(BaseModel):
    ros_domain_id: str


class RosServiceCallRequest(BaseModel):
    name: str
    type: str
    request: dict = {}
    timeout_sec: float = 10.0
    namespace: str | None = None


class RosActionGoalRequest(BaseModel):
    name: str
    type: str
    goal: dict = {}
    timeout_sec: float = 120.0
    namespace: str | None = None


class LlmChatMessage(BaseModel):
    role: str
    content: str


class LlmChatRequest(BaseModel):
    messages: list[LlmChatMessage]
    model: str | None = None
    timeout_sec: float = 120.0


class ExecuteCommandRequest(BaseModel):
    command: str
    dry_run: bool = False
    timeout_sec: float = 180.0
    namespace: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    launch_manager.set_event_loop(loop)
    ros_bridge.start(loop)
    try:
        yield
    finally:
        launch_manager.stop()
        launch_manager.stop_motion_server()
        launch_manager.set_event_loop(None)
        ros_bridge.stop()


app = FastAPI(
    title="OMX Web Bridge",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    ros_status = asdict(ros_bridge.status())
    return {
        "ok": ros_status["error"] is None,
        "service": "omx_web_bridge",
        "ros": ros_status,
        "websocket_clients": await ws_manager.client_count(),
    }


@app.get("/robot/info")
async def get_robot_info() -> dict:
    return robot_info()


@app.get("/robot/launch/status")
async def get_launch_status() -> dict:
    return {
        "ok": True,
        "status": asdict(launch_manager.status()),
        "hardware_port": launch_manager.detect_hardware_port(),
    }


@app.get("/ros/domain")
async def get_ros_domain() -> dict:
    return ros_bridge.ros_domain()


@app.post("/ros/domain")
async def set_ros_domain(request: RosDomainRequest) -> dict:
    return await asyncio.to_thread(ros_bridge.set_ros_domain, request.ros_domain_id)


@app.get("/ros/graph")
async def get_ros_graph() -> dict:
    return await asyncio.to_thread(ros_bridge.graph_snapshot)


@app.post("/ros/service-call")
async def call_ros_service(request: RosServiceCallRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.call_dynamic_service,
        request.name,
        request.type,
        request.request,
        request.timeout_sec,
    )


@app.post("/ros/action-goal")
async def send_ros_action_goal(request: RosActionGoalRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.send_dynamic_action_goal,
        request.name,
        request.type,
        request.goal,
        request.timeout_sec,
    )


@app.post("/llm/chat")
async def llm_chat(request: LlmChatRequest) -> dict:
    messages = [
        {"role": message.role, "content": message.content}
        for message in request.messages
        if message.role in {"system", "user", "assistant"} and message.content.strip()
    ]
    if not messages:
        return {"ok": False, "model": request.model or ollama_model(), "message": "No chat messages provided"}

    return await asyncio.to_thread(
        call_ollama_chat,
        messages[-20:],
        request.model,
        request.timeout_sec,
    )


@app.post("/llm/execute-command")
async def llm_execute_command(request: ExecuteCommandRequest) -> dict:
    command = request.command.strip()
    if not command:
        return {"ok": False, "message": "command is empty."}
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.execute_command,
        command,
        request.dry_run,
        request.timeout_sec,
    )


@app.post("/robot/launch")
async def start_robot_launch(request: LaunchRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return launch_manager.start(request.mode, request.namespace)


@app.post("/robot/launch/stop")
async def stop_robot_launch() -> dict:
    return launch_manager.stop_response()


@app.post("/perception/snapshot")
async def trigger_perception_snapshot() -> dict:
    return await asyncio.to_thread(launch_manager.send_perception_snapshot_key)


@app.post("/motion/plan-joints")
async def plan_joints(request: JointTargetRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.plan_joints,
        request.joint_names,
        request.positions,
        request.velocity_scale,
    )


@app.post("/motion/execute-joints")
async def execute_joints(request: JointTargetRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.execute_joints,
        request.joint_names,
        request.positions,
        velocity_scale=request.velocity_scale,
        plan_id=request.plan_id,
    )


@app.post("/motion/named")
async def execute_named(request: NamedMotionRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(ros_bridge.execute_named, request.name)


@app.post("/motion/gripper")
async def execute_gripper(request: GripperRequest) -> dict:
    ros_bridge.use_namespace(request.namespace)
    return await asyncio.to_thread(
        ros_bridge.execute_gripper,
        request.position,
        request.max_effort,
    )


@app.post("/motion/stop")
async def stop_motion() -> dict:
    return await asyncio.to_thread(ros_bridge.cancel_active_goals)


@app.post("/motion/clear-plan")
async def clear_plan() -> dict:
    return await asyncio.to_thread(ros_bridge.clear_plan)


@app.websocket("/ws/state")
async def websocket_state(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    latest = ros_bridge.latest_joint_state()
    if latest is not None:
        await websocket.send_json(latest)

    try:
        while True:
            # Phase 2 is server-push only. Receiving keeps the connection alive
            # and lets the client close cleanly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/image")
async def websocket_image(websocket: WebSocket, topic: str, type: str) -> None:
    await websocket.accept()
    loop = asyncio.get_running_loop()

    def send_frame(frame: dict) -> None:
        asyncio.run_coroutine_threadsafe(websocket.send_json(frame), loop)

    attached = ros_bridge.add_image_listener(topic, type, send_frame)
    if not attached.get("ok"):
        await websocket.send_json({"type": "image_error", "message": attached.get("message", "Image stream failed.")})
        await websocket.close()
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ros_bridge.remove_image_listener(topic, send_frame)
    except Exception:
        ros_bridge.remove_image_listener(topic, send_frame)


@app.websocket("/ws/numeric")
async def websocket_numeric(websocket: WebSocket, topic: str, type: str) -> None:
    await websocket.accept()
    loop = asyncio.get_running_loop()

    def send_sample(sample: dict) -> None:
        asyncio.run_coroutine_threadsafe(websocket.send_json(sample), loop)

    attached = ros_bridge.add_numeric_listener(topic, type, send_sample)
    if not attached.get("ok"):
        await websocket.send_json({"type": "numeric_error", "message": attached.get("message", "Numeric stream failed.")})
        await websocket.close()
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ros_bridge.remove_numeric_listener(topic, send_sample)
    except Exception:
        ros_bridge.remove_numeric_listener(topic, send_sample)


@app.get("/")
async def root() -> dict:
    return {
        "service": "omx_web_bridge",
        "endpoints": [
            "/health",
            "/robot/info",
            "/robot/launch/status",
            "/robot/launch",
            "/robot/launch/stop",
            "/ros/domain",
            "/ros/graph",
            "/ros/service-call",
            "/ros/action-goal",
            "/llm/chat",
            "/llm/execute-command",
            "/motion/plan-joints",
            "/motion/execute-joints",
            "/motion/named",
            "/motion/gripper",
            "/motion/stop",
            "/motion/clear-plan",
            "/perception/snapshot",
            "/ws/state",
            "/ws/image",
            "/ws/numeric",
        ],
    }
