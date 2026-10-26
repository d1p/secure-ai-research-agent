"""Smart web-access tools for Open WebUI.

Exposes three deliberately-different tools so the model can pick the cheapest
one that actually works for the job:

* ``web_search``  - DuckDuckGo snippets. Default for factual / general info.
* ``http_fetch``  - plain HTTP(S) GET (through the safeguard gateway). Static
                    pages, docs, direct files. No JavaScript.
* ``browse_page`` - the real sandboxed Stagehand Chrome (through the
                    orchestrator's ``/web-loader``). JS-heavy, interactive or
                    shopping sites (e.g. eBay) where the other two fail.

The model is steered by the router model's system prompt; these functions only
provide the capabilities.
"""

from __future__ import annotations

import json
import os

import httpx

_WEB_LOADER_URL = os.environ.get(
    "EXTERNAL_WEB_LOADER_URL", "http://orchestrator:8080/web-loader"
)
_WEB_LOADER_BASE = _WEB_LOADER_URL.rsplit("/", 1)[0]
_WEB_LOADER_KEY = os.environ.get("EXTERNAL_WEB_LOADER_API_KEY", "")


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_WEB_LOADER_KEY}"}


def _run_id(metadata: dict | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in ("session_id", "chat_id", "message_id"):
        value = metadata.get(key)
        if value:
            return f"owui:{value}"
    return ""


class Tools:
    def __init__(self) -> None:
        self.citation = True

    async def web_search(self, query: str, count: int = 5) -> str:
        """Search the web for general information and return titles, URLs and snippets.

        Use this FIRST for factual or general questions ("what is X", "price of Y
        in general", "recent news about Z"). Cheap and fast. If snippets are not
        enough and you need the full page, follow up with http_fetch (static) or
        browse_page (interactive).

        :param query: the search query
        :param count: number of results to return (1-10, default 5)
        """
        try:
            from ddgs import DDGS

            results = list(DDGS().text(query, max_results=max(1, min(int(count), 10))))
        except Exception as exc:  # noqa: BLE001
            return f"web_search failed: {exc}"

        if not results:
            return "web_search returned no results"

        lines = []
        for item in results:
            lines.append(
                "- {title}\n  {url}\n  {snippet}".format(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=(item.get("body", "") or "").strip(),
                )
            )
        return "\n".join(lines)

    async def http_fetch(
        self,
        url: str,
        max_chars: int = 0,
        links: str = "sources",
        mode: str = "full",
        offset: int = 0,
        length: int = 0,
        query: str = "",
        __metadata__: dict | None = None,
    ) -> str:
        """Fetch a URL over plain HTTP(S) and return its text content.

        Use for static pages, documentation, articles, sitemaps or direct files.
        Fast and cheap, but it does NOT run JavaScript, so dynamic/interactive
        sites will return little or nothing - use browse_page for those.

        :param url: absolute http:// or https:// URL
        :param max_chars: maximum characters to return; 0 uses the page-type
            ceiling (12k article, 16k docs/thread, 24k paper/table, 8k listing)
        :param links: citation policy: sources (default), inline, or none
        :param mode: full (default), outline, section, or query
        :param offset: section start (with mode=section)
        :param length: section length (with mode=section)
        :param query: query terms (with mode=query)
        """
        if not url.lower().startswith(("http://", "https://")):
            return "http_fetch error: url must start with http:// or https://"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = _auth()
                run_id = _run_id(__metadata__)
                if run_id:
                    headers["X-Run-Id"] = run_id
                resp = await client.post(
                    f"{_WEB_LOADER_BASE}/fetch",
                    headers=headers,
                    json={
                        "url": url,
                        "max_chars": int(max_chars),
                        "links": links,
                        "mode": mode,
                        "offset": int(offset),
                        "length": int(length),
                        "query": query or None,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return f"http_fetch error: {exc}"
        return data.get("text", "")

    async def browse_page(self, url: str, __metadata__: dict | None = None) -> str:
        """Open a URL in the real sandboxed browser and return the visible text.

        Use for JavaScript-heavy, interactive or shopping sites where
        http_fetch fails (e.g. eBay listings, sites that need cookies/login).
        Slower than http_fetch, so only use when search/snippets are not enough.

        :param url: absolute http:// or https:// URL
        """
        if not url.lower().startswith(("http://", "https://")):
            return "browse_page error: url must start with http:// or https://"
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                headers = _auth()
                run_id = _run_id(__metadata__)
                if run_id:
                    headers["X-Run-Id"] = run_id
                resp = await client.post(
                    f"{_WEB_LOADER_BASE}/web-loader",
                    headers=headers,
                    json={"urls": [url]},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return f"browse_page error: {exc}"
        if isinstance(data, list) and data:
            # /web-loader already applies the page-type reader budget.
            return data[0].get("page_content") or ""
        return json.dumps(data)
