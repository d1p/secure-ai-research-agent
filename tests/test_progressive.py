"""Opt-in outline/section/query views (default remains full)."""

from __future__ import annotations

from shared import reader
from shared.reader import read_html

HTML = """<html><head><title>Doc</title></head><body><article>
<h1>Doc</h1><h2>Alpha</h2><p>alpha paragraph with widgets.</p>
<h2>Beta</h2><p>beta paragraph about circuits.</p>
<h2>Gamma</h2><p>gamma paragraph with widgets and circuits.</p>
</article></body></html>"""


def test_default_is_full() -> None:
    full = read_html(HTML, max_chars=None)
    assert "[outline]" not in full.text
    assert "beta paragraph" in full.text


def test_outline_has_headings_and_offsets() -> None:
    out = read_html(HTML, max_chars=500, mode="outline")
    assert "[outline]" in out.text
    assert "## Alpha @" in out.text
    assert "## Beta @" in out.text
    assert len(out.text) <= 500 + 200


def test_section_round_trips_offset() -> None:
    full = read_html(HTML, max_chars=None)
    start = full.text.index("beta paragraph")
    out = read_html(HTML, max_chars=None, mode="section", offset=start, length=40)
    assert "beta paragraph" in out.text
    assert f"[section offset={start}" in out.text


def test_query_excerpt_selects_relevant_paragraph() -> None:
    out = read_html(HTML, max_chars=400, mode="query", query="circuits")
    assert "[query excerpt: circuits]" in out.text
    assert "circuits" in out.text
    assert "alpha paragraph" not in out.text


def test_query_without_match_falls_back() -> None:
    out = read_html(HTML, max_chars=400, mode="query", query="nonexistentterm")
    assert "Doc" in out.text


def test_progressive_respects_budget() -> None:
    for mode, kwargs in (
        ("outline", {}),
        ("section", {"offset": 10, "length": 50}),
        ("query", {"query": "widgets"}),
    ):
        out = read_html(HTML, max_chars=120, mode=mode, **kwargs)
        assert len(out.text) <= 120 + 200, (mode, len(out.text))


def test_invalid_mode_falls_back_to_full(monkeypatch) -> None:
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "fixed body")
    out = read_html(HTML, max_chars=None, mode="bogus")
    assert "fixed body" in out.text
