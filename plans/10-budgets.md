# Plan 10 - Budgets by page type

- **Workstream:** B3 (ceilings)
- **Depends on:** plans 08-09
- **Gate:** page-type budgets measured on the corpus; no finance-specific
  domain table; existing explicit `max_chars` behavior preserved.

## Goal

Replace domain budgets with page-type ceilings that generalise beyond finance,
while keeping a deployment escape hatch and hard cap.

## Proposed ceilings (starting point, to be measured)

| Page type | Ceiling (chars) |
|---|---|
| article | 24,000 |
| news / blog / product / spa | 12,000 |
| docs | 12,000 |
| tutorial | 40,000 |
| thread | 16,000 |
| paper / pdf | 24,000 |
| table / data / xbrl | 24,000 |
| listing / search | 8,000 |
| paywall / challenge | 2,000 (message only) |
| unknown | 12,000 |
| hard maximum | 48,000 |

These are ceilings, not targets. Measure the minimum budget that retains all
ground-truth answers per fixture and set the ceiling with headroom, rather than
filling the cap.

## API

- `content_budget(url, requested=None, page_type=None)`; when `page_type` is
  known use the page-type ceiling, else `unknown`.
- Explicit `max_chars` is honoured up to the hard maximum (and the page-type
  ceiling); `0`/`None` means use the page-type ceiling.
- `READER_BUDGET_OVERRIDES` (JSON env) is an optional deployment escape hatch
  (for example a site that needs more); it is not a hardcoded domain table and
  is documented as a deployment choice.
- Remove the hardcoded finance domain table. XBRL remains a `table` tag with a
  larger ceiling.

## Measurement

- Bench scans budgets in 100-char steps per fixture; records the minimum budget
  for full ground-truth recall and the tokens at that budget.
- Compare old domain budgets vs new page-type budgets on the same corpus:
  tokens, P/R, fact presence, QA if enabled.
- If a page type needs more than the hard maximum, say so; do not silently
  truncate the answer.

## Tests

- Budget table per page type; unknown fallback; hard maximum; explicit request
  below/at/above ceiling; `0`/`None`/invalid; env override parsing; no
  finance-domain branch.
- Existing `test_content_budget_per_domain` is replaced with page-type
  expectations; note the intentional behavior change.
- A budget test asserts the output length never exceeds the resolved ceiling
  plus the truncation marker (and sources are included in the budget).

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_reader.py tests/test_budgets.py
.venv/bin/python scripts/bench_reader.py --runs 3 --budget-scan
```

Acceptance: measured budget table in the plan note; accuracy not worse; tokens
not worse at equal accuracy; default suite green.

## Risks / notes

- Page-type detection errors can under-budget a page; unknown defaults to the
  general 12k and the omission marker makes truncation visible.
- A deployment override is not a substitute for fixing the classifier; log
  overrides in `decision.md` if used.
