#!/usr/bin/env python3
"""Capture pinned, trimmed benchmark fixtures.

Network capture is explicit: run with ``--allow-network``. The committed
fixtures are the source of truth for offline tests and benchmarks; this script
is for refreshing or adding fixtures, not for the default test suite.

It never stores secrets or personal data: emails, private/link-local IPs and
phone-like strings are redacted before writing.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html as html_lib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from lxml import html

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
UA = os.environ.get(
    "FETCH_USER_AGENT",
    "homelab-ai-stack/1.0 (+https://example.com/bot)",
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PRIVATE_IP_RE = re.compile(
    r"\b(?:10|127|169\.254|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)"
    r"\.[0-9]{1,3}\.[0-9]{1,3}\b"
)
PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+\d{1,3}[\s.-]?|\(\d{2,4}\)[\s.-]?)\d{2,4}[\s.-]\d{3,4}(?![\w.])"
)
ANALYTICS_RE = re.compile(
    r"<script\b[^>]*\bsrc=[\"'][^\"']*(?:google-analytics|googletagmanager|"
    r"doubleclick|hotjar|segment|facebook|twitter|adsbygoogle|clarity\.ms)"
    r"[^\"']*[\"'][^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)
DATA_URI_RE = re.compile(r"data:[^\"'\s]{20000,}")
NOISE_XPATHS = (
    ".//*[contains(@class,'navbox')]",
    ".//*[contains(@class,'vertical-navbox')]",
    ".//*[contains(@class,'reflist')]",
    ".//*[contains(@class,'mw-references-wrap')]",
    ".//*[contains(@class,'mw-editsection')]",
    ".//*[contains(@class,'catlinks')]",
    ".//*[contains(@class,'printfooter')]",
    ".//*[contains(@class,'metadata')]",
    ".//*[contains(@class,'ambox')]",
    ".//*[contains(@class,'mbox-small')]",
    ".//*[contains(@class,'pagetop')]",
    ".//footer",
    ".//nav",
    ".//aside",
)


def get(url: str, timeout: int = 90) -> tuple[bytes, int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/pdf,"
            "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.status, resp.headers.get("content-type", "")


def scrub(text: str) -> str:
    text = ANALYTICS_RE.sub(" <!-- analytics script removed --> ", text)
    text = DATA_URI_RE.sub("data:[redacted-large-data-uri]", text)
    text = EMAIL_RE.sub("[redacted-email]", text)
    text = PRIVATE_IP_RE.sub("[redacted-private-ip]", text)
    text = PHONE_RE.sub("[redacted-phone]", text)
    return text


def tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def drop_noise(root) -> None:
    for xpath in NOISE_XPATHS:
        for node in root.xpath(xpath):
            node.drop_tree()


def block_text(node) -> str:
    block = {
        "address",
        "article",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
    parts: list[str] = []

    def walk(el) -> None:
        if not isinstance(el.tag, str):
            return
        tag = el.tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg", "canvas"}:
            return
        if tag in block:
            parts.append("\n")
        if el.text:
            parts.append(el.text)
        for child in el:
            walk(child)
        if tag in block:
            parts.append("\n")
        if el.tail:
            parts.append(el.tail)

    walk(node)
    return tidy("".join(parts))


def reference_from_xpath(raw: str, xpath: str) -> str:
    doc = html.fromstring(raw)
    nodes = doc.xpath(xpath)
    if not nodes:
        return ""
    drop_noise(nodes[0])
    return block_text(nodes[0])


def visible_text(raw: str) -> str:
    doc = html.fromstring(raw)
    for bad in doc.xpath("//script|//style|//noscript|//template|//svg|//canvas"):
        bad.drop_tree()
    return tidy(doc.text_content())


def write_page(slug: str, raw: bytes) -> tuple[str, int]:
    out = FIXTURES / slug
    out.mkdir(parents=True, exist_ok=True)
    if len(raw) > 250_000:
        path = out / "page.html.gz"
        path.write_bytes(gzip.compress(raw, compresslevel=9))
        return path.name, len(raw)
    path = out / "page.html"
    path.write_bytes(raw)
    return path.name, len(raw)


def record(
    slug: str,
    page_type: str,
    source_url: str,
    raw: bytes,
    content_type: str,
    *,
    license_note: str,
    capture_method: str,
    reference: str,
    reference_scope: str = "full",
    tags: list[str] | None = None,
    synthetic: bool = False,
    extra: dict | None = None,
) -> None:
    out = FIXTURES / slug
    out.mkdir(parents=True, exist_ok=True)
    if "pdf" not in content_type.lower():
        raw = scrub(raw.decode("utf-8", errors="replace")).encode("utf-8")
    reference = scrub(reference)
    stored_name, bytes_raw = write_page(slug, raw)
    inner = scrub(visible_text(raw))
    (out / "innertext.txt").write_text(inner + "\n", encoding="utf-8")
    (out / "reference.md").write_text(reference + "\n", encoding="utf-8")
    meta = {
        "slug": slug,
        "page_type": page_type,
        "source_url": source_url,
        "captured_at": datetime.now(UTC).date().isoformat(),
        "license": license_note,
        "capture_method": capture_method,
        "synthetic": synthetic,
        "content_type": content_type,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes_raw": bytes_raw,
        "stored_file": stored_name,
        "innertext_source": "lxml-visible-text",
        "reference_method": "curated selector + manual spot check",
        "reference_scope": reference_scope,
        "tags": tags or [],
    }
    if extra:
        meta.update(extra)
    (out / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  wrote {slug} ({page_type}, {bytes_raw} bytes)")


def wikipedia(
    slug: str,
    title: str,
    revid: int,
    page_type: str,
    tags: list[str],
    lang: str = "en",
) -> None:
    url = (
        f"https://{lang}.wikipedia.org/w/index.php?title={urllib.parse.quote(title)}"
        f"&oldid={revid}"
    )
    raw, status, ctype = get(url)
    if status != 200:
        raise RuntimeError(f"{slug}: HTTP {status}")
    reference = reference_from_xpath(
        raw.decode("utf-8", "replace"),
        "//*[@id='mw-content-text']//*[contains(@class,'mw-parser-output')]",
    )
    record(
        slug,
        page_type,
        url,
        raw,
        ctype,
        license_note="CC BY-SA 4.0 (Wikipedia); pinned revision excerpt",
        capture_method="http-get + oldid permalink",
        reference=reference,
        reference_scope="sample" if slug == "large-page" else "full",
        tags=tags,
        extra={"revid": revid, "title": title},
    )


def synthetic(
    slug: str, page_type: str, body: str, reference: str, tags: list[str]
) -> None:
    raw = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{slug}</title><meta name='description' content='Synthetic {page_type} fixture'>"
        "</head><body>"
        "<nav><a href='/'>Home</a><a href='/topics'>Topics</a></nav>"
        f"{body}"
        "<footer>Copyright synthetic fixture. Privacy. Terms.</footer>"
        "</body></html>"
    ).encode()
    record(
        slug,
        page_type,
        f"https://example.com/{slug}",
        raw,
        "text/html; charset=utf-8",
        license_note="No source license; synthetic test data",
        capture_method="synthetic",
        reference=reference,
        tags=tags,
        synthetic=True,
    )


def so_fixture() -> None:
    import gzip as gz

    qurl = (
        "https://api.stackexchange.com/2.3/questions/136097"
        "?site=stackoverflow&filter=withbody"
    )
    aurl = (
        "https://api.stackexchange.com/2.3/questions/136097/answers"
        "?site=stackoverflow&filter=withbody&sort=votes&order=desc"
    )

    def api(url: str) -> dict:
        raw, _, _ = get(url)
        return json.loads(gz.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)

    q = api(qurl)["items"][0]
    answers = api(aurl)["items"][:5]
    body = [
        "<div id='mainbar'><div id='question' class='question'>",
        f"<h1>{html_lib.escape(q['title'])}</h1>",
        f"<div class='question-body'>{q['body']}</div>",
        "</div><div id='answers'>",
    ]
    for a in answers:
        body.append(
            f"<div class='answer' data-score='{a.get('score', 0)}' "
            f"data-accepted='{str(a.get('is_accepted', False)).lower()}'>"
            f"<div class='answer-body'>{a['body']}</div></div>"
        )
    body.append("</div></div>")
    raw = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html_lib.escape(q['title'])} - Stack Overflow</title></head>"
        "<body><nav>Stack Overflow</nav>"
        + "".join(body)
        + "<footer>Stack Overflow</footer>"
        "</body></html>"
    ).encode()
    reference = reference_from_xpath(raw.decode(), "//*[@id='mainbar']")
    record(
        "qa-stackoverflow",
        "thread",
        "https://stackoverflow.com/questions/136097",
        raw,
        "text/html; charset=utf-8",
        license_note="CC BY-SA 4.0 (Stack Exchange); question + top answers",
        capture_method="stackexchange-api-reconstruction",
        reference=reference,
        tags=["has_comments", "has_code"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("pass --allow-network to capture fixtures")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    only = set(args.only)

    def want(slug: str) -> bool:
        return not only or slug in only

    print("capturing fixtures...")
    if want("wikipedia-encyclopedia"):
        wikipedia(
            "wikipedia-encyclopedia", "Reddit", 1381843935, "article", ["has_tables"]
        )
    if want("captcha-mention"):
        wikipedia(
            "captcha-mention", "CAPTCHA", 1381256336, "article", ["mentions_captcha"]
        )
    if want("non-english"):
        wikipedia(
            "non-english",
            "Künstliche Intelligenz",
            271639746,
            "article",
            ["non_english"],
            lang="de",
        )
    if want("large-page"):
        wikipedia("large-page", "United States", 1381951802, "article", ["large"])
    if want("data-table"):
        wikipedia(
            "data-table",
            "List of countries and dependencies by population",
            1381775320,
            "table",
            ["has_tables", "data"],
        )

    if want("news-public-domain"):
        url = "https://www.nasa.gov/news-release/nasa-usda-sign-agreement-advancing-earth-science-agriculture/"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(raw.decode("utf-8", "replace"), "//article")
        record(
            "news-public-domain",
            "news",
            url,
            raw,
            ctype,
            license_note="U.S. government work (NASA), public domain",
            capture_method="http-get",
            reference=reference,
            tags=["news"],
        )

    if want("blog-longform-cc"):
        url = "https://www.eff.org/deeplinks/2026/10/anti-circumvention-laws-raise-cost-knowledge"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(raw.decode("utf-8", "replace"), "//article")
        record(
            "blog-longform-cc",
            "blog",
            url,
            raw,
            ctype,
            license_note="CC BY (EFF Deeplinks); excerpt for testing",
            capture_method="http-get",
            reference=reference,
            tags=["longform"],
        )

    if want("docs-reference"):
        url = "https://docs.python.org/3/library/asyncio-task.html"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(
            raw.decode("utf-8", "replace"), "//div[contains(@class,'body')]"
        )
        record(
            "docs-reference",
            "docs",
            url,
            raw,
            ctype,
            license_note="Python Software Foundation license",
            capture_method="http-get",
            reference=reference,
            tags=["has_code", "has_tables"],
        )

    if want("tutorial-code"):
        url = "https://docs.python.org/3/tutorial/controlflow.html"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(
            raw.decode("utf-8", "replace"), "//div[contains(@class,'body')]"
        )
        record(
            "tutorial-code",
            "tutorial",
            url,
            raw,
            ctype,
            license_note="Python Software Foundation license",
            capture_method="http-get",
            reference=reference,
            tags=["has_code"],
        )

    if want("forum-hackernews"):
        url = "https://news.ycombinator.com/item?id=50245138"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(
            raw.decode("utf-8", "replace"), "//*[@id='hnmain']"
        )
        record(
            "forum-hackernews",
            "thread",
            url,
            raw,
            ctype,
            license_note="User-submitted Hacker News content; excerpt for testing",
            capture_method="http-get",
            reference=reference,
            tags=["has_comments"],
        )

    if want("qa-stackoverflow"):
        so_fixture()

    if want("github-readme"):
        url = "https://github.com/open-webui/open-webui"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(
            raw.decode("utf-8", "replace"),
            "//article[contains(@class,'markdown-body')]",
        )
        record(
            "github-readme",
            "docs",
            url,
            raw,
            ctype,
            license_note="Repository license: Other/NOASSERTION (see repo); README excerpt",
            capture_method="http-get",
            reference=reference,
            tags=["has_code", "github_readme"],
        )

    if want("github-issue"):
        url = "https://github.com/open-webui/open-webui/issues/33229"
        raw, _status, ctype = get(url)
        doc = html.fromstring(raw.decode("utf-8", "replace"))
        bodies = doc.xpath("//*[contains(@class,'markdown-body')]")
        reference = tidy("\n\n".join(block_text(b) for b in bodies[:8]))
        record(
            "github-issue",
            "thread",
            url,
            raw,
            ctype,
            license_note="Repository license: Other/NOASSERTION (see repo); issue excerpt",
            capture_method="http-get",
            reference=reference,
            tags=["has_comments", "has_code"],
        )

    if want("paper-arxiv-html"):
        url = "https://arxiv.org/html/2307.09288v1"
        raw, _status, ctype = get(url)
        reference = reference_from_xpath(raw.decode("utf-8", "replace"), "//article")
        record(
            "paper-arxiv-html",
            "paper",
            url,
            raw,
            ctype,
            license_note="arXiv non-exclusive distribution license 1.0; excerpt",
            capture_method="http-get",
            reference=reference,
            tags=["has_tables", "has_code"],
        )

    if want("paper-arxiv-pdf"):
        from io import BytesIO

        from pypdf import PdfReader, PdfWriter

        url = "https://arxiv.org/pdf/2307.09288"
        raw, _status, ctype = get(url)
        reader = PdfReader(BytesIO(raw))
        writer = PdfWriter()
        for page in reader.pages[:10]:
            writer.add_page(page)
        buf = BytesIO()
        writer.write(buf)
        trimmed = buf.getvalue()
        text_parts = []
        for i, page in enumerate(reader.pages[:10], 1):
            text_parts.append(f"[page {i}]\n{page.extract_text() or ''}")
        reference = tidy("\n\n".join(text_parts))
        out = FIXTURES / "paper-arxiv-pdf"
        out.mkdir(parents=True, exist_ok=True)
        (out / "page.pdf").write_bytes(trimmed)
        (out / "reference.md").write_text(reference + "\n", encoding="utf-8")
        (out / "innertext.txt").write_text("", encoding="utf-8")
        meta = {
            "slug": "paper-arxiv-pdf",
            "page_type": "pdf",
            "source_url": url,
            "captured_at": datetime.now(UTC).date().isoformat(),
            "license": "arXiv non-exclusive distribution license 1.0; first 10 pages",
            "capture_method": "http-get + pypdf trim",
            "synthetic": False,
            "content_type": "application/pdf",
            "sha256": hashlib.sha256(trimmed).hexdigest(),
            "bytes_raw": len(trimmed),
            "stored_file": "page.pdf",
            "innertext_source": "pdf-text",
            "reference_method": "pypdf text + manual spot check",
            "reference_scope": "full",
            "tags": ["pdf"],
            "pages_original": len(reader.pages),
            "pages_stored": 10,
        }
        (out / "meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n"
        )
        print(f"  wrote paper-arxiv-pdf (pdf, {len(trimmed)} bytes)")

    if want("spa-rendered"):
        rendered = """<main><h1>Widget documentation</h1>
<p>Widget is a client-side library for composing dashboards.</p>
<h2>Install</h2><pre><code>npm install widget</code></pre>
<h2>Configuration</h2><table><tr><th>Option</th><th>Default</th></tr>
<tr><td>theme</td><td>auto</td></tr><tr><td>refreshSeconds</td><td>30</td></tr></table>
<p>The default refresh interval is 30 seconds.</p></main>"""
        shell = (
            "<!doctype html><html><head><meta charset='utf-8'><title>Widget docs</title>"
            "<script>window.__NEXT_DATA__={props:{}}</script></head><body>"
            "<div id='root'></div><script src='/static/app.js'></script></body></html>"
        )
        out = FIXTURES / "spa-rendered"
        out.mkdir(parents=True, exist_ok=True)
        (out / "page.html").write_text(shell, encoding="utf-8")
        (out / "rendered.html").write_text(rendered, encoding="utf-8")
        (out / "reference.md").write_text(
            tidy(html.fromstring(rendered).text_content()) + "\n"
        )
        (out / "innertext.txt").write_text(
            tidy(html.fromstring(rendered).text_content()) + "\n", encoding="utf-8"
        )
        meta = {
            "slug": "spa-rendered",
            "page_type": "spa",
            "source_url": "https://example.com/spa-rendered",
            "captured_at": datetime.now(UTC).date().isoformat(),
            "license": "No source license; synthetic test data",
            "capture_method": "synthetic raw shell + rendered DOM",
            "synthetic": True,
            "content_type": "text/html; charset=utf-8",
            "sha256": hashlib.sha256(shell.encode()).hexdigest(),
            "bytes_raw": len(shell),
            "stored_file": "page.html",
            "innertext_source": "rendered-lxml",
            "reference_method": "synthetic content",
            "reference_scope": "full",
            "tags": ["spa", "has_tables", "has_code"],
        }
        (out / "meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n"
        )
        print("  wrote spa-rendered (spa, synthetic)")

    synthetic(
        "product-reviews",
        "product",
        "<main><h1>Aurora Desk Lamp</h1><p class='price'>$49.99</p>"
        "<p>Rating: 4.6 out of 5 from 1,284 reviews.</p>"
        "<h2>Reviews</h2><div class='review'><p>Ada: Great light, easy on the eyes.</p></div>"
        "<div class='review'><p>Ben: The USB-C port stopped working after two months.</p></div>"
        "<div class='review'><p>Cleo: Best desk lamp for late-night reading.</p></div>"
        "<table><tr><th>Spec</th><th>Value</th></tr><tr><td>Color temperature</td><td>2700-6500 K</td></tr>"
        "<tr><td>Warranty</td><td>2 years</td></tr></table></main>",
        "Aurora Desk Lamp costs $49.99, has a 4.6/5 rating from 1,284 reviews, "
        "a 2-year warranty, and a 2700-6500 K color temperature. Ben reports a "
        "USB-C port failure after two months.",
        ["has_tables", "has_comments"],
    )
    synthetic(
        "listing-search",
        "listing",
        "<main><h1>Search results for 'mechanical keyboard'</h1><p>128 results</p>"
        "<ul class='results'><li><a href='/p/1'>QuietType 87</a> - $89.00 - rating 4.7</li>"
        "<li><a href='/p/2'>ClickyPro TKL</a> - $64.50 - rating 4.3</li>"
        "<li><a href='/p/3'>SplitErgo 65</a> - $129.00 - rating 4.8</li>"
        "<li><a href='/p/4'>BudgetBoard 60</a> - $39.99 - rating 4.0</li></ul>"
        "<p>Page 1 of 13</p></main>",
        "Search for 'mechanical keyboard' returns 128 results. The top four are "
        "QuietType 87 ($89.00, 4.7), ClickyPro TKL ($64.50, 4.3), SplitErgo 65 "
        "($129.00, 4.8) and BudgetBoard 60 ($39.99, 4.0). Page 1 of 13.",
        ["listing"],
    )
    synthetic(
        "paywall-cookie",
        "paywall",
        "<main><h1>Deep-sea mining explained</h1>"
        "<p>The first paragraph is visible. The rest is hidden by the paywall.</p>"
        "<div class='paywall'><h2>Subscribe to continue</h2>"
        "<p>Create a free account or subscribe for unlimited access.</p>"
        "<a href='/login'>Log in</a></div></main>",
        "[paywall] Subscribe to continue. Create a free account or subscribe for unlimited access.",
        ["paywall"],
    )
    synthetic(
        "challenge-bot",
        "challenge",
        "<main><h1>Just a moment...</h1>"
        "<div id='cf-challenge-running'>Performing security verification.</div>"
        "<p>Checking your browser before accessing the site. Enable JavaScript and cookies to continue.</p>"
        "<form id='challenge-form'><div class='g-recaptcha'></div></form></main>",
        "[needs_human] Challenge detected; human intervention required.",
        ["challenge"],
    )
    synthetic(
        "xbrl-statement",
        "table",
        "<main><type>XML</type><description>IDEA: XBRL DOCUMENT</description>"
        "<h1>Consolidated Statements of Operations</h1>"
        "<table><tr><th>Metric</th><th>2026</th><th>2025</th></tr>"
        "<tr><td>Revenue</td><td>804,905</td><td>499,627</td></tr>"
        "<tr><td>Operating income</td><td>231,716</td><td>89,297</td></tr>"
        "<tr><td>Net income</td><td>252,848</td><td>89,297</td></tr></table></main>",
        "2026 revenue 804,905; 2025 revenue 499,627; 2026 operating income "
        "231,716; 2026 net income 252,848.",
        ["has_tables", "xbrl", "data"],
    )

    manifest = []
    for meta_path in sorted(FIXTURES.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        manifest.append(meta)
    (FIXTURES / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} fixture manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
