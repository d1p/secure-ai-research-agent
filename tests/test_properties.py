"""Property/fuzz tests: malformed input never crashes and budgets hold."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from shared.reader import read_html
from shared.tokens import count_tokens


@given(st.text(max_size=2000))
@settings(max_examples=30, deadline=None)
def test_reader_never_raises_and_is_deterministic(text: str) -> None:
    first = read_html(text, max_chars=200)
    second = read_html(text, max_chars=200)
    assert first.text == second.text
    assert first.method == second.method
    assert first.reason == second.reason


@given(st.integers(min_value=1, max_value=500), st.text(max_size=1000))
@settings(max_examples=30, deadline=None)
def test_output_never_exceeds_budget(budget: int, text: str) -> None:
    result = read_html(text, max_chars=budget)
    assert (
        len(result.text)
        <= budget
        + len("[content truncated; raise max_chars or request the source URL for more]")
        + 4
    )


@given(st.binary(max_size=1000))
@settings(max_examples=20, deadline=None)
def test_pdf_parser_never_raises(data: bytes) -> None:
    from shared.reader import extract_pdf

    result = extract_pdf(data, max_chars=200)
    assert isinstance(result.text, str)
    assert count_tokens(result.text) >= 0
