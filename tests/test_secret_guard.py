"""Unit tests for the LiteLLM secret guard (project spec section 11)."""

from __future__ import annotations

import pytest

from litellm.secret_guard import (
    Finding,
    detect_secrets,
    detect_secrets_in_request,
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
    assert "env_assignment" in categories("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")


def test_env_assignment_quoted_detected() -> None:
    assert "env_assignment" in categories('AWS_SECRET_ACCESS_KEY="abcdefghijklmnopqrstuvwxyz1234567890"')


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
            {"role": "user", "content": "here is my key sk-abcdefghijklmnopqrstuvwxyz123456"},
        ],
        "nested": {"deep": ["AKIAIOSFODNN7EXAMPLE"]},
    }
    findings = detect_secrets_in_request(payload)
    cats = {f.category for f in findings}
    assert "openai_key" in cats and "aws_access_key" in cats


def test_detect_secrets_returns_finding_type() -> None:
    findings = detect_secrets("ghp_" + "b" * 36)
    assert all(isinstance(f, Finding) for f in findings)
