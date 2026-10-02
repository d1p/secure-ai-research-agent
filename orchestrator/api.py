"""Orchestrator API.

OpenAI-compatible chat endpoint + approval management.  The coding workflow
(project spec section 17) never modifies the workspace before approval.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from typing import Any

from agent import (
    call_browser,
    run_agent,
    set_approval_status,
)
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from tools.aider_runner import run_aider

ORCHESTRATOR_TOKEN = os.environ.get("ORCHESTRATOR_TOKEN", "")
WEB_LOADER_API_KEY = os.environ.get("WEB_LOADER_API_KEY", "")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-flash")

MAX_PAGE_CONTENT_CHARS = 60000

app = FastAPI(title="orchestrator")


def _setup_otel(app: FastAPI) -> None:
    """Enable OpenTelemetry tracing (FastAPI + httpx) when configured."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return

    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "orchestrator")})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


_setup_otel(app)


def _check_auth(authorization: str | None) -> None:
    if not ORCHESTRATOR_TOKEN:
        raise HTTPException(503, "orchestrator token not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != ORCHESTRATOR_TOKEN:
        raise HTTPException(401, "invalid token")


class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list[dict[str, Any]] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|edit)$")
    feedback: str | None = None


class WebLoaderRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)


def _extract_mcp_text(payload: dict[str, Any]) -> str:
    """Extract text chunks from a browser `tools/call` response envelope."""
    content = (payload.get("result") or {}).get("content", [])
    chunks = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(chunks).strip()


async def _fetch_page_text(agent_id: str, url: str) -> str:
    """Navigate the browser to `url` and return its visible text.

    Reuses the safeguard gateway (SSRF/tier/rate-limit/audit) as the security
    boundary; the orchestrator never talks to the browser directly.  The browser
    is driven by the Stagehand service (navigate + read page text).
    """
    nav = await call_browser(agent_id, "stagehand_navigate", {"url": url})
    if isinstance(nav, dict) and nav.get("error"):
        return f"[browser error {nav['error']}] {nav.get('detail', '')}"
    if isinstance(nav, dict) and nav.get("needs_human"):
        return f"[needs_human] {nav.get('message', 'challenge detected')}"
    if isinstance(nav, dict) and nav.get("needs_approval"):
        return "[needs_approval] navigation requires approval"

    snap = await call_browser(agent_id, "stagehand_read", {})
    if isinstance(snap, dict) and snap.get("error"):
        return f"[browser error {snap['error']}] {snap.get('detail', '')}"

    text = _extract_mcp_text(snap) if isinstance(snap, dict) else ""
    if not text:
        return "[no text content]"
    if len(text) > MAX_PAGE_CONTENT_CHARS:
        text = text[:MAX_PAGE_CONTENT_CHARS] + "\n\n[content truncated]"
    return text


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    agent_id = "openwebui"
    result = await run_agent(agent_id, req.messages)
    content = result.get("result", "")
    if result.get("needs_approval"):
        # Coding request: return the plan + approval id for the UI to render.
        content = json.dumps(
            {
                "needs_approval": True,
                "approval_id": result.get("approval_id"),
                "plan": result.get("plan"),
                "allowed_files": result.get("allowed_files"),
                "message": "Review the plan. Approve, edit, or reject.",
            }
        )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }


@app.post("/web-loader")
async def web_loader(req: WebLoaderRequest, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    """Open WebUI 'external web loader' contract.

    Accepts ``{"urls": [...]}`` and returns ``[{"page_content": ..., "metadata": {...}}]``
    so Open WebUI's `fetch_url` tool can read pages through the sandboxed browser.
    """
    if not WEB_LOADER_API_KEY:
        raise HTTPException(503, "web loader key not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != WEB_LOADER_API_KEY:
        raise HTTPException(401, "invalid token")

    results: list[dict[str, Any]] = []
    for url in req.urls:
        text = await _fetch_page_text("openwebui", url)
        results.append({"page_content": text, "metadata": {"source": url}})
    return results


@app.get("/approvals/{approval_id}")
async def get_approval(approval_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    from agent import _pg

    conn = await _pg()
    try:
        row = await conn.fetchrow("SELECT * FROM orchestrator.approvals WHERE id=$1", approval_id)
    finally:
        await conn.close()
    if not row:
        raise HTTPException(404, "approval not found")
    return dict(row)


@app.post("/approvals/{approval_id}/decision")
async def decide(approval_id: int, req: DecisionRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    from agent import _pg

    conn = await _pg()
    try:
        row = await conn.fetchrow("SELECT * FROM orchestrator.approvals WHERE id=$1", approval_id)
    finally:
        await conn.close()
    if not row:
        raise HTTPException(404, "approval not found")

    if req.decision == "reject":
        await set_approval_status(approval_id, "rejected")
        return {"status": "rejected"}

    if req.decision == "edit":
        # Re-plan with feedback; keeps the approval pending.
        return {"status": "pending", "message": "edit triggers re-planning (re-run planning with feedback)"}

    # approve -> execute coding in an ephemeral runner on a throwaway worktree
    allowed_files = json.loads(row["allowed_files"] or "[]")
    request_text = row["request"]
    outcome = _execute_coding(request_text, allowed_files)
    await set_approval_status(approval_id, "approved" if outcome["ok"] else "rejected", outcome)
    return outcome


def _prepare_worktree(repo_name: str, branch: str) -> str:
    """Create a throwaway git worktree under /workspace (no merge/push)."""
    os.makedirs(WORKSPACE, exist_ok=True)
    repo_dir = os.path.join(WORKSPACE, repo_name)
    worktree = os.path.join(WORKSPACE, "worktrees", branch)
    if os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "-C", repo_dir, "worktree", "add", "-b", branch, worktree], check=True, capture_output=True)
    else:
        os.makedirs(worktree, exist_ok=True)
    return worktree


def _execute_coding(request_text: str, allowed_files: list[str]) -> dict[str, Any]:
    branch = f"agent-{uuid.uuid4().hex[:8]}"
    repo_name = _repo_name()
    worktree = _prepare_worktree(repo_name, branch)
    model = "bedrock-claude-sonnet"

    result = run_aider(request_text, model, worktree)

    if result["exit_code"] != 0:
        return {"ok": False, "reason": f"runner exited {result['exit_code']}", "branch": branch}

    changed = _changed_files(worktree)
    unapproved = [f for f in changed if f not in allowed_files]
    if unapproved:
        subprocess.run(["git", "-C", worktree, "worktree", "remove", "--force", worktree], capture_output=True, check=False)
        return {"ok": False, "reason": "out-of-plan files changed", "unapproved_files": unapproved, "branch": branch}

    diff = subprocess.run(["git", "-C", worktree, "diff", "--name-only"], capture_output=True, text=True, check=False).stdout
    return {"ok": True, "branch": branch, "changed_files": changed, "diff_files": diff.splitlines()}


def _repo_name() -> str:
    repos = os.environ.get("WORKSPACE_REPOS", "")
    if repos and "=" in repos:
        return repos.split("=")[0].split(",")[0]
    return "workspace"


def _changed_files(worktree: str) -> list[str]:
    out = subprocess.run(["git", "-C", worktree, "diff", "--name-only"], capture_output=True, text=True, check=False).stdout
    return [f for f in out.splitlines() if f.strip()]
