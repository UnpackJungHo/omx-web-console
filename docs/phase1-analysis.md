# Phase 1 Analysis - OMX Web Control + Unity WebGL

확인일: 2026-04-25

## 목표

기존 `/home/kjhz/omx_ws`의 ROS2, MoveIt, motion server, Unity 구성을 웹 제어 MVP의 기준 인터페이스로 정리한다. Phase 2 백엔드는 기존 하드웨어 제어 계층을 직접 대체하지 않고, `/joint_states`와 기존 `/omx/*` action server를 웹 API와 WebSocket으로 노출한다.

## 워크스페이스 구분

| 경로 | 역할 |
|---|---|
| `/home/kjhz/omx_ws` | 기존 ROS2 bringup, MoveIt, motion server, 하드웨어 제어 |
| `/home/kjhz/UnityProjects/ros2_unity_manipulator` | 기존 Unity `omx_f` scene와 이후 WebGL build 원본 |
| `/home/kjhz/omx_web_ws` | 신규 웹 백엔드, 프론트엔드, Unity WebGL build, 문서 |

Phase 1에서 생성한 신규 산출물:

- `/home/kjhz/omx_web_ws/docs/phase1-analysis.md`
- `/home/kjhz/omx_web_ws/docs/joint-map.json`
- `/home/kjhz/omx_web_ws/docs/api-draft.md`

## ROS2 Bringup

확인 파일:

- `/home/kjhz/omx_ws/src/omx_bringup/launch/omx_control.launch.py`

주요 역할:

- `robot_state_publisher`
- `ros2_control_node`
- `joint_state_broadcaster`
- `arm_controller`
- `gripper_traj_controller`
- `joint_trajectory_executor`를 통한 초기 home 이동
- 선택적 RViz 실행

확인된 launch argument:

| 이름 | 기본값 | 웹 MVP 기준 |
|---|---:|---|
| `start_rviz` | `true` | `false` |
| `prefix` | `''` | `''` |
| `use_mock_hardware` | `false` | 개발 검증은 `true`, 실제 하드웨어는 `false` |
| `port_name` | `/dev/ttyACM0` | 기본값 유지, 필요 시 UI/설정에서 override |

Phase 1 실제 확인 명령:

```bash
cd /home/kjhz/omx_ws
source install/setup.bash
ros2 launch omx_bringup omx_control.launch.py use_mock_hardware:=true start_rviz:=false
ros2 topic echo /joint_states --once
```

확인된 `/joint_states`:

```yaml
name:
- gripper_joint_1
- joint1
- joint2
- joint3
- joint4
- joint5
position:
- 0.0
- 0.0
- -1.57
- 1.57
- 1.57
- 0.0
velocity:
- 0.0
- 0.0
- 0.0
- 0.0
- 0.0
- 0.0
```

결론:

- 실제 `/joint_states`에는 `joint1`~`joint5`와 `gripper_joint_1`이 나온다.
- `gripper_joint_2`는 `/joint_states`에 직접 나오지 않는다.
- 웹/Unity에서는 `gripper_joint_2 = gripper_joint_1 * -1`로 파생한다.

## MoveIt

확인 파일:

- `/home/kjhz/omx_ws/src/omx_bringup/launch/omx_moveit.launch.py`
- `/home/kjhz/omx_ws/src/omx_bringup/config/omx_f/omx_f.srdf`
- `/home/kjhz/omx_ws/src/omx_bringup/config/omx_f/kinematics.yaml`
- `/home/kjhz/omx_ws/src/omx_bringup/config/omx_f/moveit_controllers.yaml`

확인된 planning group:

| group | 구성 |
|---|---|
| `arm` | `link0` -> `end_effector_link` chain |
| `gripper` | `gripper_joint_1`, `gripper_joint_2` |

확인된 named state:

| group | state | joints |
|---|---|---|
| `arm` | `init` | `joint1..joint5 = 0` |
| `arm` | `home` | `joint1=0`, `joint2=-1.57`, `joint3=1.57`, `joint4=1.57`, `joint5=0` |
| `gripper` | `close` | `gripper_joint_1=0` |
| `gripper` | `open` | `gripper_joint_1=1` |

MoveIt controller 연결:

| controller | type | joints |
|---|---|---|
| `arm_controller` | `FollowJointTrajectory` | `joint1`~`joint5` |
| `gripper_traj_controller` | `FollowJointTrajectory` | `gripper_joint_1` |

IK 설정:

- group: `arm`
- solver: `kdl_kinematics_plugin/KDLKinematicsPlugin`
- `position_only_ik: true`
- timeout: `0.3`
- attempts: `3`

결론:

- 웹 MVP는 joint-space 제어를 우선한다.
- Cartesian pose target은 5-DOF 특성상 후속 Phase에서 별도 UX와 validation을 둔다.

## Motion Server

확인 파일:

- `/home/kjhz/omx_ws/src/omx_motion_server/src/motion_server.cpp`
- `/home/kjhz/omx_ws/src/omx_motion_server/launch/motion_server.launch.py`
- `/home/kjhz/omx_ws/src/omx_interfaces/action/*.action`

실제 확인 명령:

```bash
cd /home/kjhz/omx_ws
source install/setup.bash
ros2 launch omx_bringup omx_control.launch.py use_mock_hardware:=true start_rviz:=false
ros2 launch omx_bringup omx_moveit.launch.py start_rviz:=false
ros2 launch omx_motion_server motion_server.launch.py
ros2 action list | grep /omx
```

확인된 action server:

```text
/omx/gripper_command
/omx/move_to_joints
/omx/move_to_named
/omx/move_to_pose
```

확인된 정책:

- arm action은 `arm_busy_`로 동시 실행을 막는다.
- gripper action은 `gripper_busy_`로 동시 실행을 막는다.
- 기본 velocity scaling은 `0.3`이다.
- 기본 acceleration scaling은 `0.1`이다.
- named pose alias:
  - `home` -> `home`
  - `init` -> `init`
  - `ready` -> `home`
  - `stow` -> `init`
  - `pre_grasp` -> `home`
- gripper command 범위는 `0.0 = close`, `1.0 = open`이다.

Phase 2 백엔드는 MoveIt을 직접 감싸기보다 기존 action client로 붙는다. 단, `MoveToJoints.action`에는 plan-only와 execute 분리가 없으므로 MVP의 `Plan`은 target validation과 현재 상태 비교 수준으로 두고, `Execute`에서 `/omx/move_to_joints`를 호출한다.

## Unity

확인 경로:

- `/home/kjhz/UnityProjects/ros2_unity_manipulator`

확인 파일:

- `Assets/Scenes/OMX_AI.unity`
- `Assets/URDF/open_manipulator_description/urdf/omx_f/omx_f.urdf`

Scene 확인:

- root object: `omx_f`
- `ArticulationBody` 컴포넌트 존재
- `jointName` 값으로 `joint1`~`joint5`, `gripper_joint_1`, `gripper_joint_2` 확인
- `useUrdfData: 1` 확인

Unity URDF joint axis:

| joint | axis | note |
|---|---|---|
| `joint1` | `0 0 1` | revolute |
| `joint2` | `0 1 0` | revolute |
| `joint3` | `0 1 0` | revolute |
| `joint4` | `0 1 0` | revolute |
| `joint5` | `1 0 0` | revolute |
| `gripper_joint_1` | `0 0 1` | revolute |
| `gripper_joint_2` | `0 0 1` | mimic `gripper_joint_1`, multiplier `-1` |

결론:

- Phase 4에서는 새 모델을 import하지 않는다.
- `OMX_AI.unity`의 기존 `omx_f` 아래 ArticulationBody를 `jointName` 또는 object name 기준으로 수집한다.
- ROS 값은 radian이며, Unity `ArticulationDrive.target` 적용 시 degree 변환을 고려한다.

## Phase 2 진입 기준

Phase 2에서 바로 사용할 기준:

- 상태 입력: `/joint_states`
- arm 실행 action: `/omx/move_to_joints`
- named 실행 action: `/omx/move_to_named`
- gripper 실행 action: `/omx/gripper_command`
- pose 실행 action은 후순위 API로만 열어두고 UI 기본 동선에서는 숨긴다.
- WebSocket 상태 메시지는 `joint_state`, `target_joints`, `motion_status`, `error`를 기본 타입으로 둔다.
