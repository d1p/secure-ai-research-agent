"""Gateway fetch reliability and SSRF redirect tests (offline)."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi import HTTPException

import gateway.app as gw
from gateway.security import UrlVerdict

HTML = (
    "<html><head><title>t</title></head><body><article><p>"
    + "word " * 2000
    + "</p></article></body></html>"
)


@pytest.fixture(autouse=True)
def _allow_urls(monkeypatch):
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "test-token")
    monkeypatch.setattr(gw, "validate_url", lambda _url: UrlVerdict(True))
    gw._HTTP_CACHE.clear()


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token", "X-Agent-Id": "pytest"}


@pytest.mark.asyncio
async def test_retry_and_backoff(monkeypatch) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        if len(attempts) < 3:
            raise httpx.ConnectError("transient", request=request)
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    result = await gw._http_fetch(
        "http://example.com/page", transport=httpx.MockTransport(handler)
    )
    assert len(attempts) == 3
    assert sleeps == [0.25, 0.5]
    assert json.loads(result["result"]["content"][0]["text"])["status"] == 200


@pytest.mark.asyncio
async def test_clean_502_with_exception_type(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    with pytest.raises(HTTPException) as exc:
        await gw._http_fetch(
            "http://example.com/page", transport=httpx.MockTransport(handler)
        )
    assert exc.value.status_code == 502
    assert "ConnectError" in exc.value.detail


@pytest.mark.asyncio
async def test_redirect_to_blocked_address_is_rejected(monkeypatch) -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://blocked.example/"},
        )

    def validate(url: str) -> UrlVerdict:
        if "blocked" in url:
            return UrlVerdict(False, "blocked private address")
        return UrlVerdict(True)

    monkeypatch.setattr(gw, "validate_url", validate)
    with pytest.raises(HTTPException) as exc:
        await gw._http_fetch(
            "http://example.com/page", transport=httpx.MockTransport(handler)
        )
    assert exc.value.status_code == 403
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_health_stays_responsive_during_large_parse(monkeypatch) -> None:
    big = (
        "<html><body><article><p>" + "word " * 300000 + "</p></article></body></html>"
    ).encode()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big, headers={"content-type": "text/html"})

    def slow_read(*_args, **_kwargs):
        time.sleep(0.5)
        from shared.reader import ReaderResult

        return ReaderResult(text="parsed", method="reader", reason="reader_ok")

    monkeypatch.setattr(gw, "read_html", slow_read)
    transport = httpx.ASGITransport(app=gw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(
                "/execute",
                headers=_auth(),
                json={"tool": "http_fetch", "args": {"url": "http://example.com/big"}},
            )
        )
        await asyncio.sleep(0.05)
        started = time.perf_counter()
        response = await client.get("/healthz")
        elapsed = time.perf_counter() - started
        assert response.status_code == 200
        assert elapsed < 0.3, f"health blocked for {elapsed:.3f}s"
        result = await task
        assert result.status_code == 200


@pytest.mark.asyncio
async def test_http_fetch_tier0_and_missing_url() -> None:
    transport = httpx.ASGITransport(app=gw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/execute",
            headers=_auth(),
            json={"tool": "http_fetch", "args": {}},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_metrics_endpoint() -> None:
    transport = httpx.ASGITransport(app=gw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
