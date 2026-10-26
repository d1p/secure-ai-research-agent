"""Fixture corpus integrity: hashes, coverage, licenses and privacy."""

from __future__ import annotations

import gzip
import hashlib
import json
import re

from fixture_utils import (
    FIXTURES,
    GRADING,
    KINDS,
    PAGE_TYPES,
    fixture_dirs,
    load_meta,
    load_page_bytes,
    load_questions,
    load_reference,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PRIVATE_IP_RE = re.compile(
    r"\b(?:10|127|169\.254|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)"
    r"\.[0-9]{1,3}\.[0-9]{1,3}\b"
)
INTERNAL_HOST_RE = re.compile(r"\.(?:local|lan|internal|home|corp)\b", re.IGNORECASE)


def test_manifest_matches_directories_and_hashes() -> None:
    metas = [load_meta(p.parent.name) for p in fixture_dirs()]
    assert len(metas) == 21
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert {m["slug"] for m in manifest} == {m["slug"] for m in metas}
    for meta in metas:
        slug = meta["slug"]
        for key in (
            "page_type",
            "source_url",
            "captured_at",
            "license",
            "capture_method",
            "stored_file",
            "sha256",
        ):
            assert meta.get(key), f"{slug} missing {key}"
        assert meta["page_type"] in PAGE_TYPES, slug
        raw = load_page_bytes(slug)
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], slug
        assert raw, slug
        assert (FIXTURES / slug / "reference.md").read_text().strip(), slug
        assert (FIXTURES / slug / "questions.json").exists(), slug


def test_required_categories_are_covered() -> None:
    metas = {m["slug"]: m for m in (load_meta(p.parent.name) for p in fixture_dirs())}
    by_type: dict[str, list[str]] = {}
    for meta in metas.values():
        by_type.setdefault(meta["page_type"], []).append(meta["slug"])

    required_types = {
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
        "spa",
        "paywall",
        "challenge",
    }
    assert required_types <= set(by_type), required_types - set(by_type)
    assert "wikipedia-encyclopedia" in metas
    assert "github-readme" in metas and "github-issue" in metas
    assert any("xbrl" in m["tags"] for m in metas.values())
    assert any("mentions_captcha" in m["tags"] for m in metas.values())
    assert any("non_english" in m["tags"] for m in metas.values())
    assert any("large" in m["tags"] for m in metas.values())
    assert any("has_code" in m["tags"] for m in metas.values())
    assert any("has_comments" in m["tags"] for m in metas.values())
    assert any("has_tables" in m["tags"] for m in metas.values())


def test_large_and_pdf_fixtures_are_real() -> None:
    large = load_meta("large-page")
    assert len(load_page_bytes("large-page")) > 1_000_000, large
    assert (FIXTURES / "large-page" / large["stored_file"]).suffix == ".gz"
    assert load_page_bytes("paper-arxiv-pdf").startswith(b"%PDF-")
    assert any(
        (FIXTURES / p.parent.name / "page.html.gz").exists() for p in fixture_dirs()
    )


def test_paywall_and_challenge_expect_refusal() -> None:
    for slug in ("paywall-cookie", "challenge-bot"):
        assert load_meta(slug).get("expected_needs_human") is True
        assert load_questions(slug)


def test_synthetic_fixtures_are_labelled() -> None:
    for slug in (
        "product-reviews",
        "listing-search",
        "paywall-cookie",
        "challenge-bot",
        "spa-rendered",
        "xbrl-statement",
    ):
        assert load_meta(slug)["synthetic"] is True
        assert "No source license" in load_meta(slug)["license"]


def test_fixtures_contain_no_personal_data() -> None:
    for path in FIXTURES.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".gz":
            text = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        elif path.suffix in {".html", ".txt", ".md", ".json", ".pdf"}:
            text = path.read_bytes().decode("utf-8", "replace")
        else:
            continue
        assert not EMAIL_RE.search(text), f"email in {path}"
        assert not PRIVATE_IP_RE.search(text), f"private IP in {path}"
        # host.docker.internal is a documented Docker special-use name, not infra.
        scrubbed = text.replace("host.docker.internal", "host.docker.example")
        assert not INTERNAL_HOST_RE.search(scrubbed), f"internal hostname in {path}"


def test_questions_shape_and_evidence() -> None:
    for meta_path in fixture_dirs():
        slug = meta_path.parent.name
        reference = " ".join(load_reference(slug).split()).lower()
        questions = load_questions(slug)
        assert 3 <= len(questions) <= 5, slug
        assert len({q["id"] for q in questions}) == len(questions), slug
        for q in questions:
            assert q["question"].strip(), (slug, q)
            assert q["answer"].strip(), (slug, q)
            assert q["evidence"].strip(), (slug, q)
            assert q["kind"] in KINDS, (slug, q)
            assert q["grading"] in GRADING, (slug, q)
            evidence = " ".join(q["evidence"].split()).lower()
            assert evidence in reference, (slug, q["id"], q["evidence"])
