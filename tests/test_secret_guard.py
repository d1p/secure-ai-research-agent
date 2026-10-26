"""Unit tests for the LiteLLM secret guard (project spec section 11)."""

from __future__ import annotations

import pytest

from litellm.secret_guard import (
    Finding,
    detect_secrets,
    detect_secrets_in_request,
    extract_message_texts,
)


def categories(text: str) -> set[str]:
    return {f.category for f in detect_secrets(text)}


# --- AWS access keys -------------------------------------------------------
def test_aws_access_key_detected() -> None:
    assert "aws_access_key" in categories("AKIAIOSFODNN7EXAMPLE")


def test_aws_session_key_detected() -> None:
    assert "aws_access_key" in categories("ASIAIOSFODNN7EXAMPLE")


# --- OpenAI-style keys -----------------------------------------------------
def test_openai_key_detected() -> None:
    assert "openai_key" in categories("sk-abcdefghijklmnopqrstuvwxyz123456")


def test_openai_proj_key_detected() -> None:
    assert "openai_key" in categories("sk-proj-abcdefghijklmnopqrstuvwxyz123456")


@pytest.mark.parametrize(
    "text",
    [
        "sk-hynix-results-bull-950-bear-800",
        "https://example.com/head-taoyuan-talks-27-october-sk-hynix-results-bull-950-bear-800/",
        "SK Hynix (sk-hynix) reported earnings",
    ],
)
def test_sk_hynix_slug_not_flagged(text: str) -> None:
    assert "openai_key" not in categories(text)


# --- GitHub tokens ---------------------------------------------------------
@pytest.mark.parametrize("prefix", ["ghp_", "gho_", "ghu_", "ghs_", "ghr_"])
def test_github_tokens_detected(prefix: str) -> None:
    token = prefix + "a" * 36
    assert "github_token" in categories(token)


# --- PEM private keys ------------------------------------------------------
def test_pem_private_key_detected() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----"
    assert "pem_private_key" in categories(pem)


def test_pem_ec_private_key_detected() -> None:
    pem = "-----BEGIN EC PRIVATE KEY-----\nabc\n-----END EC PRIVATE KEY-----"
    assert "pem_private_key" in categories(pem)


# --- .env-style assignments ------------------------------------------------
def test_env_assignment_detected() -> None:
    assert "env_assignment" in categories(
        "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"
    )


def test_env_assignment_quoted_detected() -> None:
    assert "env_assignment" in categories(
        'AWS_SECRET_ACCESS_KEY="abcdefghijklmnopqrstuvwxyz1234567890"'
    )


# --- Normal RAG content must NOT be flagged --------------------------------
def test_normal_rag_content_not_flagged() -> None:
    text = (
        "The document describes the company's Q3 earnings. Revenue was $1.2B, "
        "up 15% year over year. Key=value pairs like region=us-east are common."
    )
    assert detect_secrets(text) == []


def test_short_assignment_not_flagged() -> None:
    assert detect_secrets("A=1 and B=2") == []


# --- Request-walking -------------------------------------------------------
def test_detect_secrets_in_nested_request() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "here is my key sk-abcdefghijklmnopqrstuvwxyz123456",
            },
        ],
        "nested": {"deep": ["AKIAIOSFODNN7EXAMPLE"]},
    }
    findings = detect_secrets_in_request(payload)
    cats = {f.category for f in findings}
    assert "openai_key" in cats and "aws_access_key" in cats


def test_detect_secrets_returns_finding_type() -> None:
    findings = detect_secrets("ghp_" + "b" * 36)
    assert all(isinstance(f, Finding) for f in findings)


# --- Pre-call hook scope ----------------------------------------------------
# The LiteLLM pre-call hook payload includes the resolved `api_key` (which
# itself matches the `sk-...` pattern).  The hook must only scan message
# content, otherwise every real request would be blocked.


def test_extract_message_texts_ignores_injected_api_key() -> None:
    payload = {
        "model": "deepseek-flash",
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    }
    assert extract_message_texts(payload) == ["Reply with exactly: OK"]


def test_hook_scope_not_flagged_by_injected_api_key() -> None:
    payload = {
        "model": "deepseek-flash",
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
        "messages": [{"role": "user", "content": "hello world"}],
    }
    findings = [
        f for text in extract_message_texts(payload) for f in detect_secrets(text)
    ]
    assert findings == []


def test_hook_scope_still_flags_secret_in_message() -> None:
    payload = {
        "model": "deepseek-flash",
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
        "messages": [{"role": "user", "content": "my token is ghp_" + "b" * 36}],
    }
    findings = [
        f for text in extract_message_texts(payload) for f in detect_secrets(text)
    ]
    assert {f.category for f in findings} == {"github_token"}


def test_extract_message_texts_multimodal_parts() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAAA"},
                    },
                ],
            }
        ]
    }
    assert extract_message_texts(payload) == ["describe this"]
