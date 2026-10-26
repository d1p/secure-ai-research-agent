# Plan 08 - Page-type detection

- **Workstream:** B1
- **Depends on:** plans 01-04 (corpus and baseline)
- **Gate:** detection runs on the corpus, misclassification is reported, and no
  extraction routing is enabled unless measured. This plan can ship detection
  as observability-only first.

## Goal

Classify pages simply and honestly so budgets, structured extraction and
thread mode can use a shared signal instead of domain names.

## Types

`article`, `news`, `blog`, `docs`, `tutorial`, `thread`, `listing`, `table`,
`paper`, `pdf`, `product`, `spa`, `paywall`, `challenge`, `unknown`.

Tags (not types): `non_english`, `large`, `has_comments`, `has_code`,
`has_tables`, `xbrl`.

## Heuristics (ordered, cheap, no ML)

1. `challenge`: existing structural/title/phrase detection on raw HTML.
2. `paywall`/cookie wall: structural markers (`paywall`, `subscribe-wall`,
   `regwall`, consent overlay with blocking backdrop) plus a short visible body
   and login/subscribe copy. Must not fire on a long article that merely
   discusses paywalls; test both.
3. `pdf`: content-type or URL suffix/magic (plan 15 adds magic).
4. `xbrl`: IDEA/XBRL marker -> `table` with tag `xbrl`.
5. `spa`: very little visible text relative to script size, plus framework
   markers (`__NEXT_DATA__`, `id="root"`, `ng-app`, hydration scripts); if
   `rendered.html` differs substantially, prefer `spa`.
6. `thread`: repeated comment containers, HN/Stack Overflow markers, author +
   timestamp repetition, high link/comment density.
7. `listing`: repeated item/card links with little prose, search-result markup,
   pagination.
8. `table`: table text dominates visible text and numeric cells are frequent.
9. `paper`: arXiv/doi/abstract/references markers.
10. `docs`: docs navigation/sidebar plus many headings and code; `tutorial` if
    step/tutorial markers and code blocks dominate.
11. `news`: `NewsArticle`/`news` metadata or article + date/author/byline.
12. `blog`: `BlogPosting`/blog markers.
13. `article`: `<article>`/`main` plus headings/prose.
14. `unknown`: default; never guess a risky mode from a weak signal.

Use JSON-LD/schema.org when present, but do not require it. Keep thresholds in
one module with tests.

## Measurement

- Add `page_type` to `ReaderResult` and a `detect_page_type` function.
- Bench prints a confusion matrix against `meta.page_type` and overall accuracy
  per type; report exact numbers and per-type errors.
- This plan first ships detection as logging/measurement only. Routing in plans
  09/10/14 is enabled per type only where accuracy and benchmark results
  support it.
- If a type is misclassified too often, keep it `unknown` and say so; do not add
  brittle domain rules.

## Tests (`tests/test_page_types.py`)

- One positive and one hard negative per type (e.g., article about CAPTCHA,
  article mentioning paywalls, docs page with few code blocks).
- SPA raw shell vs rendered DOM.
- Non-English page still classified by structure, with `non_english` tag.
- `unknown` for ambiguous/minimal HTML.
- Determinism on repeated calls.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_page_types.py
.venv/bin/python scripts/bench_reader.py --page-type-report
.venv/bin/python -m pytest -q
```

Acceptance: confusion matrix and per-type accuracy are in the plan-08 note or
bench output; no behavior routing yet (or only behind a default-off flag);
default suite green.

## Risks / notes

- Detection is heuristic; false `thread`/`listing` modes can lose content.
  Prefer `unknown` over a confident wrong type.
- xbrl remains a tag on `table`; no finance-specific branch is added.
- Non-English detection must not use English-only keywords as the only signal.
