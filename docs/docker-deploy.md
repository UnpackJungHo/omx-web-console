# Docker 배포 가이드

목표는 두 가지 모드로 나눈다.

- 기기가 없는 사용자: Docker 안에서 ROS2 mock hardware와 MoveIt을 실행하고, 웹 UI와 Unity WebGL로 관절 움직임을 테스트한다.
- 실제 기기가 있는 사용자: 같은 웹 UI를 쓰되 백엔드 컨테이너에 USB 시리얼 장치를 넘겨 박스 잡기 동작까지 실행한다.

## 현실적인 무료 배포 구조

무료로 가장 안정적인 구조는 다음이다.

```text
브라우저
  -> frontend 컨테이너: Nginx + React/Vite + Unity WebGL
  -> backend 컨테이너: FastAPI + ROS2 bridge + ROS launch manager
  -> mock hardware 또는 USB로 연결된 실제 OpenMANIPULATOR-X
```

정적 UI만 GitHub Pages나 Cloudflare Pages에 올릴 수도 있다. 다만 HTTPS로 열린 페이지는 로컬의 `http://robot-ip:8000` 백엔드를 직접 호출할 수 없어 mixed content 문제가 난다. 외부 공유까지 무료로 하려면 로봇 PC에서 Cloudflare Tunnel 같은 HTTPS 터널을 frontend 컨테이너의 `http://localhost:8080`으로 연결하는 방식이 현실적이다.

실제 USB 장치는 클라우드 무료 서버에 붙일 수 없다. 실기기 제어는 반드시 로봇이 연결된 PC, Raspberry Pi, Jetson, 노트북 같은 로컬 장비에서 Docker를 실행해야 한다.

## 사전 조건

- Docker와 Docker Compose가 설치되어 있어야 한다.
- 현재 백엔드는 `/home/kjhz/omx_ws/install/setup.bash`를 source해서 `omx_bringup`, `omx_motion_server`, `omx_interfaces`를 사용한다.
- 다른 PC에서 실행하려면 해당 PC에도 ROS workspace를 빌드해 두고 `OMX_ROS_WS_HOST`로 경로를 넘긴다.
- Unity WebGL 화면까지 포함하려면 `frontend/omx-web-ui/public/unity-webgl`에 WebGL 빌드가 sync되어 있어야 한다.

## 기기 없이 mock 모드로 실행

```bash
cd /home/kjhz/omx_web_ws
docker compose build
docker compose up
```

브라우저에서 연다.

```text
http://localhost:8080
```

웹 UI에서 `가상 하드웨어`를 누르면 컨테이너 안에서 다음 계열의 launch가 실행된다.

```text
ros2 launch omx_bringup omx_control.launch.py start_rviz:=false use_mock_hardware:=true
ros2 launch omx_bringup omx_moveit.launch.py start_rviz:=false
ros2 launch omx_motion_server motion_server.launch.py
```

## 실제 기기로 실행

먼저 장치 포트를 확인한다.

```bash
ls /dev/ttyACM* /dev/ttyUSB*
```

예를 들어 `/dev/ttyACM0`이면 다음처럼 실행한다.

```bash
cd /home/kjhz/omx_web_ws
OMX_HARDWARE_PORT=/dev/ttyACM0 docker compose -f docker-compose.yml -f docker-compose.real.yml up
```

웹 UI에서 `실기기 하드웨어`를 누르면 `use_mock_hardware:=false`와 `port_name:=/dev/ttyACM0`로 launch된다.

## 다른 PC에서 테스트하게 배포

가장 단순한 무료 방식은 이미지를 빌드해서 Docker Hub나 GitHub Container Registry에 올리고, 테스트할 PC에서 같은 compose 파일로 받는 것이다.

현재 compose는 ROS workspace를 volume으로 마운트한다.

```bash
OMX_ROS_WS_HOST=/path/to/omx_ws docker compose up
```

완전히 독립적인 이미지를 만들려면 `omx_ws/src`를 이미지 안에 복사하고 `rosdep install`, `colcon build`까지 Dockerfile에 넣는 별도 full image가 필요하다. 이 방식은 이미지가 커지고 빌드 시간이 길지만, 테스트 PC에 ROS workspace를 미리 빌드하지 않아도 된다.

## 공개 링크로 공유

로봇 PC에서 다음 순서로 운영한다.

1. `docker compose up`으로 `http://localhost:8080`을 띄운다.
2. 무료 HTTPS 터널을 `localhost:8080`에 연결한다.
3. 생성된 HTTPS 주소를 공유한다.

실제 로봇까지 외부에서 움직일 수 있게 열 때는 권한 제어가 필요하다. 지금 백엔드는 인증이 없으므로 공개 인터넷에 그대로 노출하면 안 된다. 최소한 터널 접근 제어, VPN, 또는 임시 비밀번호 프록시를 앞에 둬야 한다.
