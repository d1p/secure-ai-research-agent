"""Page-type budgets and deployment overrides."""

from __future__ import annotations

import json

from shared.reader import PAGE_TYPE_BUDGETS, content_budget


def test_budgets_are_page_type_not_domain() -> None:
    assert content_budget("https://finance.example.com/x", page_type="article") == 24000
    assert content_budget("https://finance.example.com/x", page_type="table") == 24000
    assert "stockanalysis.com" not in PAGE_TYPE_BUDGETS
    assert content_budget("https://example.com/x", page_type="unknown") == 12000


def test_explicit_request_is_capped_by_page_type_and_hard_max(monkeypatch) -> None:
    assert content_budget("https://example.com/x", 99999, "docs") == 12000
    assert content_budget("https://example.com/x", 4000, "docs") == 4000
    assert content_budget("https://example.com/x", 0, "docs") == 12000
    assert content_budget("https://example.com/x", -1, "docs") == 12000


def test_env_override_is_a_deployment_escape_hatch(monkeypatch) -> None:
    monkeypatch.setenv(
        "READER_BUDGET_OVERRIDES",
        json.dumps({"example.com": 30000, "bad.example": "nope"}),
    )
    assert content_budget("https://example.com/x", page_type="docs") == 30000
    assert content_budget("https://docs.example.com/x", page_type="docs") == 30000
    assert content_budget("https://bad.example/x", page_type="docs") == 12000
    assert content_budget("https://example.com/x", 99999, "docs") == 30000


def test_invalid_override_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("READER_BUDGET_OVERRIDES", "{not json")
    assert content_budget("https://example.com/x", page_type="docs") == 12000
