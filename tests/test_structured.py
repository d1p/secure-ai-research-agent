"""Structured content, context header and omission markers."""

from __future__ import annotations

from fixture_utils import load_meta, load_page_text

from shared import reader
from shared.reader import read_html

SAMPLE = """<!doctype html><html><head>
<title>Widget Guide</title>
<meta name="description" content="How to configure widgets.">
<link rel="canonical" href="https://example.com/guide?utm_source=x&id=7">
</head><body><main><h1>Widget Guide</h1>
<p>Widgets are configurable.</p>
<h2>Options</h2><ul><li>theme</li><li>refresh</li></ul>
<pre><code class="language-python">print("hi")</code></pre>
<table><tr><th>Option</th><th>Default</th></tr><tr><td>theme</td><td>auto</td></tr></table>
</main></body></html>"""


def test_header_title_h1_description_canonical() -> None:
    result = read_html(SAMPLE, "https://example.com/guide", max_chars=None)
    assert result.text.startswith("# Widget Guide")
    assert "> How to configure widgets." in result.text
    assert "https://example.com/guide?id=7" in result.text
    assert "utm_source" not in result.text
    # H1 duplicates the title, so it is not emitted twice.
    assert result.text.count("Widget Guide") == 1


def test_code_lists_and_tables_survive(monkeypatch) -> None:
    # Force the reader path so the header/structured assertions are independent
    # of trafilatura availability.
    monkeypatch.setattr(
        reader,
        "_extract_markdown",
        lambda *a, **k: (
            'Widgets are configurable.\n\n- theme\n- refresh\n\n```python\nprint("hi")\n```\n\n'
            "| Option | Default |\n| --- | --- |\n| theme | auto |"
        ),
    )
    result = read_html(SAMPLE, "https://example.com/guide", max_chars=None)
    assert "```python" in result.text and 'print("hi")' in result.text
    assert "- theme" in result.text and "- refresh" in result.text
    assert "| Option | Default |" in result.text


def test_xbrl_table_markdown_and_omission_marker() -> None:
    raw = load_page_text("xbrl-statement")
    result = read_html(raw, load_meta("xbrl-statement")["source_url"], max_chars=None)
    assert result.method == "table"
    assert "| Metric | 2026 | 2025 |" in result.text
    assert "| --- | --- | --- |" in result.text
    assert "804,905" in result.text
    assert "[table mode: non-table context omitted" in result.text


def test_fallback_marker_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "")
    result = read_html(
        "<html><body><article><p>"
        + ("fallback text " * 100)
        + "</p></article></body></html>",
        max_chars=None,
    )
    assert result.method == "tag-strip"
    assert "[reader low coverage; tag-strip fallback used]" in result.text


def test_truncation_marker_explains_next_step() -> None:
    result = read_html(SAMPLE, "https://example.com/guide", max_chars=120)
    assert "[content truncated" in result.text
    assert "raise max_chars" in result.text


def test_refusal_results_have_no_header() -> None:
    challenge = read_html(load_page_text("challenge-bot"), max_chars=None)
    assert challenge.text == ""
    paywall = read_html(load_page_text("paywall-cookie"), max_chars=None)
    assert paywall.text.startswith("[paywall]")
    assert "# " not in paywall.text
