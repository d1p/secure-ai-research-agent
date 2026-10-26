"""Secret guard for the LiteLLM proxy.

Blocks prompts that contain obvious secrets before they ever leave the host
for a cloud provider.  The pure detection functions below are dependency-free
so they can be unit-tested without the LiteLLM runtime; the `CustomLogger`
subclass at the bottom wires the same logic into LiteLLM's `async_pre_call_hook`.

Policy (from the project spec, section 11):
  * AWS access keys (AKIA.../ASIA...)
  * OpenAI-style `sk-...`
  * GitHub tokens (`ghp_...` and siblings)
  * PEM private keys
  * `.env`-style `KEY=` assignments with long secret values

Normal RAG chunks are intentionally NOT filtered unless they match one of the
rules above.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    """A single detected secret."""

    category: str
    value: str


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
# Legacy keys are `sk-` + an alphanumeric body; project/service-account (and
# Anthropic) keys use a known hyphenated prefix.  Do NOT allow arbitrary
# hyphens in the plain body, otherwise slugs like `sk-hynix-results-...`
# (SK Hynix) are misread as keys.
_OPENAI_KEY = re.compile(
    r"\bsk-(?:proj-[A-Za-z0-9_-]{20,}|svcacct-[A-Za-z0-9_-]{20,}|ant-[A-Za-z0-9_-]{20,}|[A-Za-z0-9]{20,})\b"
)
_GITHUB_TOKEN = re.compile(r"\bgh[psuro]_[A-Za-z0-9]{20,}\b")
_PEM_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
# `.env`-style assignment: an uppercase KEY name followed by `=` and a long value.
_ENV_ASSIGNMENT = re.compile(
    r"\b[A-Z][A-Z0-9_]{2,}\s*=\s*[\"']?[A-Za-z0-9+/_.\-]{24,}[\"']?"
)


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", _AWS_ACCESS_KEY),
    ("openai_key", _OPENAI_KEY),
    ("github_token", _GITHUB_TOKEN),
    ("pem_private_key", _PEM_PRIVATE_KEY),
    ("env_assignment", _ENV_ASSIGNMENT),
]


class SecretGuardError(Exception):
    """Raised when a cloud-bound request contains a secret."""


def detect_secrets(text: str) -> list[Finding]:
    """Return all secret findings present in a single string."""
    if not text:
        return []
    findings: list[Finding] = []
    for category, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            findings.append(Finding(category=category, value=match.group(0)))
    return findings


def _walk(value: Any) -> Iterable[str]:
    """Yield every string contained in a (possibly nested) payload."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def detect_secrets_in_request(payload: Any) -> list[Finding]:
    """Return all secret findings anywhere in a request payload."""
    findings: list[Finding] = []
    for text in _walk(payload):
        findings.extend(detect_secrets(text))
    return findings


def extract_message_texts(data: Any) -> list[str]:
    """Return only the text a user/model supplied in a chat request.

    LiteLLM injects infrastructure fields (notably the resolved ``api_key``,
    which itself matches the ``sk-...`` pattern) into the pre-call hook
    payload.  Scanning the whole dict would flag the caller's own credentials,
    so the hook must restrict itself to message content.
    """
    if not isinstance(data, dict):
        return []
    texts: list[str] = []
    messages = data.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        texts.append(part["text"])
    return texts


# ---------------------------------------------------------------------------
# LiteLLM callback wiring (only importable inside the LiteLLM runtime)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised inside the LiteLLM container only
    from litellm.integrations.custom_logger import CustomLogger
except Exception:  # noqa: BLE001 - litellm not installed in the unit-test venv
    CustomLogger = object  # type: ignore[assignment]


class SecretGuardHandler(CustomLogger):  # type: ignore[misc]
    """Reject any cloud-bound request containing obvious secrets."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any = None,
        cache: Any = None,
        data: dict[str, Any] | None = None,
        call_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        findings: list[Finding] = []
        for text in extract_message_texts(data):
            findings.extend(detect_secrets(text))
        if findings:
            detail = "; ".join(f"{f.category}: {f.value[:24]}" for f in findings[:3])
            raise SecretGuardError(
                f"SecretGuard blocked request: detected {len(findings)} "
                f"secret(s) — {detail}"
            )
        return data


# Module-level instance referenced from config.yaml:
#   litellm_settings:
#     callbacks: secret_guard.secret_guard_handler
secret_guard_handler = SecretGuardHandler()
