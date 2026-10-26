"""Golden extraction snapshots and fallback-boundary checks."""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest
from fixture_utils import (
    fixture_dirs,
    load_meta,
    load_page_bytes,
    load_page_text,
    load_rendered,
)

from shared import reader
from shared.reader import content_budget, extract_pdf, read_html

GOLDEN = Path(__file__).resolve().parent / "golden"


def _current_output(slug: str, meta: dict) -> str:
    if meta["page_type"] == "pdf":
        return extract_pdf(
            load_page_bytes(slug), content_budget("", page_type="pdf")
        ).text
    raw = load_rendered(slug) if meta["page_type"] == "spa" else load_page_text(slug)
    return read_html(
        raw,
        meta["source_url"],
        content_budget(meta["source_url"], page_type=meta["page_type"]),
        include_links="sources",
    ).text


def _golden_path(slug: str) -> Path:
    return GOLDEN / f"{slug}.md.gz"


def test_golden_snapshots() -> None:
    GOLDEN.mkdir(exist_ok=True)
    update = os.environ.get("UPDATE_GOLDEN") == "1"
    for meta_path in fixture_dirs():
        slug = meta_path.parent.name
        meta = load_meta(slug)
        current = _current_output(slug, meta).replace("\r\n", "\n").strip() + "\n"
        path = _golden_path(slug)
        if update or not path.exists():
            path.write_bytes(gzip.compress(current.encode(), compresslevel=9))
            if not update:
                pytest.skip(f"created golden for {slug}; rerun")
            continue
        expected = gzip.decompress(path.read_bytes()).decode().replace("\r\n", "\n")
        assert current == expected, (
            f"golden changed for {slug}; review the diff, then "
            f"UPDATE_GOLDEN=1 pytest tests/test_golden.py"
        )


def _boundary(html_size: int, reader_size: int, monkeypatch) -> str:
    monkeypatch.setattr(reader, "_extract_markdown", lambda *a, **k: "x" * reader_size)
    html = "<html><body><p>" + ("word " * (html_size // 5)) + "</p></body></html>"
    return read_html(html, max_chars=None).method


def test_fallback_boundary_ratio(monkeypatch) -> None:
    # tag text about 2000 chars; 0.35 * 2000 = 700.
    assert _boundary(2000, 700, monkeypatch) == "reader"
    assert _boundary(2000, 699, monkeypatch) == "tag-strip"


def test_fallback_boundary_min_chars(monkeypatch) -> None:
    # Below the minimum tag length, a tiny reader result is kept.
    assert _boundary(700, 100, monkeypatch) == "reader"


def test_fallback_boundary_max_chars(monkeypatch) -> None:
    # Long tag text with a small reader result falls back below 4000 chars.
    assert _boundary(12000, 3999, monkeypatch) == "tag-strip"
    assert _boundary(12000, 4000, monkeypatch) == "reader"
