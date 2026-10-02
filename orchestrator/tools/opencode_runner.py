"""OpenCode coding runner (project spec section 18).

OpenCode runs inside an ephemeral, hardened container.  `--model litellm/...`
routes through the LiteLLM proxy; no automatic approval flags are ever used.
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


def run_opencode(task: str, model: str, worktree_path: str) -> dict[str, Any]:
    """Run opencode on a throwaway worktree and return exit code + logs."""
    name = f"runner-opencode-{uuid.uuid4().hex[:8]}"
    command = [
        "opencode", "run",
        "--model", f"litellm/{model}",
        task,
    ]
    env = {
        "OPENAI_BASE_URL": LITELLM_URL,
        "OPENAI_API_KEY": LITELLM_MASTER_KEY,
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
        return {"tool": "opencode", "exit_code": exit_code, "container_id": container_id}
    finally:
        remove_container(container_id)
