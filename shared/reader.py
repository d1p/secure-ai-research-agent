"""Reader-mode extraction for fetched HTML.

Turns a full HTML document into clean Markdown containing the main content
(title, body text, links, tables) using trafilatura.  Falls back to a
conservative tag-strip when readability extraction yields nothing *or* when
it drops too much of the page (data-heavy sites such as SEC/StockAnalysis).

Link policy defaults to ``sources``: link labels stay in the body, but unique
external URLs are appended once under ``Sources:``.  This removes the citation
URL bloat that made raw reader output expensive while keeping citations.

Goal: maximise useful information per token, not merely shrink the output.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_MAX_CHARS = 12_000
HARD_MAX_CHARS = 32_000
FINANCE_MAX_CHARS = 24_000
READER_MIN_RATIO = 0.35
READER_FALLBACK_MIN_CHARS = 800
READER_FALLBACK_MAX_CHARS = 4000
MAX_SOURCE_LINKS = 60
TABLE_MIN_CHARS = 40
TRUNCATION_MARKER = "\n\n[content truncated]"

DOMAIN_BUDGETS: dict[str, int] = {
    "sec.gov": HARD_MAX_CHARS,
    "stockanalysis.com": FINANCE_MAX_CHARS,
    "finance.yahoo.com": FINANCE_MAX_CHARS,
    "macrotrends.net": FINANCE_MAX_CHARS,
    "barchart.com": FINANCE_MAX_CHARS,
    "marketwatch.com": FINANCE_MAX_CHARS,
    "bloomberg.com": FINANCE_MAX_CHARS,
    "reuters.com": FINANCE_MAX_CHARS,
}

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(
    r"<(script|style|noscript|template|svg|canvas)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")
_MD_LINK_RE = re.compile(
    r"\[([^\]]*)\]\(\s*(<[^>]+>|https?://[^)\s]+|[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)

_CHALLENGE_TITLE_RE = re.compile(
    r"<title[^>]*>\s*(?:just a moment|attention required|access denied|"
    r"security verification|verify you are human|checking your browser|please wait)",
    re.IGNORECASE,
)
_CHALLENGE_STRUCTURAL_RE = re.compile(
    r"(?:id|class|name)\s*=\s*[\"'][^\"']*"
    r"(?:cf-challenge|challenge-form|cf_chl|g-recaptcha|h-captcha|hcaptcha|captcha)"
    r"[^\"']*[\"']",
    re.IGNORECASE,
)
_CHALLENGE_PHRASES = (
    "performing security verification",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies",
    "complete the security check",
    "just a moment",
    "attention required",
    "are you a robot",
    "unusual traffic",
    "access denied",
    "request blocked",
    "cf-error-details",
)


@dataclass(frozen=True)
class ReaderResult:
    """Outcome of a reader-mode extraction."""

    text: str
    method: str
    challenge: bool = False
    reader_chars: int = 0
    tag_chars: int = 0
    truncated: bool = False
    source_count: int = 0


def _str_from_any(value) -> str:
    """Coerce bytes/Response-like input to str."""
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


def audit_host(url: str) -> str:
    """Return the lowercase hostname for a URL (empty when unparseable)."""
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def domain_budget(url: str) -> int:
    """Per-domain output ceiling in characters."""
    host = audit_host(url)
    for suffix, budget in DOMAIN_BUDGETS.items():
        if host == suffix or host.endswith("." + suffix):
            return budget
    return DEFAULT_MAX_CHARS


def content_budget(url: str, requested: int | None = None) -> int:
    """Resolve the effective character budget.

    ``requested`` of ``None``/``0`` means "use the per-domain default"; a
    positive value is honoured up to that domain's ceiling.
    """
    cap = domain_budget(url)
    if requested is None:
        return cap
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return cap
    if value <= 0:
        return cap
    return min(value, cap)


def detect_challenge_html(html) -> bool:
    """Detect bot-verification pages without flagging articles that mention them."""
    source = _str_from_any(html)
    if not source.strip():
        return False
    head = source[:50_000]
    if _CHALLENGE_TITLE_RE.search(head) or _CHALLENGE_STRUCTURAL_RE.search(head):
        return True
    plain = _strip_tags(head)
    return _challenge_score(plain) >= 2 or (
        _challenge_score(plain) == 1 and len(plain) < 1500
    )


def detect_challenge_text(text) -> bool:
    """Detect a challenge from already-rendered visible text."""
    plain = _str_from_any(text)
    if not plain.strip():
        return False
    score = _challenge_score(plain)
    return score >= 2 or (score == 1 and len(plain) < 1500)


def _challenge_score(text: str) -> int:
    lowered = text.lower()
    return sum(1 for phrase in _CHALLENGE_PHRASES if phrase in lowered)


def _is_xbrl_document(html) -> bool:
    """True for SEC IDEA/XBRL statement pages (R2.htm, R4.htm, ...)."""
    head = _str_from_any(html)[:20_000].lower()
    return "idea: xbrl document" in head or (
        "xbrl document" in head and "<type>xml" in head
    )


def _cell_text(cell) -> str:
    """Visible cell text with nested scripts/styles removed."""
    for bad in cell.xpath(".//script|.//style|.//noscript|.//template"):
        bad.drop_tree()
    return _WS_RE.sub(" ", cell.text_content() or "").strip()[:200]


def _table_rows(table) -> tuple[list[str], int]:
    rows: list[str] = []
    numeric = 0
    for row in table.xpath("./tr|./thead/tr|./tbody/tr")[:200]:
        cells = [_cell_text(cell) for cell in row.xpath("./th|./td")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        rows.append(" | ".join(cells))
        numeric += sum(1 for cell in cells if re.search(r"\d", cell))
    return rows, numeric


def _extract_tables(html) -> str:
    """Extract the most data-dense tables as pipe-separated text.

    This is the fallback for pages that are mostly a table (SEC XBRL filings,
    financial sites) and that trafilatura treats as non-article content.
    """
    source = _str_from_any(html)
    if not source.strip():
        return ""
    try:
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(
            source,
            parser=lxml_html.HTMLParser(recover=True, no_network=True),
        )
    except Exception:  # noqa: BLE001 - lxml is optional at runtime
        return ""

    candidates: list[tuple[int, int, str]] = []
    for table in doc.xpath("//table"):
        if table.xpath("ancestor::table"):
            continue
        rows, numeric = _table_rows(table)
        if len(rows) < 2 or numeric < 2:
            continue
        text = "\n".join(rows)
        if len(text) >= TABLE_MIN_CHARS:
            candidates.append((numeric, len(text), text))

    candidates.sort(reverse=True)
    return "\n\n".join(item[2] for item in candidates[:3])


def _extract_markdown(source: str, url: str, include_links: bool) -> str:
    try:
        import trafilatura

        return _tidy(
            trafilatura.extract(
                source,
                url=url or None,
                output_format="markdown",
                include_links=include_links,
                include_tables=True,
                include_formatting=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,
                # trafilatura 2.3.x deduplicate=True keeps cross-call state
                # and starts returning empty output after a few extractions
                # of the same page; that silently forced tag-strip fallback.
                deduplicate=False,
            )
            or ""
        )
    except Exception:  # noqa: BLE001 - best-effort: callers fall back
        return ""


def _compact_links(markdown: str, mode: str, max_sources: int) -> tuple[str, list[str]]:
    if mode == "inline" or not markdown:
        return markdown, []

    sources: list[str] = []
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        raw_url = match.group(2).strip()
        if raw_url.startswith("<") and raw_url.endswith(">"):
            raw_url = raw_url[1:-1].strip()
        scheme = urlsplit(raw_url).scheme.lower()
        if (
            mode == "sources"
            and scheme in {"http", "https"}
            and raw_url not in seen
            and len(sources) < max_sources
        ):
            seen.add(raw_url)
            sources.append(raw_url)
        return label or raw_url

    return _tidy(_MD_LINK_RE.sub(replace, markdown)), sources


def _truncate(body: str, sources_block: str, max_chars: int | None) -> tuple[str, bool]:
    if not max_chars or max_chars <= 0:
        return body + sources_block, False
    if len(body) + len(sources_block) <= max_chars:
        return body + sources_block, False

    body_budget = max_chars - len(sources_block)
    if body_budget >= 200:
        return (
            body[:body_budget].rstrip() + TRUNCATION_MARKER + sources_block,
            True,
        )
    return (body + sources_block)[:max_chars] + TRUNCATION_MARKER, True


def read_html(
    html,
    url: str = "",
    max_chars: int | None = DEFAULT_MAX_CHARS,
    *,
    include_links: str = "sources",
) -> ReaderResult:
    """Extract reader-mode Markdown and report what was done.

    ``include_links`` is one of ``sources`` (default), ``inline`` or ``none``.
    Never raises for malformed input or a missing trafilatura install.
    """
    source = _str_from_any(html)
    if not source.strip():
        return ReaderResult(text="", method="empty")

    if detect_challenge_html(source):
        return ReaderResult(text="", method="challenge", challenge=True)

    if _is_xbrl_document(source):
        tables = _extract_tables(source)
        if len(tables) >= TABLE_MIN_CHARS:
            text, truncated = _truncate(tables, "", max_chars)
            return ReaderResult(
                text=text,
                method="table",
                tag_chars=len(_strip_tags(source)),
                truncated=truncated,
            )

    tag_text = _strip_tags(source)
    mode = include_links if include_links in {"sources", "inline", "none"} else "sources"
    reader_text = _extract_markdown(source, url, include_links=mode != "none")
    method = "reader"

    too_small = bool(
        reader_text
        and len(tag_text) >= READER_FALLBACK_MIN_CHARS
        and len(reader_text) < READER_MIN_RATIO * len(tag_text)
        and len(reader_text) < READER_FALLBACK_MAX_CHARS
    )
    if not reader_text or too_small:
        method = "tag-strip"
        tables = _extract_tables(source)
        if len(tables) >= TABLE_MIN_CHARS and len(tables) >= len(reader_text):
            method = "table"
            body, sources = tables, []
        else:
            body, sources = tag_text, []
    else:
        source_cap = MAX_SOURCE_LINKS if not max_chars else min(
            MAX_SOURCE_LINKS, max(8, max_chars // 600)
        )
        body, sources = _compact_links(reader_text, mode, source_cap)

    sources_block = ""
    if sources:
        sources_block = "\n\nSources:\n" + "\n".join(f"- {item}" for item in sources)

    text, truncated = _truncate(body, sources_block, max_chars)
    return ReaderResult(
        text=text,
        method=method,
        reader_chars=len(reader_text),
        tag_chars=len(tag_text),
        truncated=truncated,
        source_count=len(sources),
    )


def html_to_reader(
    html,
    url: str = "",
    max_chars: int | None = DEFAULT_MAX_CHARS,
    *,
    include_links: str = "sources",
) -> str:
    """Return just the extracted text (backwards-compatible helper)."""
    return read_html(html, url, max_chars, include_links=include_links).text
