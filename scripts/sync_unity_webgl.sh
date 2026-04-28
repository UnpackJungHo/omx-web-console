#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-/home/kjhz/omx_web_ws/unity-webgl/build}"
TARGET_DIR="/home/kjhz/omx_web_ws/frontend/omx-web-ui/public/unity-webgl"

if [ ! -d "$SOURCE_DIR/Build" ] || [ ! -d "$SOURCE_DIR/TemplateData" ]; then
  echo "Unity WebGL build not found at $SOURCE_DIR" >&2
  echo "Expected: $SOURCE_DIR/Build and $SOURCE_DIR/TemplateData" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
find "$TARGET_DIR" -mindepth 1 ! -name ".gitkeep" -exec rm -rf {} +
cp -a "$SOURCE_DIR/Build" "$TARGET_DIR/"
cp -a "$SOURCE_DIR/TemplateData" "$TARGET_DIR/"
if [ -f "$SOURCE_DIR/index.html" ]; then
  cp -a "$SOURCE_DIR/index.html" "$TARGET_DIR/"
fi
cat > "$TARGET_DIR/manifest.json" <<'JSON'
{
  "available": true,
  "loaderUrl": "/unity-webgl/Build/build.loader.js",
  "dataUrl": "/unity-webgl/Build/build.data",
  "frameworkUrl": "/unity-webgl/Build/build.framework.js",
  "codeUrl": "/unity-webgl/Build/build.wasm"
}
JSON

echo "Synced Unity WebGL build to $TARGET_DIR"
