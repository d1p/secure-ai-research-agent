# Plan 02 - Ground truth and hand-marked references

- **Workstream:** A2
- **Depends on:** plan 01
- **Gate:** every fixture has 3-5 verifiable questions and a labelled
  reference; the validator passes offline.

## Goal

Make "answer accuracy" and "main-content precision/recall" measurable without
inventing facts after the fact.

## Deliverables per fixture

`questions.json`:

```json
[
  {
    "id": "q1",
    "question": "Who founded the project and in which year?",
    "answer": "Jane Doe, 2011",
    "evidence": "exact or near-exact source quote",
    "kind": "prose|deep|table|list|code|comment",
    "grading": "exact|semantic",
    "notes": "numeric answers compare after normalising separators"
  }
]
```

- 3-5 questions per fixture. Each set includes at least one answer that sits
  deep in the page and one that lives in a table, list, code block or comment.
- `exact` is used for numbers, names and dates; `semantic` for prose answers.
- For paywall/challenge fixtures, `meta.json` records
  `expected_needs_human: true`; the questions are checks of the expected clean
  refusal (for example "does the loader avoid returning the challenge body?"),
  not questions whose answers require leaking challenge junk.

`reference.md` (hand-marked main content):

- Include title, headings, body, tables, code and comment text in order.
- Exclude navigation, footers, ads, cookie banners, related-link rails and
  boilerplate.
- For threads, include the question and all meaningful comments; mark deleted
  or junk comments as excluded.
- For the >1 MB page, mark representative main sections and record
  `reference_scope: "sample"`; precision/recall on that fixture is reported
  as sample-scoped, not as full-page recall.
- Record `reference_scope: "full"` everywhere else.

## Reference marking method

1. Draft from the current reader output plus a raw-DOM spot check.
2. Manually correct omissions and boilerplate; or write from the source where
   the reader output is untrustworthy.
3. Keep the same text order as the page so recall is meaningful.
4. Record the marking method and time in `meta.json`.

## Page-type labels

Each `meta.json` has `page_type` from the plan 01 enum, plus tags such as
`non_english`, `large`, `paywall`, `challenge`, `has_comments`, `has_code`.
Plan 08 measures detection against these labels; they are not changed to make
the detector look good.

## Tests

- `tests/test_ground_truth.py` validates JSON shape, 3-5 questions, unique ids,
  allowed `kind`/`grading`, non-empty answers/evidence, reference presence, and
  that every quoted `evidence` string actually occurs in `reference.md` or the
  raw fixture (normalised whitespace).
- It checks the required "deep" and "structured" coverage per fixture.
- It checks `expected_needs_human` fixtures have no answerable questions whose
  answer would require leaking challenge junk.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_ground_truth.py
.venv/bin/python -m pytest -q
```

## Risks / notes

- Ground truth is the most expensive part of the corpus. If a source is
  ambiguous, prefer a question the page answers unambiguously; drop the
  question rather than guess.
- Do not tune questions to the current extractor. Answer them from the
  reference/source, then measure extractors against them.
