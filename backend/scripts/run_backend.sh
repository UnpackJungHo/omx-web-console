#!/usr/bin/env bash
set -euo pipefail

cd /home/kjhz/omx_ws
set +u
source install/setup.bash
set -u

cd /home/kjhz/omx_web_ws/backend
if [ ! -d .venv ]; then
  python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate
python3 -m pip install -r requirements.txt
exec uvicorn omx_web_bridge.app:app --host "${OMX_WEB_HOST:-127.0.0.1}" --port "${OMX_WEB_PORT:-8000}"
