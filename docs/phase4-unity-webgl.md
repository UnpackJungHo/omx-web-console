# Phase 4 - Unity WebGL Integration

확인일: 2026-04-25

## 구현된 것

Unity runtime bridge:

```text
/home/kjhz/UnityProjects/ros2_unity_manipulator/Assets/Scripts/OMX/OmxWebJointBridge.cs
```

역할:

- scene의 `omx_f` root 아래 `ArticulationBody`를 수집한다.
- URDF Importer 컴포넌트의 `jointName` 필드를 reflection으로 읽는다.
- `joint1`~`joint5`, `gripper_joint_1`, `gripper_joint_2` target을 radian 입력에서 degree drive target으로 변환한다.
- `gripper_joint_2`는 `gripper_joint_1 * -1` 성격으로 처리한다.
- React/JavaScript에서 다음 호출을 받을 수 있다.

```javascript
unityInstance.SendMessage(
  'OmxWebJointBridge',
  'SetJointStateJson',
  JSON.stringify({ type: 'joint_state', joints })
)
```

Unity editor/build helper:

```text
/home/kjhz/UnityProjects/ros2_unity_manipulator/Assets/Editor/OmxWebGLBuild.cs
```

역할:

- `Assets/Scenes/OMX_AI.unity`에 `OmxWebJointBridge` GameObject를 보장한다.
- WebGL build output을 `/home/kjhz/omx_web_ws/unity-webgl/build`로 생성하도록 시도한다.

React integration:

```text
/home/kjhz/omx_web_ws/frontend/omx-web-ui/src/OmxConsole.tsx
/home/kjhz/omx_web_ws/frontend/omx-web-ui/src/OmxConsole.css
```

역할:

- 기존 SVG placeholder를 Unity WebGL canvas loader로 교체했다.
- `public/unity-webgl/manifest.json`을 보고 Unity build 존재 여부를 판단한다.
- Unity instance가 준비되면 `/ws/state`에서 받은 `joint_state`를 `OmxWebJointBridge.SetJointStateJson`으로 전달한다.
- build가 없으면 콘솔 에러 없이 `Unity WebGL build not installed` 상태를 표시한다.

Sync helper:

```text
/home/kjhz/omx_web_ws/scripts/sync_unity_webgl.sh
```

역할:

- `/home/kjhz/omx_web_ws/unity-webgl/build` 산출물을 Vite public folder로 복사한다.
- `public/unity-webgl/manifest.json`을 `available: true`로 바꾼다.

## 확인 완료

Scene bridge 부착:

```bash
"/home/kjhz/Unity/Hub/Editor/2022.3.62f3/Editor/Unity" \
  -batchmode \
  -projectPath "/home/kjhz/UnityProjects/ros2_unity_manipulator" \
  -executeMethod OmxWebGLBuild.EnsureBridgeInScene \
  -quit \
  -logFile /tmp/omx_phase4_unity_setup.log
```

결과:

```text
Ensured OmxWebJointBridge in Assets/Scenes/OMX_AI.unity
```

Frontend verification:

```bash
cd /home/kjhz/omx_web_ws/frontend/omx-web-ui
npm run lint
npm run build
```

결과:

- lint 통과
- production build 통과
- Playwright 확인: browser console error/warning 없음

## 현재 blocker

WebGL build command:

```bash
"/home/kjhz/Unity/Hub/Editor/2022.3.62f3/Editor/Unity" \
  -batchmode \
  -projectPath "/home/kjhz/UnityProjects/ros2_unity_manipulator" \
  -executeMethod OmxWebGLBuild.BuildWebGL \
  -quit \
  -logFile /tmp/omx_phase4_webgl_build.log
```

실패 원인:

```text
Switching to WebGL:WebGLSupport is disabled
Error building player because build target was unsupported
Exception: WebGL build failed: Unknown
```

현재 Unity 설치에 있는 playback engine:

```text
/home/kjhz/Unity/Hub/Editor/2022.3.62f3/Editor/Data/PlaybackEngines/LinuxStandaloneSupport
```

`WebGLSupport` 디렉터리가 없다.

## 다음 조치

Unity Hub에서 Unity `2022.3.62f3`에 WebGL Build Support 모듈을 설치한다.

그 후:

```bash
"/home/kjhz/Unity/Hub/Editor/2022.3.62f3/Editor/Unity" \
  -batchmode \
  -projectPath "/home/kjhz/UnityProjects/ros2_unity_manipulator" \
  -executeMethod OmxWebGLBuild.BuildWebGL \
  -quit \
  -logFile /tmp/omx_phase4_webgl_build.log

/home/kjhz/omx_web_ws/scripts/sync_unity_webgl.sh
```

Frontend에서 `http://127.0.0.1:5173/`를 열면 오른쪽 `Unity WebGL View`가 실제 Unity canvas로 바뀐다.
