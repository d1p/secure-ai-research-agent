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

import asyncio
import json
import os
import re
import time
from typing import Any, ClassVar

import httpx
import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
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

from shared import metrics
from shared.budget import OutputBudget
from shared.cache import TTLCache, env_ttl
from shared.reader import (
    content_budget,
    detect_challenge_html,
    detect_challenge_text,
    detect_page_type,
    extract_pdf,
    read_html,
)
from shared.telemetry import alert_large_empty, host_from_url, record_load
from shared.tokens import count_tokens
from shared.untrusted import wrap_untrusted

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
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return

    resource = Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", "safeguard-gateway")}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


_setup_otel(app)


# ---------------------------------------------------------------------------
# Stagehand client (stateless HTTP -> browser container's Stagehand service)
# ---------------------------------------------------------------------------
class StagehandClient:
    _ENDPOINTS: ClassVar[dict[str, tuple[str, str | None]]] = {
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

    async def call(
        self, action: str, args: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
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
    elif action == "content":
        # Raw HTML from the rendered page; the orchestrator turns this into
        # reader-mode Markdown before handing it to an agent.
        text = data.get("html", "")
    elif action == "navigate":
        text = json.dumps(
            {"ok": True, "url": data.get("url", ""), "title": data.get("title", "")}
        )
    elif action == "screenshot":
        text = (
            json.dumps({"screenshot": data.get("screenshot", "")[:200]})
            if data.get("screenshot")
            else ""
        )
    else:
        payload = data.get("data", data.get("result", data))
        text = json.dumps(payload, default=str) if payload not in (None, "") else ""
    return {"result": {"content": [{"type": "text", "text": text}]}}


async def _run_stagehand(
    agent_id: str, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    action = tool.removeprefix("stagehand_")
    try:
        status, data = await stagehand.call(action, args)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="stagehand service unreachable"
        ) from exc
    if status >= 400:
        raise HTTPException(
            status_code=502, detail=data.get("error", f"stagehand returned {status}")
        )
    if action == "content" and detect_challenge_html(data.get("html", "")):
        message = _challenge_message()
        return {
            "result": {
                "content": [{"type": "text", "text": f"[needs_human] {message}"}]
            },
            "needs_human": True,
            "message": message,
        }
    return _stagehand_result(action, data)


# ---------------------------------------------------------------------------
# Plain HTTP(S) fetch (no browser).  For static pages/files; the browser stays
# reserved for JS-heavy / interactive sites.  Same SSRF + audit boundary.
# ---------------------------------------------------------------------------
MAX_FETCH_REDIRECTS = 5
MAX_FETCH_BYTES = 8_000_000
_HTTP_CACHE = TTLCache(
    maxsize=int(os.environ.get("WEB_LOADER_CACHE_SIZE", "128")),
    ttl=env_ttl("WEB_LOADER_CACHE_TTL", 300.0),
)
_OUTPUT_BUDGET = OutputBudget()
_FETCH_UA = os.environ.get(
    "FETCH_USER_AGENT",
    "homelab-ai-stack/1.0 (ops@example.invalid)",
)


async def _http_fetch(
    url: str,
    max_chars: int | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    cache: bool = True,
    links: str = "sources",
    mode: str = "full",
    offset: int = 0,
    length: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    cache_key = f"{url}|{max_chars or 0}|{links}|{mode}|{offset}|{length}|{query or ''}"
    if cache:
        cached = _HTTP_CACHE.get(cache_key)
        if cached:
            record_load(
                service="gateway",
                reason="cache_hit",
                method=cached.get("method", "text"),
                page_type=cached.get("page_type", "unknown"),
                chars_out=cached.get("chars_out", 0),
                tokens_out=cached.get("tokens_out", 0),
                truncated=cached.get("truncated", False),
                source_count=cached.get("source_count", 0),
                cache_hit=True,
                host=host_from_url(url),
            )
            return cached["result"]
        metrics.inc(
            "web_loader_cache_lookups_total",
            {"service": "gateway", "result": "miss"},
        )
    current = url
    resp: httpx.Response | None = None
    transport = transport or httpx.AsyncHTTPTransport(retries=2)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=False,
        transport=transport,
    ) as client:
        for _ in range(MAX_FETCH_REDIRECTS + 1):
            verdict = validate_url(current)
            if not verdict.ok:
                raise HTTPException(status_code=403, detail=verdict.reason)
            for attempt in range(3):
                try:
                    resp = await client.get(
                        current,
                        headers={
                            "User-Agent": _FETCH_UA,
                            "Accept": "text/html,application/xhtml+xml,text/plain,application/json,*/*",
                        },
                    )
                    break
                except (
                    httpx.ConnectTimeout,
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                ) as exc:
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    raise HTTPException(
                        status_code=502,
                        detail=f"fetch failed after retry: {type(exc).__name__}: {exc}",
                    ) from exc
                except httpx.HTTPError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"fetch failed: {type(exc).__name__}: {exc}",
                    ) from exc
            if resp.is_redirect and "location" in resp.headers:
                current = str(httpx.URL(current).join(resp.headers["location"]))
                continue
            break
    content_type = resp.headers.get("content-type", "")
    body = resp.content[:MAX_FETCH_BYTES]
    is_pdf = "application/pdf" in content_type.lower() or body.startswith(b"%PDF-")
    is_html = "html" in content_type.lower() or body.lstrip()[:15].lower().startswith(
        b"<!doctype html"
    )
    host = host_from_url(current)
    reason = "text_passthrough"
    method = "text"
    page_type = "unknown"
    truncated = False
    source_count = 0
    chars_in = len(body)
    tokens_in = 0

    if is_pdf:
        page_type = "pdf"
        budget = content_budget(current, max_chars, page_type)
        extracted = await asyncio.to_thread(extract_pdf, body, budget)
        reason = extracted.reason or "pdf_text"
        method = extracted.method
        truncated = extracted.truncated
        raw = extracted.text
        tokens_in = count_tokens(raw)
    elif is_html:
        raw = body.decode(resp.encoding or "utf-8", errors="replace")
        page_type = detect_page_type(raw, current)
        budget = content_budget(current, max_chars, page_type)
        tokens_in = count_tokens(raw)
        extracted = await asyncio.to_thread(
            read_html,
            raw,
            current,
            budget,
            include_links=links,
            mode=mode,
            offset=offset,
            length=length,
            query=query,
        )
        reason = extracted.reason or "reader_ok"
        method = extracted.method
        page_type = extracted.page_type
        truncated = extracted.truncated
        source_count = extracted.source_count
        if extracted.challenge:
            message = _challenge_message()
            record_load(
                service="gateway",
                reason="challenge_needs_human",
                method=method,
                page_type=page_type,
                chars_in=chars_in,
                chars_out=0,
                tokens_in=tokens_in,
                tokens_out=0,
                truncated=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                host=host,
            )
            result = {
                "result": {
                    "content": [{"type": "text", "text": f"[needs_human] {message}"}]
                },
                "needs_human": True,
                "message": message,
            }
            cache_control = resp.headers.get("cache-control", "").lower()
            if (
                cache
                and "no-store" not in cache_control
                and "no-cache" not in cache_control
            ):
                _HTTP_CACHE.set(
                    cache_key,
                    {
                        "result": result,
                        "method": method,
                        "page_type": page_type,
                        "chars_out": 0,
                        "tokens_out": 0,
                        "truncated": False,
                        "source_count": 0,
                    },
                )
            return result
        if not extracted.text:
            alert_large_empty(
                service="gateway",
                host=host,
                raw_chars=len(raw),
                content_type=content_type,
                reason=reason,
            )
        raw = extracted.text
    else:
        raw = body.decode(resp.encoding or "utf-8", errors="replace")
        if "\x00" in raw[:4096] or not content_type.lower().startswith(
            ("text/", "application/json", "application/xml")
        ):
            reason = "binary_rejected"
            method = "binary"
            raw = f"[binary content not shown: content_type={content_type or 'unknown'} bytes={len(body)}]"
        else:
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            budget = content_budget(current, max_chars, "unknown")
            if len(raw) > budget:
                raw = raw[:budget] + "\n\n[content truncated]"
                truncated = True
        tokens_in = count_tokens(raw)

    raw = wrap_untrusted(raw, current)
    chars_out = len(raw)
    tokens_out = count_tokens(raw)
    record_load(
        service="gateway",
        reason=reason,
        method=method,
        page_type=page_type,
        chars_in=chars_in,
        chars_out=chars_out,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        truncated=truncated,
        source_count=source_count,
        duration_ms=(time.perf_counter() - started) * 1000,
        host=host,
    )
    text = json.dumps(
        {
            "url": current,
            "status": resp.status_code,
            "content_type": content_type,
            "text": raw,
            "reason": reason,
            "method": method,
            "page_type": page_type,
            "truncated": truncated,
            "source_count": source_count,
        },
        default=str,
    )
    result = {"result": {"content": [{"type": "text", "text": text}]}}
    cache_control = resp.headers.get("cache-control", "").lower()
    if cache and "no-store" not in cache_control and "no-cache" not in cache_control:
        _HTTP_CACHE.set(
            cache_key,
            {
                "result": result,
                "method": method,
                "page_type": page_type,
                "chars_out": chars_out,
                "tokens_out": tokens_out,
                "truncated": truncated,
                "source_count": source_count,
            },
        )
    return result


# ---------------------------------------------------------------------------
# Policy / state
# ---------------------------------------------------------------------------
def _load_policy() -> dict[str, Any]:
    with open(POLICY_FILE, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


POLICY = _load_policy()
_rate_state: dict[str, list[float]] = {}  # agent_id -> request timestamps
_page_loads: dict[str, dict[str, float]] = {}  # agent_id -> {domain: last_ts}
_snapshots: dict[str, str] = {}  # agent_id -> latest snapshot text


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


async def _audit(
    agent_id: str, url: str, tool: str, status: str, tier: str = "", detail: str = ""
) -> None:
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orchestrator.browser_audit (agent_id, url, tool, tier, status, detail) "
                "VALUES ($1,$2,$3,$4,$5,$6)",
                agent_id,
                url,
                tool,
                tier,
                status,
                detail,
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


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint() -> str:
    from shared import metrics

    return metrics.render()


@app.post("/execute")
async def execute(
    req: ExecuteRequest,
    authorization: str | None = Header(default=None),
    x_agent_id: str | None = Header(default=None),
    x_run_id: str | None = Header(default=None),
) -> dict[str, Any]:
    await require_auth(authorization)
    agent_id = x_agent_id or "anonymous"
    run_id = x_run_id or f"agent:{agent_id}"

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
            await _audit(
                agent_id, url, tool, "approval_required", str(tier), "sensitive action"
            )
            return {"needs_approval": True, "tool": tool, "reason": verdict.reason}

    # Approval-required tools
    if tier == TIER_APPROVAL:
        await _audit(agent_id, url, tool, "approval_required", str(tier))
        return {"needs_approval": True, "tool": tool}

    # Plain HTTP(S) fetch: handled locally (gateway holds the egress network),
    # never via the browser.
    if tool == "http_fetch":
        if not url:
            raise HTTPException(status_code=400, detail="missing url")
        try:
            max_chars = int(req.args.get("max_chars", 0))
        except (TypeError, ValueError):
            max_chars = 0
        cache = bool(req.args.get("cache", True))
        links = str(req.args.get("links", "sources"))
        if links not in {"sources", "inline", "none"}:
            raise HTTPException(
                status_code=400, detail="links must be sources|inline|none"
            )
        try:
            result = await _http_fetch(url, max_chars, cache=cache, links=links)
        except HTTPException as exc:
            reason = "fetch_failed" if exc.status_code >= 500 else "fetch_blocked"
            record_load(
                service="gateway",
                reason=reason,
                method="text",
                page_type="unknown",
                error_class=str(exc.status_code),
                host=host_from_url(url),
            )
            await _audit(
                agent_id,
                url,
                tool,
                "denied" if exc.status_code < 500 else "error",
                str(tier),
                json.dumps({"reason": reason, "status": exc.status_code}),
            )
            raise
        result = _apply_output_budget(result, run_id)
        status = "challenge" if result.get("needs_human") else "allowed"
        await _audit(
            agent_id,
            url,
            tool,
            status,
            str(tier),
            json.dumps(
                {
                    "reason": "challenge_needs_human"
                    if result.get("needs_human")
                    else "reader_ok"
                }
            ),
        )
        return result

    # Execute via Stagehand
    result = await _run_stagehand(agent_id, tool, req.args)

    if tool in {"stagehand_read", "stagehand_content"}:
        result = _apply_output_budget(result, run_id)

    # Cache snapshots for subsequent click/type validation.
    if tool == "stagehand_read":
        text = _extract_text(result)
        if text:
            _snapshots[agent_id] = text

    await _audit(agent_id, url, tool, "allowed", str(tier))

    # Challenge detection (CAPTCHA / Cloudflare / login wall).  Skip raw HTML:
    # page markup often mentions these words without being a challenge page.
    challenge = False if tool == "stagehand_content" else _detect_challenge(result)
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

    def __init__(
        self, ok: bool, reason: str = "", approval_required: bool = False
    ) -> None:
        self.ok = ok
        self.reason = reason
        self.approval_required = approval_required


def _validate_interaction(tool: str, args: dict[str, Any]) -> _Verdict:
    """Block sensitive actions; flag sensitive instructions for approval."""
    if tool == "stagehand_act":
        instruction = str(args.get("instruction", "") or "")
        target = str(
            args.get("element") or args.get("ref") or args.get("selector") or ""
        )
        value = str(args.get("text") or args.get("value") or "")

        if target and (
            is_sensitive_element(target, "", "")
            or is_sensitive_element(target, "", value)
        ):
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


def _apply_output_budget(result: dict[str, Any], run_id: str) -> dict[str, Any]:
    text = _extract_text(result)
    if not text:
        return result
    allowed, used = _OUTPUT_BUDGET.consume(run_id, len(text))
    if allowed:
        return result
    metrics.inc("web_loader_budget_exceeded_total", {"service": "gateway"})
    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": "[budget_exceeded] Tool-output budget reached; summarize what you have and stop fetching.",
                }
            ]
        },
        "budget_exceeded": True,
        "used_chars": used,
    }


def _detect_challenge(result: dict[str, Any]) -> bool:
    return detect_challenge_text(_extract_text(result))


def _challenge_message() -> str:
    return str(
        (POLICY.get("challenge_response") or {}).get(
            "message", "Challenge detected; human intervention required via noVNC."
        )
    )
