"""Tool-tier and sensitive-element tests (project spec section 14/22)."""

from __future__ import annotations

import pytest

from gateway.security import (
    TIER_ALWAYS,
    TIER_APPROVAL,
    TIER_FORBIDDEN,
    TIER_VALIDATED,
    action_is_sensitive,
    classify_tool,
    field_is_sensitive,
    is_sensitive_element,
)


@pytest.mark.parametrize(
    "tool",
    [
        "stagehand_navigate",
        "stagehand_read",
        "stagehand_observe",
        "stagehand_extract",
        "stagehand_screenshot",
    ],
)
def test_tier0_tools(tool: str) -> None:
    assert classify_tool(tool) == TIER_ALWAYS


@pytest.mark.parametrize("tool", ["stagehand_act"])
def test_tier1_tools(tool: str) -> None:
    assert classify_tool(tool) == TIER_VALIDATED


@pytest.mark.parametrize(
    "tool",
    [
        "stagehand_exec",
        "browser_evaluate",
        "browser_cookie_get",
        "browser_localstorage_get",
        "browser_file_download",
        "stagehand_network",
    ],
)
def test_tier3_tools_403(tool: str) -> None:
    assert classify_tool(tool) == TIER_FORBIDDEN


def test_unknown_tool_denied() -> None:
    assert classify_tool("stagehand_mystery_tool") == TIER_FORBIDDEN


@pytest.mark.parametrize("label", ["password", "Enter password", "credit card number", "CVV", "PIN code"])
def test_sensitive_fields_blocked(label: str) -> None:
    assert field_is_sensitive(label) is True


@pytest.mark.parametrize(
    "label",
    ["buy now", "checkout", "place order", "submit", "send message", "delete account", "sign in", "confirm purchase"],
)
def test_sensitive_actions_flagged(label: str) -> None:
    assert action_is_sensitive(label) is True


def test_sensitive_element_detection() -> None:
    assert is_sensitive_element("input", "textbox", "password") is True
    assert is_sensitive_element("button", "button", "Buy now") is True


def test_normal_element_not_sensitive() -> None:
    assert is_sensitive_element("input", "searchbox", "search the web") is False
