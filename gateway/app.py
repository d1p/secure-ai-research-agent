"""Browser safeguard gateway.

The security boundary between the orchestrator and the browser.  Playwright MCP
is NOT a security boundary; this service is.

Responsibilities (project spec section 13):
  * shared-token auth (orchestrator -> gateway)
  * agent_id from the authenticated caller only (header), never the body
  * URL / DNS / redirect validation + SSRF prevention
  * tool-tier enforcement (tiers 0..3)
  * rate limiting + page-load limiting
  * audit logging to Postgres (browser_audit)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import httpx
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from security import (
    TIER_APPROVAL,
    TIER_FORBIDDEN,
    TIER_VALIDATED,
    UrlVerdict,
    classify_tool,
    is_sensitive_element,
    validate_url,
)

GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "")
MCP_ENDPOINT = os.environ.get("MCP_ENDPOINT", "http://browser:8931")
BROWSERHAND_ENDPOINT = os.environ.get("BROWSERHAND_ENDPOINT", "http://browserhand:29981")
BROWSERHAND_API_KEY = os.environ.get("BROWSERHAND_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
POLICY_FILE = os.environ.get("POLICY_FILE", "/app/policy.yaml")

app = FastAPI(title="safeguard-gateway")


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

    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "safeguard-gateway")})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


_setup_otel(app)


# ---------------------------------------------------------------------------
# Minimal MCP-over-SSE client for Playwright MCP
# ---------------------------------------------------------------------------
class MCPClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
        self._post_url: str | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._ready = asyncio.Event()
        self._reader: asyncio.Task[Any] | None = None

    async def connect(self) -> None:
        self._reader = asyncio.create_task(self._read_stream())
        await asyncio.wait_for(self._ready.wait(), timeout=15.0)
        await self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "safeguard-gateway", "version": "1.0.0"},
            },
        )
        await self.notify("notifications/initialized", {})

    async def reconnect(self) -> None:
        """Reset and re-establish the MCP session (e.g. after browser restart)."""
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        self._post_url = None
        self._ready = asyncio.Event()
        await self._client.aclose()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
        await self.connect()

    async def _read_stream(self) -> None:
        async with self._client.stream("GET", f"{self.base_url}/sse") as resp:
            resp.raise_for_status()
            event: str | None = None
            data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if line == "":
                    if event:
                        self._handle_event(event, "\n".join(data_lines))
                    event, data_lines = None, []
                    continue
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:"):].strip())

    def _handle_event(self, event: str, data: str) -> None:
        if event == "endpoint":
            self._post_url = data if data.startswith("http") else self.base_url + data
            self._ready.set()
        elif event == "message":
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                return
            fut = self._pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def _post(self, payload: dict[str, Any]) -> None:
        assert self._post_url, "MCP endpoint not yet known"
        await self._client.post(self._post_url, json=payload)

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return await asyncio.wait_for(fut, timeout=170.0)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params})

    async def list_tools(self) -> list[dict[str, Any]]:
        resp = await self.call("tools/list", {})
        return resp.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self.call("tools/call", {"name": name, "arguments": args})


mcp = MCPClient(MCP_ENDPOINT)
_connected = False


# ---------------------------------------------------------------------------
# BrowserHand client (stateless HTTP -> relay -> user's real Chrome)
# ---------------------------------------------------------------------------
class BrowserHandClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def command(self, action: str, params: dict[str, Any], user_id: str = "") -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {"action": action, "params": params or {}}
        if user_id:
            body["userId"] = user_id
        resp = await self._client.post(f"{self.base_url}/command", json=body, headers=headers)
        return resp.status_code, resp.json()


browserhand = BrowserHandClient(BROWSERHAND_ENDPOINT, BROWSERHAND_API_KEY)


_BROWSERHAND_IMAGE_ACTIONS = {"screenshot", "fullscreenshot", "pdf"}


def _browserhand_result(tool: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a relay response to the same MCP `tools/call` envelope the
    orchestrator already parses: {"result": {"content": [{"type": "text", ...}]}}."""
    action = tool.removeprefix("browserhand_")
    data = raw.get("data", {})
    if action == "gettext" and isinstance(data, dict):
        text = data.get("extractedText", "")
    else:
        if action in _BROWSERHAND_IMAGE_ACTIONS and isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in ("screenshot", "data", "pdf")}
        text = json.dumps(data, default=str) if data not in (None, "") else ""
    return {"result": {"content": [{"type": "text", "text": text}]}}


async def _run_browserhand(agent_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    action = tool.removeprefix("browserhand_")
    try:
        status, raw = await browserhand.command(action, args, user_id=agent_id)
    except httpx.HTTPError as exc:  # noqa: BLE001 - connection-level failure
        raise HTTPException(status_code=502, detail="browserhand relay unreachable") from exc
    if status >= 400:
        detail = (raw.get("data") or {}).get("error", f"relay returned {status}")
        raise HTTPException(status_code=502, detail=detail)
    if not raw.get("success"):
        detail = (raw.get("data") or {}).get("error", "browserhand action failed")
        raise HTTPException(status_code=502, detail=detail)
    return _browserhand_result(tool, raw)



# ---------------------------------------------------------------------------
# Policy / state
# ---------------------------------------------------------------------------
def _load_policy() -> dict[str, Any]:
    with open(POLICY_FILE, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


POLICY = _load_policy()
_rate_state: dict[str, list[float]] = {}          # agent_id -> request timestamps
_page_loads: dict[str, dict[str, float]] = {}     # agent_id -> {domain: last_ts}
_snapshots: dict[str, str] = {}                   # agent_id -> latest snapshot text


def _now() -> float:
    return time.monotonic()


def _enforce_rate_limit(agent_id: str) -> None:
    limit = int(POLICY["rate_limit"]["requests_per_minute"])
    cutoff = _now() - 60.0
    stamps = [t for t in _rate_state.setdefault(agent_id, []) if t > cutoff]
    if len(stamps) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    stamps.append(_now())
    _rate_state[agent_id] = stamps


def _enforce_page_load_limit(agent_id: str, url: str) -> None:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or url
    interval = float(POLICY["rate_limit"]["page_load_interval_seconds"])
    last = _page_loads.setdefault(agent_id, {}).get(host, 0.0)
    if _now() - last < interval:
        raise HTTPException(status_code=429, detail="page-load rate limit per domain")
    _page_loads[agent_id][host] = _now()


# ---------------------------------------------------------------------------
# Audit (Postgres)
# ---------------------------------------------------------------------------
_pool: Any = None


async def _init_db() -> None:
    global _pool
    try:
        import asyncpg

        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    except Exception:  # noqa: BLE001 - DB optional for standalone runs
        _pool = None


async def _audit(agent_id: str, url: str, tool: str, status: str, tier: str = "", detail: str = "") -> None:
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orchestrator.browser_audit (agent_id, url, tool, tier, status, detail) "
                "VALUES ($1,$2,$3,$4,$5,$6)",
                agent_id, url, tool, tier, status, detail,
            )
    except Exception:  # noqa: BLE001,S110 - best-effort audit, never block browsing
        pass


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
async def require_auth(authorization: str | None = Header(default=None)) -> str:
    if not GATEWAY_TOKEN:
        raise HTTPException(status_code=503, detail="gateway token not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    return token


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ExecuteRequest(BaseModel):
    tool: str = Field(...)
    args: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    await _init_db()
    global _connected
    try:
        await mcp.connect()
        _connected = True
    except Exception:  # noqa: BLE001 - gateway starts even if MCP not ready
        _connected = False


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "mcp_connected": _connected}


@app.get("/tools")
async def list_tools(_: str = Depends(require_auth)) -> dict[str, Any]:
    tools = await mcp.list_tools()
    return {
        "tools": [
            {"name": t.get("name"), "tier": classify_tool(t.get("name", ""))}
            for t in tools
        ]
    }


@app.post("/execute")
async def execute(
    req: ExecuteRequest,
    authorization: str | None = Header(default=None),
    x_agent_id: str | None = Header(default=None),
) -> dict[str, Any]:
    await require_auth(authorization)
    agent_id = x_agent_id or "anonymous"

    _enforce_rate_limit(agent_id)

    tool = req.tool
    tier = classify_tool(tool)

    if tier == TIER_FORBIDDEN:
        await _audit(agent_id, "", tool, "denied", "3", "forbidden tool")
        raise HTTPException(status_code=403, detail="tool not permitted")

    url = req.args.get("url", "")

    # URL/SSRF validation for navigation
    if tool in ("browser_navigate", "browserhand_navigate") and url:
        verdict: UrlVerdict = validate_url(url)
        if not verdict.ok:
            await _audit(agent_id, url, tool, "denied", str(tier), verdict.reason)
            raise HTTPException(status_code=403, detail=verdict.reason)
        _enforce_page_load_limit(agent_id, url)

    # Validated interactions (click/type/fill) must be checked against the
    # latest snapshot and sensitive-field rules.
    if tier == TIER_VALIDATED:
        snap = _snapshots.get(agent_id, "")
        verdict = _validate_interaction(tool, req.args, snap)
        if not verdict.ok:
            await _audit(agent_id, url, tool, "denied", str(tier), verdict.reason)
            raise HTTPException(status_code=403, detail=verdict.reason)
        # Sensitive action keywords (submit/send/delete/sign in/…) require approval.
        if verdict.approval_required:
            await _audit(agent_id, url, tool, "approval_required", str(tier), "sensitive action")
            return {"needs_approval": True, "tool": tool, "reason": verdict.reason}

    # Approval-required tools
    if tier == TIER_APPROVAL:
        await _audit(agent_id, url, tool, "approval_required", str(tier))
        return {"needs_approval": True, "tool": tool}

    # Execute
    is_browserhand = tool.startswith("browserhand_")
    try:
        if is_browserhand:
            result = await _run_browserhand(agent_id, tool, req.args)
        else:
            result = await mcp.call_tool(tool, req.args)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - reconnect once on a stale MCP session
        if is_browserhand:
            raise HTTPException(status_code=502, detail="browserhand relay unreachable")
        await mcp.reconnect()
        result = await mcp.call_tool(tool, req.args)

    # Cache snapshots for subsequent click/type validation.
    if tool in ("browser_snapshot", "browserhand_gettext", "browserhand_extract"):
        text = _extract_text(result)
        if text:
            _snapshots[agent_id] = text

    await _audit(agent_id, url, tool, "allowed", str(tier))

    # Challenge detection (CAPTCHA / Cloudflare / login wall)
    challenge = _detect_challenge(result)
    if challenge:
        await _audit(agent_id, url, tool, "challenge", str(tier), "needs_human")
        return {
            **result,
            "needs_human": True,
            "message": POLICY["challenge_response"]["message"],
        }

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _Verdict:
    ok: bool
    reason: str = ""
    approval_required: bool = False

    def __init__(self, ok: bool, reason: str = "", approval_required: bool = False) -> None:
        self.ok = ok
        self.reason = reason
        self.approval_required = approval_required


def _validate_interaction(tool: str, args: dict[str, Any], snapshot: str) -> _Verdict:
    """Block sensitive fields; flag sensitive actions for approval."""
    target = str(args.get("element") or args.get("ref") or args.get("selector") or "")
    value = str(args.get("text") or args.get("value") or "")

    # Typing into sensitive fields
    if tool in ("browser_type", "browser_fill_form", "browserhand_type"):
        if is_sensitive_element(target, "", value) or is_sensitive_element(target, "", ""):
            return _Verdict(False, "sensitive field blocked")
        if value and _looks_like_secret(value):
            return _Verdict(False, "refusing to type a secret")

    # Clicking sensitive actions
    if tool in ("browser_click", "browser_drag", "browser_drop") and is_sensitive_element(target, "", ""):
        return _Verdict(False, "sensitive action blocked")

    return _Verdict(True)


def _looks_like_secret(value: str) -> bool:
    import re

    return bool(
        re.search(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b", value)
        or re.search(r"\bsk-[A-Za-z0-9]{20,}\b", value)
        or re.search(r"\bgh[psuro]_[A-Za-z0-9]{20,}\b", value)
    )


def _extract_text(result: dict[str, Any]) -> str:
    content = result.get("result", {}).get("content", [])
    chunks = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(item.get("text", ""))
    return "\n".join(chunks)


def _detect_challenge(result: dict[str, Any]) -> bool:
    text = _extract_text(result).lower()
    indicators = (
        "captcha",
        "verify you are human",
        "are you a robot",
        "attention required",
        "cloudflare",
        "just a moment",
        "access denied",
        "challenge",
        "complete the security check",
    )
    return any(ind in text for ind in indicators)
