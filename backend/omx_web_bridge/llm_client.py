from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def ollama_base_url() -> str:
    return os.getenv("OMX_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_model() -> str:
    return os.getenv("OMX_OLLAMA_MODEL", "qwen3-4b-omx")


def call_ollama_chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    selected_model = model or ollama_model()
    payload = {
        "model": selected_model,
        "stream": False,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_base_url()}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "model": selected_model,
            "message": detail or error.reason or f"HTTP {error.code}",
        }
    except urllib.error.URLError as error:
        return {
            "ok": False,
            "model": selected_model,
            "message": f"Ollama unavailable: {error.reason}",
        }
    except TimeoutError:
        return {
            "ok": False,
            "model": selected_model,
            "message": "Ollama request timed out",
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "model": selected_model, "message": raw or "Invalid Ollama response"}

    content = parsed.get("message", {}).get("content")
    if not isinstance(content, str):
        content = parsed.get("response")
    if not isinstance(content, str):
        return {"ok": False, "model": selected_model, "message": "Ollama response had no message content"}

    return {
        "ok": True,
        "model": parsed.get("model", selected_model),
        "message": content,
    }
