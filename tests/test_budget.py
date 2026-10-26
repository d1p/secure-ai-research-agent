"""Cumulative output budget for sub-agent runs."""

from __future__ import annotations

import gateway.app as gw
from shared.budget import OutputBudget


def test_budget_allows_then_blocks() -> None:
    budget = OutputBudget(max_chars=100, ttl=60)
    assert budget.consume("run", 60, now=0)[0] is True
    assert budget.consume("run", 30, now=1)[0] is True
    allowed, used = budget.consume("run", 20, now=2)
    assert allowed is False
    assert used == 90


def test_new_run_and_ttl_reset() -> None:
    budget = OutputBudget(max_chars=50, ttl=10)
    assert budget.consume("a", 50, now=0)[0] is True
    assert budget.consume("a", 1, now=1)[0] is False
    assert budget.consume("b", 50, now=1)[0] is True
    assert budget.consume("a", 1, now=11)[0] is True


def test_gateway_budget_marker(monkeypatch) -> None:
    monkeypatch.setattr(gw, "_OUTPUT_BUDGET", OutputBudget(max_chars=50, ttl=60))
    first = {"result": {"content": [{"type": "text", "text": "x" * 40}]}}
    assert gw._apply_output_budget(first, "run") is first
    second = {"result": {"content": [{"type": "text", "text": "y" * 40}]}}
    blocked = gw._apply_output_budget(second, "run")
    assert blocked["budget_exceeded"] is True
    assert blocked["result"]["content"][0]["text"].startswith("[budget_exceeded]")
    assert "y" * 10 not in blocked["result"]["content"][0]["text"]
    fresh = {"result": {"content": [{"type": "text", "text": "z" * 40}]}}
    assert gw._apply_output_budget(fresh, "other") is fresh
