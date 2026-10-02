"""LangGraph orchestrator.

Three modes (project spec section 16):
  1. research / general chat  -> browser Tier 0-1, no approval required
  2. browser side effects     -> Tier 1/2 via the safeguard gateway
  3. coding                   -> plan -> approval -> ephemeral runner

LangGraph state is persisted to Postgres (orchestrator.checkpoints) and the
coding workflow is persisted to orchestrator.approvals.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.graph import END, StateGraph

LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://safeguard-gateway:8000")
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DOCKER_PROXY_URL = os.environ.get("DOCKER_PROXY_URL", "http://docker-socket-proxy:2375")
RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "ai-stack-agent-runner:local")
AGENTS_NETWORK = os.environ.get("AGENTS_NETWORK", "ai-stack_agents")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    messages: Annotated[list[dict[str, Any]], "append"]
    agent_id: str
    thread_id: str
    mode: str
    plan: dict[str, Any] | None
    approval_id: str | None
    allowed_files: list[str]
    result: str
    needs_approval: bool


# ---------------------------------------------------------------------------
# LiteLLM / browser helpers
# ---------------------------------------------------------------------------
async def call_litellm(messages: list[dict[str, Any]], model: str = "deepseek-chat") -> str:
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{LITELLM_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
            json={"model": model, "messages": messages},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_browser(agent_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{GATEWAY_URL}/execute",
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "X-Agent-Id": agent_id,
            },
            json={"tool": tool, "args": args},
        )
        if resp.status_code >= 400:
            return {"error": resp.status_code, "detail": resp.text}
        return resp.json()


# ---------------------------------------------------------------------------
# Postgres persistence (simple JSONB checkpoint + approvals)
# ---------------------------------------------------------------------------
async def _pg() -> Any:
    import asyncpg

    return await asyncpg.connect(DATABASE_URL)


async def save_checkpoint(thread_id: str, state: dict[str, Any]) -> str:
    checkpoint_id = str(uuid.uuid4())
    conn = await _pg()
    try:
        await conn.execute(
            "INSERT INTO orchestrator.checkpoints (thread_id, checkpoint_id, state) VALUES ($1,$2,$3)",
            thread_id, checkpoint_id, json.dumps(state, default=str),
        )
    finally:
        await conn.close()
    return checkpoint_id


async def create_approval(
    thread_id: str, agent_id: str, request: str, plan: dict[str, Any], allowed_files: list[str]
) -> int:
    conn = await _pg()
    try:
        row = await conn.fetchrow(
            "INSERT INTO orchestrator.approvals "
            "(thread_id, agent_id, status, request, plan, allowed_files) "
            "VALUES ($1,$2,'pending',$3,$4,$5) RETURNING id",
            thread_id, agent_id, request, json.dumps(plan), json.dumps(allowed_files),
        )
        return int(row["id"])
    finally:
        await conn.close()


async def set_approval_status(approval_id: int, status: str, result_diff: dict[str, Any] | None = None) -> None:
    conn = await _pg()
    try:
        await conn.execute(
            "UPDATE orchestrator.approvals SET status=$1, result_diff=$2, updated_at=now() WHERE id=$3",
            status, json.dumps(result_diff) if result_diff else None, approval_id,
        )
    finally:
        await conn.close()


async def persist_research(agent_id: str, query: str, source_urls: list[str], summary: str) -> None:
    conn = await _pg()
    try:
        await conn.execute(
            "INSERT INTO orchestrator.research_notes (agent_id, query, source_urls, summary) "
            "VALUES ($1,$2,$3,$4)",
            agent_id, query, json.dumps(source_urls), summary,
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Mode classification
# ---------------------------------------------------------------------------
async def classify(messages: list[dict[str, Any]]) -> str:
    last = next((m["content"] for m in reversed(messages) if m.get("content")), "")
    lowered = last.lower()
    coding_hints = ("fix", "implement", "write code", "refactor", "add a function", "modify ", "change the code")
    research_hints = ("research", "look up", "browse", "find ", "compare ", "search the web", "what is the price")
    if any(h in lowered for h in coding_hints):
        return "coding"
    if any(h in lowered for h in research_hints):
        return "research"
    return "chat"


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------
async def node_classify(state: AgentState) -> AgentState:
    state["mode"] = await classify(state.get("messages", []))
    return state


async def node_chat(state: AgentState) -> AgentState:
    answer = await call_litellm(state.get("messages", []))
    state["result"] = answer
    return state


async def node_research(state: AgentState) -> AgentState:
    """Research mode: browse (Tier 0-1) without approval and persist notes."""
    messages = state.get("messages", [])
    query = next((m["content"] for m in reversed(messages) if m.get("content")), "")
    # Simple research loop: navigate to a safe search URL, snapshot, summarize.
    await call_browser(state["agent_id"], "browser_navigate", {"url": _research_url(query)})
    snap = await call_browser(state["agent_id"], "browser_snapshot", {})
    summary = await call_litellm(
        [{"role": "user", "content": f"Summarize research for query '{query}' from page: {snap}"}]
    )
    await persist_research(state["agent_id"], query, [str(_research_url(query))], summary)
    state["result"] = summary
    return state


def _research_url(query: str) -> str:
    # Default to a safe general search; the real browser flow may refine this.
    from urllib.parse import quote_plus

    return f"https://duckduckgo.com/html/?q={quote_plus(query)}"


async def node_coding_plan(state: AgentState) -> AgentState:
    """Generate a plan and create a pending approval; NO files change yet."""
    request = next((m["content"] for m in reversed(state.get("messages", [])) if m.get("content")), "")
    prompt = (
        "You are a coding planner. For the request below, output JSON with keys: "
        "'summary' (string), 'steps' (list of strings), 'files' (list of exact file paths "
        "that may change). Do not include any other text.\n\nRequest:\n" + request
    )
    raw = await call_litellm([{"role": "user", "content": prompt}])
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        plan = {"summary": raw, "steps": [], "files": []}
    allowed_files = list(plan.get("files", []))
    approval_id = await create_approval(state["thread_id"], state["agent_id"], request, plan, allowed_files)
    state["plan"] = plan
    state["allowed_files"] = allowed_files
    state["approval_id"] = str(approval_id)
    state["needs_approval"] = True
    state["result"] = json.dumps({"plan": plan, "approval_id": approval_id, "allowed_files": allowed_files})
    await save_checkpoint(state["thread_id"], state)
    return state


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def _route(state: AgentState) -> str:
    return {"chat": "chat", "research": "research", "coding": "coding_plan"}[state.get("mode", "chat")]


def build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("classify", node_classify)
    g.add_node("chat", node_chat)
    g.add_node("research", node_research)
    g.add_node("coding_plan", node_coding_plan)
    g.set_entry_point("classify")
    g.add_conditional_edges("classify", _route, {"chat": "chat", "research": "research", "coding_plan": "coding_plan"})
    g.add_edge("chat", END)
    g.add_edge("research", END)
    g.add_edge("coding_plan", END)
    return g.compile()


_graph = build_graph()


async def run_agent(agent_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    thread_id = str(uuid.uuid4())
    initial: AgentState = {
        "messages": messages,
        "agent_id": agent_id,
        "thread_id": thread_id,
        "mode": "chat",
        "plan": None,
        "approval_id": None,
        "allowed_files": [],
        "result": "",
        "needs_approval": False,
    }
    result = await _graph.ainvoke(initial)
    return result
