"""Thread/forum mode: author/order/depth, collapse and caps."""

from __future__ import annotations

from fixture_utils import load_meta, load_page_text

from shared.reader import _extract_thread, read_html


def test_hackernews_thread_keeps_author_order_and_meta() -> None:
    raw = load_page_text("forum-hackernews")
    result = read_html(raw, load_meta("forum-hackernews")["source_url"], max_chars=None)
    assert result.method == "thread"
    assert result.reason == "structured_mode"
    assert "335 points" in result.text
    assert "sgiannopoulos" in result.text
    assert "@torben-friis" in result.text
    assert result.text.count("## Thread:") == 1


def test_stackoverflow_question_and_answers() -> None:
    raw = load_page_text("qa-stackoverflow")
    result = read_html(raw, load_meta("qa-stackoverflow")["source_url"], max_chars=None)
    assert result.method == "thread"
    assert "staticmethod" in result.text and "classmethod" in result.text
    assert "implicitly passed as the first argument" in result.text


def test_quote_lines_are_not_duplicated() -> None:
    html = """<html><body>
    <div class="comment"><div class="comment-body">
    <p>Parent point about widgets.</p>
    </div></div>
    <div class="comment"><div class="comment-body">
    <blockquote>Parent point about widgets.</blockquote>
    <p>A reply with its own detail.</p>
    </div></div>
    </body></html>"""
    out = _extract_thread(html, "https://example.com/thread")
    assert out
    assert "> Parent point" not in out
    assert "A reply with its own detail" in out


def test_low_signal_comments_are_collapsed() -> None:
    html = """<html><body>
    <div class="comment"><div class="comment-body">+1</div></div>
    <div class="comment"><div class="comment-body">[deleted]</div></div>
    <div class="comment"><div class="comment-body">A useful detailed answer about the topic.</div></div>
    </body></html>"""
    out = _extract_thread(html, "https://example.com/thread")
    assert "A useful detailed answer" in out
    assert "low-signal/deleted comments collapsed" in out


def test_thread_cap_marker() -> None:
    rows = "".join(
        f"<div class='comment'><div class='comment-body'>Comment {i} has useful detail.</div></div>"
        for i in range(5)
    )
    out = _extract_thread(
        f"<html><body>{rows}</body></html>", "https://example.com", max_comments=2
    )
    assert "comments capped" in out


def test_unstructured_thread_falls_back() -> None:
    raw = "<html><body><p>No thread structure here.</p></body></html>"
    assert _extract_thread(raw, "https://example.com") == ""
