"""TTL cache and gateway HTTP cache behavior."""

from __future__ import annotations

import httpx
import pytest

import gateway.app as gw
from gateway.security import UrlVerdict
from shared.cache import TTLCache


def test_ttl_cache_expiry_and_lru() -> None:
    cache = TTLCache(maxsize=2, ttl=10)
    cache.set("a", 1, now=0)
    cache.set("b", 2, now=1)
    assert cache.get("a", now=2) == 1
    assert cache.get("a", now=11) is None
    cache.set("c", 3, now=3)
    cache.set("d", 4, now=4)
    assert len(cache) == 2
    assert cache.get("b", now=4) is None


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "t")
    monkeypatch.setattr(gw, "validate_url", lambda _url: UrlVerdict(True))
    gw._HTTP_CACHE.clear()


@pytest.mark.asyncio
async def test_http_cache_avoids_second_fetch(monkeypatch) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            text="<html><body><article><p>cached page</p></article></body></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    first = await gw._http_fetch("http://example.com/cache", transport=transport)
    second = await gw._http_fetch("http://example.com/cache", transport=transport)
    assert calls == 1
    assert first == second


@pytest.mark.asyncio
async def test_no_store_is_not_cached() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            text="<html><body><article><p>fresh</p></article></body></html>",
            headers={"content-type": "text/html", "cache-control": "no-store"},
        )

    transport = httpx.MockTransport(handler)
    await gw._http_fetch("http://example.com/no-store", transport=transport)
    await gw._http_fetch("http://example.com/no-store", transport=transport)
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_can_be_bypassed() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            text="<html><body><article><p>fresh</p></article></body></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    await gw._http_fetch("http://example.com/bypass", transport=transport)
    await gw._http_fetch("http://example.com/bypass", transport=transport, cache=False)
    assert calls == 2
