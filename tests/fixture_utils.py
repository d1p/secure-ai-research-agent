"""Helpers for loading the pinned benchmark fixtures offline."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PAGE_TYPES = {
    "article",
    "news",
    "blog",
    "docs",
    "tutorial",
    "thread",
    "listing",
    "table",
    "paper",
    "pdf",
    "product",
    "spa",
    "paywall",
    "challenge",
    "unknown",
}

KINDS = {"prose", "deep", "table", "list", "code", "comment"}
GRADING = {"exact", "semantic"}


def fixture_dirs() -> list[Path]:
    return sorted(p for p in FIXTURES.glob("*/meta.json"))


def load_meta(slug: str) -> dict[str, Any]:
    return json.loads((FIXTURES / slug / "meta.json").read_text(encoding="utf-8"))


def load_page_bytes(slug: str) -> bytes:
    meta = load_meta(slug)
    path = FIXTURES / slug / meta["stored_file"]
    raw = path.read_bytes()
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def load_page_text(slug: str) -> str:
    return load_page_bytes(slug).decode("utf-8", errors="replace")


def load_rendered(slug: str) -> str | None:
    path = FIXTURES / slug / "rendered.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


def load_innertext(slug: str) -> str:
    return (FIXTURES / slug / "innertext.txt").read_text(encoding="utf-8")


def load_reference(slug: str) -> str:
    return (FIXTURES / slug / "reference.md").read_text(encoding="utf-8")


def load_questions(slug: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / slug / "questions.json").read_text(encoding="utf-8"))


def all_questions() -> dict[str, list[dict[str, Any]]]:
    return {p.parent.name: load_questions(p.parent.name) for p in fixture_dirs()}
