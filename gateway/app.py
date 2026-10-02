"""Browser safeguard gateway.

The security boundary between the orchestrator and the browser.  The browser is
driven by a Stagehand service (act/observe/extract over Chrome CDP); Stagehand
is NOT a security boundary, this service is.

Responsibilities (project spec section 13):
  * shared-token auth (orchestrator -> gateway)
  * agent_id from the authenticated caller only (header), never the body
  * URL / DNS / redirect validation + SSRF prevention
  * tool-tier enforcement (tiers 0..3)
  * rate limiting + page-load limiting
  * audit logging to Postgres (browser_audit)
"""

from __future__ import annotations

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
STAGEHAND_ENDPOINT = os.environ.get("STAGEHAND_ENDPOINT", "http://browser:8931")
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
# Stagehand client (stateless HTTP -> browser container's Stagehand service)
# ---------------------------------------------------------------------------
class StagehandClient:
    _ENDPOINTS = {
        "navigate": ("/navigate", "url"),
        "read": ("/read", None),
        "act": ("/act", "instruction"),
        "observe": ("/observe", "instruction"),
        "extract": ("/extract", "instruction"),
        "screenshot": ("/screenshot", None),
    }

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))

    async def call(self, action: str, args: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        endpoint, key = self._ENDPOINTS.get(action, ("/" + action, None))
        body: dict[str, Any] = dict(args)
        if key and key not in body:
            return 400, {"error": f"missing argument '{key}'"}
        resp = await self._client.post(f"{self.base_url}{endpoint}", json=body)
        try:
            data = resp.json()
        except json.JSONDecodeError:
            data = {"error": resp.text}
        return resp.status_code, data


stagehand = StagehandClient(STAGEHAND_ENDPOINT)


def _stagehand_result(action: str, data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Stagehand response to the MCP `tools/call` envelope the
    orchestrator already parses: {"result": {"content": [{"type": "text", ...}]}}."""
    if action == "read":
        text = data.get("text", "")
    elif action == "navigate":
        text = json.dumps({"ok": True, "url": data.get("url", ""), "title": data.get("title", "")})
    elif action == "screenshot":
        text = json.dumps({"screenshot": data.get("screenshot", "")[:200]}) if data.get("screenshot") else ""
    else:
        payload = data.get("data", data.get("result", data))
        text = json.dumps(payload, default=str) if payload not in (None, "") else ""
    return {"result": {"content": [{"type": "text", "text": text}]}}


async def _run_stagehand(agent_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    action = tool.removeprefix("stagehand_")
    try:
        status, data = await stagehand.call(action, args)
    except httpx.HTTPError as exc:  # noqa: BLE001 - connection-level failure
        raise HTTPException(status_code=502, detail="stagehand service unreachable") from exc
    if status >= 400:
        raise HTTPException(status_code=502, detail=data.get("error", f"stagehand returned {status}"))
    return _stagehand_result(action, data)


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


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok"}


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
    if tool in ("stagehand_navigate", "browser_navigate") and url:
        verdict: UrlVerdict = validate_url(url)
        if not verdict.ok:
            await _audit(agent_id, url, tool, "denied", str(tier), verdict.reason)
            raise HTTPException(status_code=403, detail=verdict.reason)
        _enforce_page_load_limit(agent_id, url)

    # Validated interactions (act) must be checked against sensitive-action rules.
    if tier == TIER_VALIDATED:
        verdict = _validate_interaction(tool, req.args)
        if not verdict.ok:
            await _audit(agent_id, url, tool, "denied", str(tier), verdict.reason)
            raise HTTPException(status_code=403, detail=verdict.reason)
        if verdict.approval_required:
            await _audit(agent_id, url, tool, "approval_required", str(tier), "sensitive action")
            return {"needs_approval": True, "tool": tool, "reason": verdict.reason}

    # Approval-required tools
    if tier == TIER_APPROVAL:
        await _audit(agent_id, url, tool, "approval_required", str(tier))
        return {"needs_approval": True, "tool": tool}

    # Execute via Stagehand
    result = await _run_stagehand(agent_id, tool, req.args)

    # Cache snapshots for subsequent click/type validation.
    if tool == "stagehand_read":
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


def _validate_interaction(tool: str, args: dict[str, Any]) -> _Verdict:
    """Block sensitive actions; flag sensitive instructions for approval."""
    if tool == "stagehand_act":
        instruction = str(args.get("instruction", "") or "")
        target = str(args.get("element") or args.get("ref") or args.get("selector") or "")
        value = str(args.get("text") or args.get("value") or "")

        if target and (is_sensitive_element(target, "", "") or is_sensitive_element(target, "", value)):
            return _Verdict(False, "sensitive field blocked")
        if value and _looks_like_secret(value):
            return _Verdict(False, "refusing to type a secret")
        if _action_is_sensitive(instruction):
            return _Verdict(True, "sensitive action", approval_required=True)

    return _Verdict(True)


def _action_is_sensitive(instruction: str) -> bool:
    from security import action_is_sensitive

    return action_is_sensitive(instruction)


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
