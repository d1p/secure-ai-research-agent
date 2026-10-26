"""Repeated reader calls must not degrade (trafilatura stateful dedup bug)."""

from __future__ import annotations

import hashlib

import pytest
from fixture_utils import load_meta, load_page_text

from shared.reader import read_html


def _hashes(html: str, slug: str, calls: int) -> list[str]:
    url = load_meta(slug)["source_url"]
    out = []
    for _ in range(calls):
        result = read_html(html, url, max_chars=None)
        assert result.text, "reader returned empty output"
        out.append(
            result.method + ":" + hashlib.sha256(result.text.encode()).hexdigest()
        )
    return out


def test_twenty_five_repeats_are_stable_fast() -> None:
    html = load_page_text("docs-reference")
    hashes = _hashes(html, "docs-reference", 25)
    assert len(set(hashes)) == 1
    assert all(h.startswith("reader:") for h in hashes)


@pytest.mark.slow
def test_repeats_on_large_page_are_stable() -> None:
    html = load_page_text("large-page")
    hashes = _hashes(html, "large-page", 10)
    assert len(set(hashes)) == 1
