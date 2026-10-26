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
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_MAX_CHARS = 12_000
HARD_MAX_CHARS = 48_000
FINANCE_MAX_CHARS = 24_000
READER_MIN_RATIO = 0.35
READER_FALLBACK_MIN_CHARS = 800
READER_FALLBACK_MAX_CHARS = 4000
MAX_SOURCE_LINKS = 60
TABLE_MIN_CHARS = 40
TABLE_OMISSION_MARKER = (
    "\n\n[table mode: non-table context omitted; use reader mode for narrative]"
)
FALLBACK_MARKER = "\n\n[reader low coverage; tag-strip fallback used]"
TRUNCATION_MARKER = (
    "\n\n[content truncated; raise max_chars or request the source URL for more]"
)

PAGE_TYPE_BUDGETS: dict[str, int] = {
    "article": 24_000,
    "news": 12_000,
    "blog": 12_000,
    "docs": 12_000,
    "tutorial": 40_000,
    "thread": 16_000,
    "paper": 24_000,
    "pdf": 24_000,
    "table": 24_000,
    "product": 12_000,
    "listing": 8_000,
    "spa": 12_000,
    "paywall": 2_000,
    "challenge": 2_000,
    "unknown": DEFAULT_MAX_CHARS,
}


def _budget_overrides() -> dict[str, int]:
    raw = os.environ.get("READER_BUDGET_OVERRIDES", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            out[str(key).lower()] = int(value)
        except (TypeError, ValueError):
            continue
    return out


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(
    r"<(script|style|noscript|template|svg|canvas)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_ZW_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
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
    r"(?:cf-challenge|challenge-form|cf_chl|g-recaptcha|h-captcha|hcaptcha)"
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


_PAYWALL_STRUCTURAL_RE = re.compile(
    r"(?:id|class)\s*=\s*[\"'][^\"']*"
    r"(?:paywall|regwall|subscribe-wall|subscription-wall|consent-wall|login-wall)"
    r"[^\"']*[\"']",
    re.IGNORECASE,
)
_PAYWALL_PHRASES = (
    "subscribe to continue",
    "subscribe for unlimited access",
    "create a free account to continue",
    "log in to continue",
    "sign in to continue",
    "already a subscriber",
    "this content is for subscribers",
)
_SPA_RE = re.compile(
    r"(?:id=[\"']root[\"']|__NEXT_DATA__|ng-app|data-reactroot|id=[\"']app[\"'])",
    re.IGNORECASE,
)
_HN_COMMENT_RE = re.compile(r"class=[\"'][^\"']*\bcomtr\b", re.IGNORECASE)
_SO_QUESTION_RE = re.compile(r"id=[\"']question[\"']", re.IGNORECASE)
_COMMENT_CONTAINER_RE = re.compile(
    r"(?:class|data-testid)=[\"'][^\"']*(?:comment|reply)[^\"']*[\"']",
    re.IGNORECASE,
)
_LISTING_RE = re.compile(
    r"(?:search-results|results-list|class=[\"'][^\"']*\bresults\b|"
    r"class=[\"'][^\"']*listing|class=[\"'][^\"']*product-list)",
    re.IGNORECASE,
)
_PRODUCT_RE = re.compile(
    r"(?:class|id)=[\"'][^\"']*(?:\bproduct\b|\bprice\b|\brating\b)[^\"']*[\"']",
    re.IGNORECASE,
)
_PAPER_RE = re.compile(
    r"(?:citation_title|citation_doi|class=[\"'][^\"']*\bltx_page)",
    re.IGNORECASE,
)
_TUTORIAL_RE = re.compile(
    r"(?:tutorial|getting started|step-by-step|how to|learn )",
    re.IGNORECASE,
)
_NEWS_RE = re.compile(
    r"(?:NewsArticle|article:published_time|press-release|class=[\"'][^\"']*\bnews\b)",
    re.IGNORECASE,
)
_BLOG_RE = re.compile(
    r"(?:BlogPosting|class=[\"'][^\"']*\bblog\b|/blog/)",
    re.IGNORECASE,
)
_ARTICLE_RE = re.compile(r"<article\b|<main\b", re.IGNORECASE)
_TABLE_RE = re.compile(r"<table\b", re.IGNORECASE)
_CODE_RE = re.compile(r"<(?:pre|code)\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"<h[23]\b", re.IGNORECASE)


def detect_paywall_html(html) -> bool:
    """Detect a blocking paywall/registration wall, not an article about one."""
    source = _str_from_any(html)
    if not source.strip():
        return False
    head = source[:80_000]
    structural = bool(_PAYWALL_STRUCTURAL_RE.search(head))
    text = _strip_tags(head).lower()
    phrase_hits = sum(1 for phrase in _PAYWALL_PHRASES if phrase in text)
    if structural and (phrase_hits >= 1 or len(text) < 1200):
        return True
    return phrase_hits >= 2 and len(text) < 1500


def _table_text_ratio(source: str) -> float:
    blocks = re.findall(r"<table\b.*?</table>", source, re.IGNORECASE | re.DOTALL)
    if not blocks:
        return 0.0
    table_text = _strip_tags("\n".join(blocks))
    page_text = _strip_tags(source)
    return len(table_text) / max(1, len(page_text))


def detect_page_type(html, url: str = "", text: str | None = None) -> str:
    """Heuristic page type for budgets/routing; conservative, no ML."""
    source = _str_from_any(html)
    url_lower = (url or "").lower()
    if url_lower.endswith(".pdf") or "/pdf/" in url_lower:
        return "pdf"
    if not source.strip():
        return "unknown"
    head = source[:120_000]
    plain = text if text is not None else _strip_tags(head)
    lowered = head.lower()

    if detect_challenge_html(source):
        return "challenge"
    if detect_paywall_html(source):
        return "paywall"
    if _is_xbrl_document(source):
        return "table"
    if (
        "arxiv.org" in url_lower
        or "doi.org" in url_lower
        or re.search(
            r"(?:citation_title|citation_doi|class=[\"'][^\"']*ltx_page)",
            head,
            re.IGNORECASE,
        )
    ):
        return "paper"
    if re.search(r"github\.com/[^/]+/[^/]+/(?:issues|pull)/", url_lower):
        return "thread"
    if re.search(r"github\.com/[^/]+/[^/]+/?$", url_lower):
        return "docs"
    if len(plain) < 600 and _SPA_RE.search(head):
        return "spa"
    if (
        _HN_COMMENT_RE.search(head)
        or _SO_QUESTION_RE.search(head)
        or len(
            re.findall(
                r"data-testid=[\"'][^\"']*(?:comment|reply)", head, re.IGNORECASE
            )
        )
        >= 4
    ):
        return "thread"
    if _LISTING_RE.search(head) and (
        head.count("<li") >= 3
        or len(re.findall(r"class=[\"'][^\"']*results", head, re.IGNORECASE)) >= 1
    ):
        return "listing"
    product_marker = _PRODUCT_RE.search(head)
    if product_marker and (
        re.search(r"\$\s?\d", head)
        or "add to cart" in lowered
        or "out of 5" in lowered
        or "customer reviews" in lowered
    ):
        return "product"
    tables = _TABLE_RE.findall(source)
    if tables:
        rows = source.count("<tr")
        numeric = len(re.findall(r"<t[dh][^>]*>[^<]*\d[^<]*</t[dh]>", source))
        if (rows >= 8 or numeric >= 6) and _table_text_ratio(source) >= 0.30:
            return "table"
    if "mw-content-text" in head or "mw-parser-output" in head:
        return "article"
    code = len(_CODE_RE.findall(head))
    headings = len(_HEADING_RE.findall(head))
    if code >= 3 and (_TUTORIAL_RE.search(head) or "tutorial" in url_lower):
        return "tutorial"
    if headings >= 5 and code >= 2:
        return "docs"
    if _BLOG_RE.search(head) or "blog" in url_lower:
        return "blog"
    if _NEWS_RE.search(head) or "news" in url_lower:
        return "news"
    if _ARTICLE_RE.search(head):
        return "article"
    return "unknown"


@dataclass(frozen=True)
class ReaderConfig:
    """Tunable trafilatura/extraction options (defaults preserve behavior)."""

    favor_recall: bool = True
    favor_precision: bool = False
    include_tables: bool = True
    include_comments: bool = False
    include_formatting: bool = True
    include_links: bool = True
    deduplicate: bool = False


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
    reason: str = ""
    page_type: str = "unknown"
    paywall: bool = False


def _str_from_any(value) -> str:
    """Coerce bytes/Response-like input to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return str(value)


def _clean_canonical(url: str) -> str:
    """Drop common tracking parameters from the header URL only."""
    try:
        parts = urlsplit(url)
        query = [
            (k, v)
            for k, v in (
                item.split("=", 1) if "=" in item else (item, "")
                for item in parts.query.split("&")
                if item
            )
            if not (
                k.lower().startswith("utm_")
                or k.lower() in {"fbclid", "gclid", "mc_cid", "mc_eid"}
            )
        ]
        from urllib.parse import urlencode

        return parts._replace(query=urlencode(query)).geturl()
    except ValueError:
        return url


def _text_of(nodes) -> str:
    parts = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(str(node))
        else:
            parts.append(" ".join(node.itertext()))
    return " ".join(parts).strip()


def _header_block(source: str, url: str) -> str:
    """Title/h1/meta-description/canonical context, a few tokens per page."""
    try:
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(source, parser=lxml_html.HTMLParser(recover=True))
    except Exception:  # noqa: BLE001 - best-effort context
        return ""
    title = _text_of(doc.xpath("//title"))
    if not title:
        title = _text_of(doc.xpath("//meta[@property='og:title']/@content"))
    h1 = _text_of(doc.xpath("//h1"))
    desc = _text_of(
        doc.xpath(
            "//meta[@name='description']/@content | "
            "//meta[@property='og:description']/@content"
        )
    )
    canonical = _text_of(doc.xpath("//link[@rel='canonical']/@href")) or url
    title = re.sub(r"\s+", " ", html_lib.unescape(title)).strip()[:200]
    h1 = re.sub(r"\s+", " ", html_lib.unescape(h1)).strip()[:200]
    desc = re.sub(r"\s+", " ", html_lib.unescape(desc)).strip()[:300]
    canonical = _clean_canonical(canonical.strip()) if canonical else ""
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
    if h1 and h1.lower() != title.lower():
        lines.append(f"## {h1}")
    if desc and desc.lower() not in {title.lower(), h1.lower()}:
        lines.append(f"> {desc}")
    if canonical:
        lines.append(f"Source: {canonical}")
    return "\n\n".join(lines)


def strip_hidden_html(source: str) -> str:
    """Remove clearly hidden nodes and HTML comments before extraction.

    Screen-reader-only text is kept; only ``hidden``, ``aria-hidden=true`` and
    inline display/visibility hiding are removed.
    """
    try:
        from lxml import etree
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(
            source, parser=lxml_html.HTMLParser(recover=True, no_network=True)
        )
    except Exception:  # noqa: BLE001 - malformed HTML: let the extractor try
        return source
    for node in doc.xpath(
        "//*[@hidden] | //*[@aria-hidden='true' or @aria-hidden='True']"
    ):
        node.drop_tree()
    for node in doc.xpath("//*[@style]"):
        style = (node.get("style") or "").lower().replace(" ", "")
        if "display:none" in style or "visibility:hidden" in style:
            node.drop_tree()
    for comment in doc.xpath("//comment()"):
        parent = comment.getparent()
        if parent is not None:
            parent.remove(comment)
    try:
        return etree.tostring(doc, encoding="unicode")
    except Exception:  # noqa: BLE001
        return source


def _dedupe_leading_heading(body: str, header: str) -> str:
    """Drop a body heading that the context header already provides."""
    headings = {
        line.lstrip("#").strip().lower()
        for line in header.splitlines()
        if line.startswith("#")
    }
    stripped = body.lstrip()
    first, _, rest = stripped.partition("\n")
    if first.startswith("#") and first.lstrip("#").strip().lower() in headings:
        return rest.lstrip()
    return body


def _strip_tags(raw: str) -> str:
    text = _SCRIPT_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return _tidy(_WS_RE.sub(" ", text))


def _tidy(text: str) -> str:
    text = _ZW_RE.sub("", text)
    lines = [line.rstrip() for line in text.splitlines()]
    text = _BLANKLINES_RE.sub("\n\n", "\n".join(lines))
    return text.strip()


def audit_host(url: str) -> str:
    """Return the lowercase hostname for a URL (empty when unparseable)."""
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def domain_budget(url: str, page_type: str | None = None) -> int:
    """Compatibility helper: page-type ceiling, optionally overridden by host."""
    return content_budget(url, page_type=page_type)


def content_budget(
    url: str,
    requested: int | None = None,
    page_type: str | None = None,
) -> int:
    """Resolve the effective character budget (a ceiling, not a target).

    The ceiling comes from the page type; ``READER_BUDGET_OVERRIDES`` is a
    deployment escape hatch keyed by host suffix. An explicit ``requested``
    value is honoured up to the ceiling and the hard maximum.
    """
    cap = PAGE_TYPE_BUDGETS.get((page_type or "unknown").lower(), DEFAULT_MAX_CHARS)
    host = audit_host(url)
    for suffix, value in _budget_overrides().items():
        if host == suffix or host.endswith("." + suffix):
            cap = value
            break
    cap = max(0, min(cap, HARD_MAX_CHARS))
    if requested is None:
        return cap
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return cap
    if value <= 0:
        return cap
    return min(value, cap, HARD_MAX_CHARS)


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


def _rows_to_markdown(rows: list[str]) -> str:
    if not rows:
        return ""
    header = [cell.strip() for cell in rows[0].split(" | ")]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        cells = [cell.strip() for cell in row.split(" | ")]
        cells = (cells + [""] * len(header))[: len(header)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


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
        text = _rows_to_markdown(rows)
        if len(text) >= TABLE_MIN_CHARS:
            candidates.append((numeric, len(text), text))

    candidates.sort(reverse=True)
    return "\n\n".join(item[2] for item in candidates[:3])


def _extract_markdown(
    source: str,
    url: str,
    include_links: bool,
    config: ReaderConfig | None = None,
) -> str:
    cfg = config or ReaderConfig()
    try:
        import trafilatura

        return _tidy(
            trafilatura.extract(
                source,
                url=url or None,
                output_format="markdown",
                include_links=include_links and cfg.include_links,
                include_tables=cfg.include_tables,
                include_formatting=cfg.include_formatting,
                include_images=False,
                include_comments=cfg.include_comments,
                favor_recall=cfg.favor_recall,
                favor_precision=cfg.favor_precision,
                # trafilatura 2.3.x deduplicate=True keeps cross-call state
                # and starts returning empty output after a few extractions
                # of the same page; that silently forced tag-strip fallback.
                deduplicate=cfg.deduplicate,
            )
            or ""
        )
    except Exception:  # noqa: BLE001 - best-effort: callers fall back
        return ""


def _compact_links(
    markdown: str, mode: str, max_sources: int
) -> tuple[str, list[str], int]:
    if mode == "inline" or not markdown:
        return markdown, [], 0

    sources: list[str] = []
    seen: set[str] = set()
    dropped = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal dropped
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        raw_url = match.group(2).strip()
        if raw_url.startswith("<") and raw_url.endswith(">"):
            raw_url = raw_url[1:-1].strip()
        scheme = urlsplit(raw_url).scheme.lower()
        if mode == "sources" and scheme in {"http", "https"} and raw_url not in seen:
            seen.add(raw_url)
            if len(sources) < max_sources:
                sources.append(raw_url)
            else:
                dropped += 1
        return label or raw_url

    return _tidy(_MD_LINK_RE.sub(replace, markdown)), sources, dropped


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


def extract_pdf(data, max_chars: int | None = DEFAULT_MAX_CHARS) -> ReaderResult:
    """Extract text from a PDF with page markers; clean failure modes."""
    import io

    try:
        from pypdf import PdfReader
    except ImportError:
        return ReaderResult(
            text="[pdf support unavailable: pypdf is not installed]",
            method="pdf",
            reason="pdf_empty",
            page_type="pdf",
        )
    try:
        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                unlocked = reader.decrypt("")
            except Exception:  # noqa: BLE001 - password may be required
                unlocked = 0
            if not unlocked:
                return ReaderResult(
                    text="[pdf encrypted: password required; not loaded]",
                    method="pdf",
                    reason="pdf_empty",
                    page_type="pdf",
                )
        pages = []
        for index, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - one bad page should not kill the file
                text = ""
            if text.strip():
                pages.append(f"[page {index}]\n{text.strip()}")
        total = len(reader.pages)
    except Exception as exc:  # noqa: BLE001 - corrupt/unsupported PDF
        return ReaderResult(
            text=f"[pdf could not be read: {type(exc).__name__}]",
            method="pdf",
            reason="pdf_empty",
            page_type="pdf",
        )
    if not pages:
        return ReaderResult(
            text=f"[pdf has no extractable text; OCR is not supported] (pages={total})",
            method="pdf",
            reason="pdf_empty",
            page_type="pdf",
        )
    body = "\n\n".join(pages)
    if total > len([p for p in pages if p]):
        body += f"\n\n[pages with text: {len(pages)} of {total}]"
    text, truncated = _truncate(body, "", max_chars)
    return ReaderResult(
        text=text,
        method="pdf",
        truncated=truncated,
        reason="pdf_text",
        page_type="pdf",
    )


LOW_SIGNAL_RE = re.compile(
    r"^(?:\+1|thanks(?:!| you)?|thank you|this|lol|nice|agreed|same|\.)$",
    re.IGNORECASE,
)


def _thread_text(node) -> str:
    text = _tidy(node.text_content())
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def _extract_thread(source: str, url: str, max_comments: int = 200) -> str:
    """Generic + HN + Stack Exchange thread extraction.

    Returns Markdown with author/order/depth when available; returns "" when
    the structure is not confident so callers can fall back to reader mode.
    """
    try:
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(
            source, parser=lxml_html.HTMLParser(recover=True, no_network=True)
        )
    except Exception:  # noqa: BLE001 - best effort
        return ""

    entries: list[tuple[int, str, str, str]] = []  # depth, author, time, text
    hn = doc.xpath(
        "//tr[contains(concat(' ', normalize-space(@class), ' '), ' comtr ')]"
    )
    hn_meta = ""
    if hn:
        titlelink = doc.xpath("//a[contains(@class,'titlelink')]")
        if titlelink:
            hn_title = _text_of(titlelink[:1])
        subtext = doc.xpath("//td[contains(@class,'subtext')]")
        if subtext:
            hn_meta = " ".join(subtext[0].text_content().split())
        for index, row in enumerate(hn[:max_comments]):
            author = _text_of(row.xpath(".//a[contains(@class,'hnuser')]"))
            when = _text_of(row.xpath(".//span[contains(@class,'age')]"))
            body = row.xpath(".//*[contains(@class,'commtext')]")
            text = _thread_text(body[0]) if body else ""
            indent = row.xpath(".//td[contains(@class,'ind')]//img/@width")
            try:
                depth = int(indent[0]) // 40 if indent else 0
            except (TypeError, ValueError):
                depth = 0
            entries.append((depth, author, when, text))
    else:
        question = doc.xpath("//*[@id='question']")
        answers = doc.xpath("//*[contains(@class,'answer')]")
        if question or answers:
            for index, node in enumerate((question + answers)[:max_comments]):
                author = _text_of(
                    node.xpath(
                        ".//*[contains(@class,'user-details')]//a | .//*[contains(@class,'author')]"
                    )
                )
                when = _text_of(node.xpath(".//time | .//*[contains(@class,'time')]"))
                body = node.xpath(
                    ".//*[contains(@class,'question-body')] | .//*[contains(@class,'answer-body')]"
                )
                text = _thread_text(body[0]) if body else _thread_text(node)
                entries.append((0, author, when, text))
        else:
            candidates = doc.xpath(
                "//*[@data-testid='comment'] | //*[contains(@class,'comment-body')] | "
                "//*[contains(@class,'comment')]"
            )
            seen: set[str] = set()
            for node in candidates:
                text = _thread_text(node)
                if not text or text in seen:
                    continue
                seen.add(text)
                author = _text_of(
                    node.xpath(
                        ".//*[contains(@class,'author')] | .//a[contains(@class,'user')]"
                    )
                )
                when = _text_of(node.xpath(".//time"))
                entries.append((0, author, when, text))

    if not entries:
        return ""

    title = _text_of(doc.xpath("//h1")) or _text_of(doc.xpath("//title"))
    if hn:
        title = locals().get("hn_title") or title
    lines = [f"## Thread: {title}".strip()]
    if hn_meta:
        lines.append(f"> {hn_meta}")
    dropped = 0
    kept = 0
    for depth, author, when, text in entries:
        lowered = " ".join(text.split()).lower()
        if not text or lowered in {"[deleted]", "[removed]"} or "deleted" == lowered:
            dropped += 1
            continue
        if len(text) < 15 or LOW_SIGNAL_RE.match(lowered):
            dropped += 1
            continue
        prefix = "  " * min(depth, 8)
        meta = " ".join(part for part in (author, when) if part)
        head = f"{prefix}- " + (f"@{meta}: " if meta else "")
        lines.append(head + text.replace("\n", " ").strip())
        kept += 1
    if dropped:
        lines.append(f"\n[{dropped} low-signal/deleted comments collapsed]")
    if len(entries) >= max_comments:
        lines.append(f"\n[{len(entries)} comments capped]")
    return "\n".join(lines)


def _outline_text(full: str, max_chars: int | None) -> str:
    head_limit = 2000 if not max_chars else max(200, min(2000, max_chars // 3))
    head = full[:head_limit].rstrip()
    headings = [
        (match.start(), match.group(0))
        for match in re.finditer(r"^#{1,6} .+$", full, re.MULTILINE)
    ]
    lines = [head, "", "[outline]"]
    for offset, heading in headings[:80]:
        lines.append(f"{heading} @{offset}")
    if not headings:
        return _truncate(full, "", max_chars)[0]
    return _truncate("\n".join(lines), "", max_chars)[0]


def _section_text(
    full: str, offset: int, length: int | None, max_chars: int | None
) -> str:
    start = max(0, int(offset))
    size = int(length) if length else (max_chars or 12000)
    size = max(200, size)
    chunk = full[start : start + size]
    marker = f"\n\n[section offset={start} length={len(chunk)} of {len(full)}]"
    return _truncate(chunk + marker, "", max_chars)[0]


def _query_excerpt(full: str, query: str, max_chars: int | None) -> str:
    terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 1}
    if not terms:
        return _truncate(full, "", max_chars)[0]
    paragraphs = re.split(r"\n{2,}", full)
    scored = []
    for index, paragraph in enumerate(paragraphs):
        words = set(re.findall(r"[a-z0-9]+", paragraph.lower()))
        score = len(words & terms)
        if score:
            scored.append((score, index, paragraph))
    selected = sorted(scored, reverse=True)[:20]
    selected.sort(key=lambda item: item[1])
    body = "\n\n".join(item[2] for item in selected)
    if not body:
        return _truncate(full, "", max_chars)[0]
    prefix = f"[query excerpt: {query}]\n\n"
    return _truncate(prefix + body, "", max_chars)[0]


def read_html(
    html,
    url: str = "",
    max_chars: int | None = DEFAULT_MAX_CHARS,
    *,
    include_links: str = "sources",
    config: ReaderConfig | None = None,
    mode: str = "full",
    offset: int = 0,
    length: int | None = None,
    query: str | None = None,
) -> ReaderResult:
    """Extract reader-mode Markdown and report what was done.

    ``include_links`` is one of ``sources`` (default), ``inline`` or ``none``.
    ``mode`` adds opt-in progressive views: ``outline`` (headings + first N
    chars), ``section`` (offset/length) and ``query`` (query-focused excerpt).
    The default remains ``full``. Never raises for malformed input.
    """
    source = _str_from_any(html)
    page_type = detect_page_type(source, url)
    if os.environ.get("LOADER_VARIANT", "new").lower() == "legacy":
        text, truncated = _truncate(
            _strip_tags(source), "", max_chars if max_chars is not None else 12000
        )
        return ReaderResult(
            text=text,
            method="legacy-tag-strip",
            tag_chars=len(_strip_tags(source)),
            truncated=truncated,
            reason="legacy",
            page_type=page_type,
        )
    if not source.strip():
        return ReaderResult(text="", method="empty", reason="reader_empty")

    if page_type == "challenge":
        return ReaderResult(
            text="",
            method="challenge",
            challenge=True,
            reason="challenge_needs_human",
            page_type="challenge",
        )

    if page_type == "paywall":
        return ReaderResult(
            text="[paywall] Paywall or login wall detected; subscribe or sign in to read the page.",
            method="paywall",
            reason="paywall",
            page_type="paywall",
            paywall=True,
        )

    source = strip_hidden_html(source)
    page_type = detect_page_type(source, url) if page_type == "unknown" else page_type

    if page_type == "thread":
        thread_text = _extract_thread(source, url)
        if thread_text:
            header = _header_block(source, url)
            body = (header + "\n\n" if header else "") + thread_text
            text, truncated = _truncate(body, "", max_chars)
            return ReaderResult(
                text=text,
                method="thread",
                truncated=truncated,
                reason="structured_mode",
                page_type="thread",
            )

    if page_type == "table" and _is_xbrl_document(source):
        tables = _extract_tables(source)
        if len(tables) >= TABLE_MIN_CHARS:
            header = _header_block(source, url)
            body = (header + "\n\n" if header else "") + tables + TABLE_OMISSION_MARKER
            text, truncated = _truncate(body, "", max_chars)
            return ReaderResult(
                text=text,
                method="table",
                tag_chars=len(_strip_tags(source)),
                truncated=truncated,
                reason="structured_mode",
                page_type=page_type,
            )

    tag_text = _strip_tags(source)
    link_mode = (
        include_links if include_links in {"sources", "inline", "none"} else "sources"
    )
    reader_text = _extract_markdown(
        source, url, include_links=link_mode != "none", config=config
    )
    method = "reader"

    too_small = bool(
        reader_text
        and len(tag_text) >= READER_FALLBACK_MIN_CHARS
        and len(reader_text) < READER_MIN_RATIO * len(tag_text)
        and len(reader_text) < READER_FALLBACK_MAX_CHARS
    )
    dropped_links = 0
    if not reader_text or too_small:
        method = "tag-strip"
        reason = "reader_empty" if not reader_text else "fallback_low_coverage"
        tables = _extract_tables(source)
        table_dominates = len(tag_text) > 0 and len(tables) >= 0.6 * len(tag_text)
        if len(tables) >= TABLE_MIN_CHARS and (page_type == "table" or table_dominates):
            method = "table"
            reason = "structured_mode"
            body, sources = tables, []
        else:
            body, sources = tag_text, []
    else:
        reason = "reader_ok"
        source_cap = (
            MAX_SOURCE_LINKS
            if not max_chars
            else min(MAX_SOURCE_LINKS, max(8, max_chars // 600))
        )
        body, sources, dropped_links = _compact_links(
            reader_text, link_mode, source_cap
        )

    sources_block = ""
    if sources:
        sources_block = "\n\nSources:\n" + "\n".join(f"- {item}" for item in sources)
        if dropped_links:
            sources_block += (
                f"\n\n[{dropped_links} source links omitted by the link cap]"
            )
    header = _header_block(source, url)
    if method == "tag-strip":
        body += FALLBACK_MARKER
    if header:
        body = header + "\n\n" + _dedupe_leading_heading(body, header)

    full = body + sources_block
    if mode == "outline":
        text, truncated = _outline_text(full, max_chars), True
    elif mode == "section":
        text, truncated = _section_text(full, offset, length, max_chars), True
    elif mode == "query" and query:
        text, truncated = _query_excerpt(full, query, max_chars), True
    else:
        text, truncated = _truncate(body, sources_block, max_chars)
    return ReaderResult(
        text=text,
        method=method,
        reader_chars=len(reader_text),
        tag_chars=len(tag_text),
        truncated=truncated,
        source_count=len(sources),
        reason=reason,
        page_type=page_type,
    )


def html_to_reader(
    html,
    url: str = "",
    max_chars: int | None = DEFAULT_MAX_CHARS,
    *,
    include_links: str = "sources",
    config: ReaderConfig | None = None,
) -> str:
    """Return just the extracted text (backwards-compatible helper)."""
    return read_html(
        html, url, max_chars, include_links=include_links, config=config
    ).text
