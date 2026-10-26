#!/usr/bin/env python3
"""Minimal repro for trafilatura's stateful deduplicate=True behavior."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from fixture_utils import load_meta, load_page_text


def run(html: str, url: str, deduplicate: bool, calls: int) -> list[tuple[int, str]]:
    import trafilatura

    out = []
    for _ in range(calls):
        text = (
            trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_formatting=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,
                deduplicate=deduplicate,
            )
            or ""
        )
        out.append((len(text), hashlib.sha256(text.encode()).hexdigest()[:12]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="docs-reference")
    parser.add_argument("--calls", type=int, default=10)
    args = parser.parse_args()
    meta = load_meta(args.fixture)
    html = load_page_text(args.fixture)
    for deduplicate in (True, False):
        rows = run(html, meta["source_url"], deduplicate, args.calls)
        print(f"deduplicate={deduplicate}")
        for index, (chars, digest) in enumerate(rows, 1):
            print(f"  {index:02d}: {chars:>8} chars {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
