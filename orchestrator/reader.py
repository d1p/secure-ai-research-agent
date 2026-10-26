"""Reader-mode extraction for fetched HTML.

Turns a full HTML document into clean Markdown containing the main content
(title, body text, links, tables) using trafilatura.  Falls back to a
conservative tag-strip when readability extraction yields nothing.

Goal: drop navigation, ads, cookie banners, scripts, styles and other
boilerplate so callers spend tokens only on core information.
"""

from __future__ import annotations

import html as html_lib
import re

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(
    r"<(script|style|noscript|template|svg|canvas)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


def _str_from_any(value):
    """Coerce bytes/lxml/Response-like input to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return str(value)


def _strip_tags(raw: str) -> str:
    text = _SCRIPT_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return _tidy(_WS_RE.sub(" ", text))


def _tidy(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    text = _BLANKLINES_RE.sub("\n\n", "\n".join(lines))
    return text.strip()


def html_to_reader(html, url: str = "", max_chars: int | None = 20000) -> str:
    """Return reader-mode Markdown for *html*. Best effort, never raises."""
    source = _str_from_any(html)
    if not source.strip():
        return ""

    cleaned = ""
    try:
        import trafilatura

        cleaned = (
            trafilatura.extract(
                source,
                url=url or None,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_formatting=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,
                deduplicate=True,
            )
            or ""
        )
        cleaned = _tidy(cleaned)
    except Exception:  # noqa: BLE001 - best-effort: fall back to tag-strip
        cleaned = ""

    if not cleaned:
        cleaned = _strip_tags(source)

    if max_chars and max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n\n[content truncated]"
    return cleaned
