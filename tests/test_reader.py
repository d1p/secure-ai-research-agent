"""Reader-mode extraction tests (HTML -> clean Markdown)."""

from __future__ import annotations

import sys

import pytest

from gateway.reader import html_to_reader

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
