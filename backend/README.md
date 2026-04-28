# OMX Web Bridge Backend

Phase 2 backend for OMX Web Control.

## Run

Use the ROS2 workspace environment first so `rclpy` and generated ROS message packages are visible.

```bash
cd /home/kjhz/omx_ws
source install/setup.bash

cd /home/kjhz/omx_web_ws/backend
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
uvicorn omx_web_bridge.app:app --host 127.0.0.1 --port 8000
```

Expected endpoints:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/robot/info`
- `WS  ws://127.0.0.1:8000/ws/state`

To receive live joint states, start the ROS side from the web UI:

- `가상 하드웨어`: runs `ros2 launch omx_bringup omx_control.launch.py start_rviz:=false use_mock_hardware:=true`
- `실기기 하드웨어`: checks `/dev/ttyACM*` or `/dev/ttyUSB*`, then runs the same launch with `use_mock_hardware:=false`
- Click the active hardware button again to stop the running launch.
- The hardware buttons now start the control launch, MoveIt launch with RViz, and `omx_motion_server` together so Plan/Execute/Gripper APIs can use the existing `/omx/*` actions.

The backend still needs to be running because browser JavaScript cannot execute local ROS2 processes directly.
