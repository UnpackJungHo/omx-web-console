# OMX Web Console

Web console for operating and inspecting an OMX ROS 2 manipulator stack.

## Structure

- `backend/`: FastAPI bridge for ROS 2 state, launch control, motion APIs, and dynamic ROS service/action calls.
- `frontend/omx-web-ui/`: React/Vite dashboard UI.
- `docs/`: API notes, deployment notes, and robot joint metadata.
- `docker/`: Dockerfiles and Nginx config for containerized deployment.
- `scripts/`: Utility scripts, including Unity WebGL sync helpers.

## Local Development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_backend.sh
```

Frontend:

```bash
cd frontend/omx-web-ui
npm install
npm run dev
```

## Notes

- ROS packages are expected under `OMX_ROS_WS` or `/home/kjhz/omx_ws` by default.
- Generated artifacts such as `node_modules/`, `.venv/`, `dist/`, Playwright logs, and Unity WebGL build output are intentionally ignored.
- If Unity preview assets are needed, build/export them separately and sync them into `frontend/omx-web-ui/public/unity-webgl/`.
