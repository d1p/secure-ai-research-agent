"""Aider coding runner (project spec section 18).

Aider runs inside an ephemeral, hardened container; it must never create
commits (--no-auto-commits) and never has push credentials.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from . import (
    create_container,
    remove_container,
    runner_container_spec,
    start_container,
    wait_container,
)

LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "ai-stack-agent-runner:local")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")


def run_aider(task: str, model: str, worktree_path: str) -> dict[str, Any]:
    """Run aider on a throwaway worktree and return exit code + logs."""
    name = f"runner-aider-{uuid.uuid4().hex[:8]}"
    command = [
        "aider",
        "--model",
        f"litellm_proxy/{model}",
        "--no-auto-commits",
        "--message",
        task,
    ]
    env = {
        "LITELLM_PROXY_API_BASE": LITELLM_URL,
        "LITELLM_PROXY_API_KEY": LITELLM_MASTER_KEY,
        "PYTHONUNBUFFERED": "1",
    }
    spec = runner_container_spec(
        image=RUNNER_IMAGE,
        command=command,
        env=env,
        binds=[f"{WORKSPACE}:/workspace"],
        name=name,
    )
    container_id = create_container(spec)
    try:
        start_container(container_id)
        exit_code = wait_container(container_id)
        return {"tool": "aider", "exit_code": exit_code, "container_id": container_id}
    finally:
        remove_container(container_id)
