"""Token counting for logs/metrics.

tiktoken cl100k_base is a labelled proxy for DeepSeek's tokenizer, not an exact
match. Offline benchmarks can use the real tokenizer via
``BENCH_DEEPSEEK_TOKENIZER``; runtime uses this helper.
"""

from __future__ import annotations

import os
from functools import lru_cache

_FORCE = os.environ.get("TOKENIZER", "").lower()
_ENCODING = None
_NAME = "chars4"


def _encoding():
    global _ENCODING, _NAME
    if _ENCODING is not None:
        return _ENCODING
    if _FORCE in {"chars4", "chars/4", "estimate"}:
        _NAME = "chars4"
        return None
    try:
        import tiktoken

        _ENCODING = tiktoken.get_encoding("cl100k_base")
        _NAME = "tiktoken:cl100k_base"
    except Exception:  # noqa: BLE001 - optional dependency
        _ENCODING = None
        _NAME = "chars4"
    return _ENCODING


@lru_cache(maxsize=256)
def _count_cached(text: str) -> int:
    enc = _encoding()
    return len(enc.encode(text)) if enc is not None else len(text) // 4


def count_tokens(text: str) -> int:
    return _count_cached(text or "")


def tokenizer_name() -> str:
    _encoding()
    return _NAME
