"""Reader-mode extraction tests (HTML -> clean Markdown)."""

from __future__ import annotations

import sys

import pytest

from shared.reader import (
    content_budget,
    detect_challenge_html,
    html_to_reader,
    read_html,
)

SAMPLE = """<!doctype html>
<html><head><title>Test Article</title>
<style>.x{color:red}</style><script>var a=1;</script></head>
<body>
<nav><a href="/">Home</a><a href="/ads">Buy now</a></nav>
<header><h1>Site Name</h1></header>
<article>
  <h1>Core Heading</h1>
  <p>This is the <b>core information</b> that must survive.</p>
  <table><tr><th>Year</th><th>Revenue</th></tr><tr><td>2025</td><td>100</td></tr></table>
  <p>Another paragraph with a <a href="https://example.com/src">source link</a>.</p>
</article>
<aside>Cookie banner. Subscribe now!</aside>
<footer>Copyright 2026</footer>
</body></html>"""


def test_fallback_strips_tags_when_reader_unavailable(monkeypatch) -> None:
    # Force the lazy `import trafilatura` to fail.
    monkeypatch.setitem(sys.modules, "trafilatura", None)
    out = html_to_reader(SAMPLE, max_chars=None)
    assert "core information" in out
    assert "source link" in out
    assert "<script" not in out.lower()
    assert "<p" not in out.lower()


def test_reader_extracts_main_content() -> None:
    pytest.importorskip("trafilatura")
    out = html_to_reader(SAMPLE, "https://example.com/article", max_chars=None)
    assert "core information" in out
    assert "source link" in out
    # Boilerplate links outside the article are dropped.
    assert "Buy now" not in out
    assert "Subscribe now" not in out
    # Tables survive as Markdown.
    assert "Revenue" in out


def test_max_chars_truncates() -> None:
    out = html_to_reader(SAMPLE, max_chars=40)
    assert "[content truncated]" in out
    assert len(out) <= 40 + len("\n\n[content truncated]")


def test_link_compaction_keeps_labels_and_dedupes_sources(monkeypatch) -> None:
    from shared import reader

    markdown = (
        "Body text. See [source](https://example.com/a) and "
        "[again](https://example.com/a), [js](javascript:void(0)), "
        "[anchor](#section)."
    )
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: markdown)
    out = read_html("<article>tiny</article>", max_chars=None)
    assert out.method == "reader"
    assert "source" in out.text and "again" in out.text
    assert "javascript:" not in out.text
    assert "#section" not in out.text
    assert out.text.count("https://example.com/a") == 1
    assert out.source_count == 1


def test_fallback_when_reader_drops_too_much(monkeypatch) -> None:
    from shared import reader

    html = "<html><body><article>" + ("important data " * 120) + "</article></body></html>"
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "tiny")
    out = read_html(html, max_chars=None)
    assert out.method == "tag-strip"
    assert "important data" in out.text


def test_fallback_when_reader_is_empty(monkeypatch) -> None:
    from shared import reader

    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "")
    out = read_html("<html><body><p>fallback text</p></body></html>", max_chars=None)
    assert out.method == "tag-strip"
    assert "fallback text" in out.text


def test_challenge_detection_structural() -> None:
    html = "<html><head><title>Just a moment...</title></head><body>wait</body></html>"
    assert detect_challenge_html(html) is True


def test_challenge_detection_ignores_article_mention() -> None:
    html = (
        "<html><head><title>How CAPTCHAs work</title></head><body><article>"
        + ("captcha " * 400)
        + "</article></body></html>"
    )
    assert detect_challenge_html(html) is False


def test_challenge_detection_on_visible_text() -> None:
    from shared.reader import detect_challenge_text

    assert detect_challenge_text("Performing security verification") is True
    assert detect_challenge_text("Please verify you are human to continue") is True
    assert detect_challenge_text("An article about captcha design " * 100) is False


def test_content_budget_per_domain() -> None:
    assert content_budget("https://en.wikipedia.org/wiki/Reddit") == 12000
    assert content_budget("https://www.sec.gov/Archives/edgar/data/x/R2.htm") == 32000
    assert content_budget("https://stockanalysis.com/stocks/rddt/financials/") == 24000
    assert content_budget("https://www.sec.gov/x", 50000) == 32000
    assert content_budget("https://www.sec.gov/x", 8000) == 8000
    assert content_budget("https://www.sec.gov/x", None) == 32000
    assert content_budget("https://www.sec.gov/x", "bad") == 32000


def test_truncation_keeps_appended_sources(monkeypatch) -> None:
    from shared import reader

    markdown = "word " * 2000 + "[source](https://example.com/keep)"
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: markdown)
    out = read_html("<article>tiny</article>", max_chars=400)
    assert out.truncated is True
    assert out.text.endswith("- https://example.com/keep")
    assert len(out.text) <= 400 + len(reader.TRUNCATION_MARKER)


def test_repeated_extraction_is_stable() -> None:
    pytest.importorskip("trafilatura")
    body = "".join(
        f"<p>Paragraph {index} contains stable reader-mode content and a "
        f'<a href="https://example.com/{index}">source</a>.</p>'
        for index in range(80)
    )
    html = f"<html><head><title>Stable article</title></head><body><article>{body}</article></body></html>"
    outputs = [read_html(html, "https://example.com/stable", max_chars=None) for _ in range(10)]
    assert all(result.text for result in outputs)
    assert all(result.method == "reader" for result in outputs)


def test_table_fallback_for_data_pages(monkeypatch) -> None:
    from shared import reader

    html = (
        "<html><body><article><p>short</p></article><table>"
        "<tr><th>Year</th><th>Revenue</th><th>Net income</th></tr>"
        "<tr><td>2026</td><td>804905</td><td>252848</td></tr>"
        "<tr><td>2025</td><td>499627</td><td>89297</td></tr>"
        "</table><footer>" + ("boilerplate " * 100) + "</footer></body></html>"
    )
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "short")
    out = read_html(html, "https://www.sec.gov/x", max_chars=None)
    assert out.method == "table"
    assert "804905" in out.text and "252848" in out.text
    assert "boilerplate" not in out.text


def test_table_fallback_strips_nested_style(monkeypatch) -> None:
    from shared import reader

    html = (
        "<html><body><table>"
        "<tr><td><style>.bad{color:red}</style>Label</td><td>123</td><td>456</td></tr>"
        "<tr><td>Row</td><td>789</td><td>012</td></tr>"
        "<tr><td>Another row</td><td>345</td><td>678</td></tr>"
        "</table></body></html>"
    )
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "")
    out = read_html(html, max_chars=None)
    assert out.method == "table"
    assert ".bad{color:red}" not in out.text
    assert "Label" in out.text and "789" in out.text
