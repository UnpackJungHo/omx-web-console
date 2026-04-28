from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def default_joint_map_path() -> Path:
    env_path = os.getenv("OMX_JOINT_MAP")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parents[2] / "docs" / "joint-map.json"


@lru_cache(maxsize=1)
def load_joint_map(path: str | None = None) -> dict[str, Any]:
    joint_map_path = Path(path).expanduser() if path else default_joint_map_path()
    with joint_map_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["_source_path"] = str(joint_map_path)
    return data


def robot_info() -> dict[str, Any]:
    joint_map = load_joint_map()
    named_states = joint_map.get("named_states", {})
    actions = joint_map.get("motion_actions", {})
    return {
        "robot": joint_map.get("robot"),
        "arm_group": joint_map.get("arm_group"),
        "gripper_group": joint_map.get("gripper_group"),
        "arm_joints": joint_map.get("arm_joints", []),
        "gripper_command_joint": joint_map.get("gripper_command_joint"),
        "gripper_mimic_joint": joint_map.get("gripper_mimic_joint"),
        "named_states": list(named_states.keys()),
        "limits": joint_map.get("limits", {}),
        "actions": {
            "move_to_named": actions.get("move_to_named"),
            "move_to_joints": actions.get("move_to_joints"),
            "gripper_command": actions.get("gripper_command"),
            "move_to_pose": actions.get("move_to_pose"),
        },
        "unity": joint_map.get("unity", {}),
        "joint_map_source": joint_map.get("_source_path"),
    }
