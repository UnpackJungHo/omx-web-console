# API Draft - OMX Web Bridge

이 문서는 Phase 2 백엔드 scaffold의 기준 API 초안이다. 백엔드는 브라우저와 Unity WebGL에 상태와 명령 인터페이스를 제공하되, 실제 로봇 제어는 기존 ROS2, MoveIt, `omx_motion_server` 계층에 위임한다.

## 원칙

- 브라우저와 Unity WebGL은 하드웨어를 직접 제어하지 않는다.
- slider 변경은 `target_joints`만 바꾸며 실제 로봇은 움직이지 않는다.
- `Plan`은 MVP에서 target validation과 현재 상태 비교 결과를 반환한다.
- `Execute`만 기존 `/omx/*` action을 호출한다.
- `Stop`은 모든 화면 상태에서 접근 가능해야 한다.
- 실제 하드웨어 실행 전에는 `use_mock_hardware:=true`로 먼저 검증한다.

## REST API

### `GET /health`

백엔드 프로세스와 ROS graph 연결 상태를 반환한다.

Response:

```json
{
  "ok": true,
  "service": "omx_web_bridge",
  "ros": {
    "rclpy_initialized": true,
    "joint_states_seen": true,
    "last_joint_state_age_sec": 0.12
  }
}
```

### `GET /robot/info`

웹 UI 렌더링에 필요한 정적 정보를 반환한다. 기본 source는 `docs/joint-map.json`이다.

Response:

```json
{
  "robot": "omx_f",
  "arm_group": "arm",
  "gripper_group": "gripper",
  "arm_joints": ["joint1", "joint2", "joint3", "joint4", "joint5"],
  "gripper_command_joint": "gripper_joint_1",
  "named_states": ["init", "home", "ready", "stow", "pre_grasp", "open", "close"],
  "actions": {
    "move_to_named": "/omx/move_to_named",
    "move_to_joints": "/omx/move_to_joints",
    "gripper_command": "/omx/gripper_command"
  }
}
```

### `POST /robot/plan`

MVP에서는 MoveIt plan cache를 만들지 않는다. target joint 이름, 범위, 누락 값을 검증하고 execute 가능 여부를 반환한다.

Request:

```json
{
  "target_joints": {
    "joint1": 0.0,
    "joint2": -1.57,
    "joint3": 1.57,
    "joint4": 1.57,
    "joint5": 0.0,
    "gripper_joint_1": 0.0
  },
  "velocity_scale": 0.3
}
```

Response:

```json
{
  "ok": true,
  "plan_id": "validation-only",
  "mode": "validation_only",
  "message": "Target is valid for MVP execution.",
  "normalized_target_joints": {
    "joint1": 0.0,
    "joint2": -1.57,
    "joint3": 1.57,
    "joint4": 1.57,
    "joint5": 0.0,
    "gripper_joint_1": 0.0
  }
}
```

### `POST /robot/execute-joints`

기존 `/omx/move_to_joints` action을 호출한다. gripper는 별도 `execute-gripper`에서 처리한다.

Request:

```json
{
  "joint_names": ["joint1", "joint2", "joint3", "joint4", "joint5"],
  "positions": [0.0, -1.57, 1.57, 1.57, 0.0],
  "velocity_scale": 0.3
}
```

ROS action mapping:

```text
/omx/move_to_joints
  joint_names: string[]
  positions: float64[]
  velocity_scale: float32
```

### `POST /robot/named-state`

기존 `/omx/move_to_named` action을 호출한다.

Request:

```json
{
  "name": "home"
}
```

지원 이름:

```text
home, init, ready, stow, pre_grasp
```

### `POST /robot/gripper`

기존 `/omx/gripper_command` action을 호출한다.

Request:

```json
{
  "position": 1.0,
  "max_effort": 0.0
}
```

의미:

- `0.0`: close
- `1.0`: open

### `POST /robot/stop`

MVP에서는 백엔드가 실행 중인 action goal을 cancel한다. ros2_control controller emergency stop은 후속 Phase에서 별도 구현한다.

Response:

```json
{
  "ok": true,
  "message": "Cancel requested for active goals."
}
```

## WebSocket

Endpoint:

```text
WS /ws/state
```

서버는 ROS 상태와 실행 상태를 broadcast한다. 클라이언트는 Phase 2에서는 read-only로 두고, target 변경은 프론트엔드 로컬 상태에서 처리한다.

### `joint_state`

`/joint_states`에서 받은 현재값이다. `gripper_joint_2`는 Unity preview를 위해 파생해서 포함할 수 있다.

```json
{
  "type": "joint_state",
  "stamp": 1777046390.2567816,
  "frame_id": "base_link",
  "joints": {
    "gripper_joint_1": 0.0,
    "gripper_joint_2": -0.0,
    "joint1": 0.0,
    "joint2": -1.57,
    "joint3": 1.57,
    "joint4": 1.57,
    "joint5": 0.0
  },
  "source": "/joint_states"
}
```

### `motion_status`

ROS action feedback과 result를 UI에 전달한다.

```json
{
  "type": "motion_status",
  "action": "/omx/move_to_joints",
  "state": "executing",
  "progress": 0.5,
  "message": "executing"
}
```

허용 state:

```text
idle, planning, planned, executing, done, canceling, canceled, failed
```

### `target_joints`

Phase 3 이후 프론트엔드가 Unity preview와 동기화할 때 사용하는 메시지 형태다. Phase 2 서버는 이 메시지를 저장하거나 broadcast하지 않아도 된다.

```json
{
  "type": "target_joints",
  "joints": {
    "joint1": 0.0,
    "joint2": -1.2,
    "joint3": 1.3,
    "joint4": 1.2,
    "joint5": 0.0,
    "gripper_joint_1": 1.0,
    "gripper_joint_2": -1.0
  }
}
```

### `error`

```json
{
  "type": "error",
  "scope": "ros_action",
  "message": "Action server /omx/move_to_joints is not available."
}
```

## Unity WebGL Message

React에서 Unity로 전달할 기준 메시지는 WebSocket `joint_state`와 같은 joint dictionary를 사용한다.

```javascript
unityInstance.SendMessage(
  "OmxWebJointBridge",
  "SetJointStateJson",
  JSON.stringify({
    type: "joint_state",
    joints: {
      joint1: 0,
      joint2: -1.57,
      joint3: 1.57,
      joint4: 1.57,
      joint5: 0,
      gripper_joint_1: 0,
      gripper_joint_2: 0
    }
  })
);
```

Unity 적용 규칙:

- ROS 값은 radian이다.
- `ArticulationDrive.target`은 degree 변환이 필요할 수 있다.
- `gripper_joint_2`가 누락되면 `gripper_joint_1 * -1`로 생성한다.
- 축 방향이 실제 표시와 반대면 `joint-map.json`의 `unity.sign_corrections`를 수정한다.

## Phase 2 구현 순서

1. FastAPI 앱과 `/health` 작성
2. `rclpy` node 생성
3. `/joint_states` subscribe
4. `/ws/state` broadcast
5. `GET /robot/info`를 `joint-map.json` 기반으로 작성
6. action client skeleton 추가
7. mock hardware 기준으로 상태 수신 검증
