"""Shared Docker API helper for spawning ephemeral coding runners.

Talks to the docker-socket-proxy (minimal permissions: create/start/stop/remove)
so the orchestrator controls the runner WITHOUT the full docker socket.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

DOCKER_PROXY_URL = os.environ.get("DOCKER_PROXY_URL", "http://docker-socket-proxy:2375")
AGENTS_NETWORK = os.environ.get("AGENTS_NETWORK", "ai-stack_agents")


def _client() -> httpx.Client:
    return httpx.Client(base_url=DOCKER_PROXY_URL, timeout=httpx.Timeout(120.0, connect=10.0))


def runner_container_spec(
    image: str,
    command: list[str],
    env: dict[str, str],
    binds: list[str],
    name: str,
) -> dict[str, Any]:
    """Build a hardened container spec (project spec section 18)."""
    return {
        "Image": image,
        "Cmd": command,
        "Env": [f"{k}={v}" for k, v in env.items()],
        "WorkingDir": "/workspace",
        "User": "1001:1001",
        "HostConfig": {
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "PidsLimit": 128,
            "Memory": 1610612736,  # 1.5 GB
            "NetworkMode": AGENTS_NETWORK,
            "Binds": binds,
            "ReadonlyRootfs": False,
        },
        "Labels": {"ai-stack": "agent-runner", "name": name},
    }


def create_container(spec: dict[str, Any]) -> str:
    with _client() as client:
        resp = client.post("/containers/create", json=spec)
        resp.raise_for_status()
        return resp.json()["Id"]


def start_container(container_id: str) -> None:
    with _client() as client:
        resp = client.post(f"/containers/{container_id}/start")
        resp.raise_for_status()


def wait_container(container_id: str, timeout: int = 900) -> int:
    """Wait for the container to exit and return its exit code."""
    deadline = time.monotonic() + timeout
    with _client() as client:
        while time.monotonic() < deadline:
            resp = client.get(f"/containers/{container_id}/json")
            resp.raise_for_status()
            state = resp.json().get("State", {})
            if not state.get("Running"):
                return int(state.get("ExitCode", 0))
            time.sleep(2)
    return -1


def container_logs(container_id: str) -> str:
    with _client() as client:
        resp = client.get(
            f"/containers/{container_id}/logs",
            params={"stdout": True, "stderr": True, "tail": 400},
        )
        resp.raise_for_status()
        return resp.text


def remove_container(container_id: str) -> None:
    with _client() as client:
        try:
            client.delete(f"/containers/{container_id}", params={"force": True})
        except httpx.HTTPError:
            pass
