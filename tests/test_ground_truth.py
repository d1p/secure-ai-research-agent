"""Ground-truth coverage: deep and structured answers per fixture."""

from __future__ import annotations

from fixture_utils import fixture_dirs, load_meta, load_questions

STRUCTURED = {"table", "list", "code", "comment"}


def test_each_content_fixture_has_deep_and_structured_coverage() -> None:
    for meta_path in fixture_dirs():
        slug = meta_path.parent.name
        meta = load_meta(slug)
        if meta.get("expected_needs_human"):
            continue
        kinds = {q["kind"] for q in load_questions(slug)}
        assert "deep" in kinds, f"{slug}: no deep question"
        if meta["page_type"] in {
            "thread",
            "listing",
            "table",
            "product",
            "docs",
            "tutorial",
            "paper",
            "pdf",
            "spa",
        } or {"has_tables", "has_code", "has_comments"} & set(meta["tags"]):
            assert kinds & STRUCTURED, f"{slug}: no structured question"


def test_expected_refusal_fixtures_do_not_require_page_junk() -> None:
    for slug in ("paywall-cookie", "challenge-bot"):
        assert load_meta(slug).get("expected_needs_human") is True
        assert len(load_questions(slug)) == 3


def test_question_sets_are_not_trivial() -> None:
    total = 0
    gradings: set[str] = set()
    for meta_path in fixture_dirs():
        slug = meta_path.parent.name
        questions = load_questions(slug)
        total += len(questions)
        gradings.update(q["grading"] for q in questions)
    assert total >= 60
    assert gradings == {"exact", "semantic"}
