"""Link policy, compaction and navigation/footer stripping."""

from __future__ import annotations

import json

import httpx
import pytest

import gateway.app as gw
from gateway.security import UrlVerdict
from shared import reader
from shared.reader import read_html

BODY = (
    "<html><body><nav><a href='https://example.com/nav'>Nav</a></nav>"
    "<article><p>Body <a href='https://example.com/a'>A</a> and "
    "<a href='https://example.com/a'>A again</a>.</p></article>"
    "<footer><a href='https://example.com/footer'>Footer</a></footer>"
    "</body></html>"
)


def test_sources_mode_dedupes_and_keeps_labels(monkeypatch) -> None:
    markdown = "[one](https://example.com/1) [one](https://example.com/1) [two](https://example.com/2)"
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: markdown)
    result = read_html("<article>x</article>", max_chars=None)
    assert result.source_count == 2
    assert result.text.count("https://example.com/1") <= 2
    assert "one" in result.text and "two" in result.text


def test_javascript_and_fragment_links_are_not_sources(monkeypatch) -> None:
    markdown = (
        "Body [js](javascript:void(0)) [frag](#x) [ok](https://example.com/ok) "
        "[mail](mailto:x@example.com)"
    )
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: markdown)
    result = read_html("<article>x</article>", max_chars=None)
    assert "javascript:" not in result.text
    assert "mailto:" not in result.text
    assert "#x" not in result.text
    assert result.source_count == 1


def test_source_cap_reports_omitted_links(monkeypatch) -> None:
    markdown = " ".join(f"[l{i}](https://example.com/{i})" for i in range(20))
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: markdown)
    result = read_html("<article>x</article>", max_chars=1200)
    assert "source links omitted by the link cap" in result.text
    assert (
        len([line for line in result.text.splitlines() if line.startswith("- http")])
        <= 8
    )


def test_navigation_footer_links_are_stripped() -> None:
    result = read_html(BODY, "https://example.com/article", max_chars=None)
    assert "example.com/nav" not in result.text
    assert "example.com/footer" not in result.text


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "t")
    monkeypatch.setattr(gw, "validate_url", lambda _url: UrlVerdict(True))
    gw._HTTP_CACHE.clear()


@pytest.mark.asyncio
async def test_gateway_link_policy_per_call(monkeypatch) -> None:
    from shared.reader import ReaderResult

    def fake_read(raw, url, budget, include_links="sources", **kwargs):
        texts = {
            "sources": "Body\n\nSources:\n- https://example.com/a",
            "inline": "Body [A](https://example.com/a)",
            "none": "Body A",
        }
        return ReaderResult(
            text=texts[include_links], method="reader", reason="reader_ok"
        )

    monkeypatch.setattr(gw, "read_html", fake_read)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=BODY, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    sources = await gw._http_fetch(
        "http://example.com/links1", transport=transport, links="sources"
    )
    inline = await gw._http_fetch(
        "http://example.com/links2", transport=transport, links="inline"
    )
    none = await gw._http_fetch(
        "http://example.com/links3", transport=transport, links="none"
    )
    sources_text = json.loads(sources["result"]["content"][0]["text"])["text"]
    inline_text = json.loads(inline["result"]["content"][0]["text"])["text"]
    none_text = json.loads(none["result"]["content"][0]["text"])["text"]
    assert "Sources:" in sources_text
    assert "](https://example.com/a)" in inline_text
    assert "https://example.com/a" not in none_text or "Sources:" not in none_text
