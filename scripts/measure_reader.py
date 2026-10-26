#!/usr/bin/env python3
"""Compare reader-mode extraction with the old tag-strip at equal budgets.

Measures the metric that matters: the smallest budget that still contains all
the key facts, and the tokens needed at that budget.  Fixed-budget token
counts alone are misleading because both methods fill the same cap.

Examples:
  python scripts/measure_reader.py --html /tmp/page.html --url https://example.com \\
      --facts "Revenue,Net Income,2025,2024"

  python scripts/measure_reader.py --url https://en.wikipedia.org/wiki/Reddit \\
      --facts "Founded,Headquarters,Steve Huffman"
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.reader import (
    DEFAULT_MAX_CHARS,
    _strip_tags,
    content_budget,
    read_html,
)

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def token_count(text: str) -> int:
        return len(_ENC.encode(text))

    TOKENIZER = "cl100k_base"
except ImportError:  # pragma: no cover - benchmark still works without tiktoken

    def token_count(text: str) -> int:
        return len(text) // 4

    TOKENIZER = "chars/4 estimate"


@dataclass(frozen=True)
class Row:
    budget: int
    reader_tokens: int
    reader_facts: int
    tag_tokens: int
    tag_facts: int


def _load(source: str) -> tuple[str, str]:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "homelab-ai-stack/1.0 (ops@example.invalid)"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        return raw.decode("utf-8", errors="replace"), source
    path = Path(source)
    return path.read_text(encoding="utf-8", errors="replace"), ""


def _facts(text: str, keys: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for key in keys if key.lower() in lowered)


def _row(html: str, url: str, facts: list[str], budget: int) -> Row:
    extracted = read_html(html, url, max_chars=budget)
    tag = _strip_tags(html)[:budget]
    return Row(
        budget=budget,
        reader_tokens=token_count(extracted.text),
        reader_facts=_facts(extracted.text, facts),
        tag_tokens=token_count(tag),
        tag_facts=_facts(tag, facts),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html", action="append", default=[], help="local HTML file (repeatable)"
    )
    parser.add_argument(
        "--url", action="append", default=[], help="URL to fetch (repeatable)"
    )
    parser.add_argument(
        "--facts",
        default="",
        help="key facts separated by '|' (use '|' so commas inside numbers work)",
    )
    parser.add_argument(
        "--budgets",
        default="2000,4000,6000,8000,10000,12000,16000,24000,32000",
        help="comma-separated character budgets",
    )
    args = parser.parse_args()

    sources = args.html + args.url
    if not sources:
        parser.error("provide at least one --html or --url")
    raw_facts = args.facts
    facts = [
        item.strip()
        for item in (raw_facts.split("|") if "|" in raw_facts else raw_facts.split(","))
        if item.strip()
    ]
    budgets = sorted({int(item) for item in args.budgets.split(",") if item.strip()})

    print(f"tokenizer: {TOKENIZER}")
    for source in sources:
        html, url = _load(source)
        if url:
            print(f"\n## {url}")
            print(
                f"per-domain budget: {content_budget(url)} chars (default {DEFAULT_MAX_CHARS})"
            )
        else:
            print(f"\n## {source}")
        full = read_html(html, url, max_chars=None)
        tag = _strip_tags(html)
        print(
            f"full reader: {token_count(full.text)} tok, {len(full.text)} chars, "
            f"method={full.method}, sources={full.source_count}; "
            f"tag-strip: {token_count(tag)} tok, {len(tag)} chars"
        )
        if full.reader_chars:
            print(
                f"link compaction: {full.reader_chars} -> {len(full.text)} chars "
                f"({100 - round(100 * len(full.text) / full.reader_chars, 1)}% smaller)"
            )
        if facts:
            print(f"facts ({len(facts)}): {', '.join(facts)}")
        print()
        print("| budget | reader tok | reader facts | tag tok | tag facts |")
        print("|--------|-----------|--------------|---------|-----------|")
        rows = [_row(html, url, facts, budget) for budget in budgets]
        for row in rows:
            print(
                f"| {row.budget} | {row.reader_tokens} | {row.reader_facts}/{len(facts)} | "
                f"{row.tag_tokens} | {row.tag_facts}/{len(facts)} |"
            )
        if facts:
            need = len(facts)
            reader_min = next((row for row in rows if row.reader_facts == need), None)
            tag_min = next((row for row in rows if row.tag_facts == need), None)
            print(
                f"\nmin budget for {need}/{need}: reader "
                f"{reader_min.budget if reader_min else 'not reached'} chars / "
                f"{reader_min.reader_tokens if reader_min else '-'} tok; tag "
                f"{tag_min.budget if tag_min else 'not reached'} chars / "
                f"{tag_min.tag_tokens if tag_min else '-'} tok"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
