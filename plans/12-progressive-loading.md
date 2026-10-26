# Plan 12 - Progressive loading (outline, offset, query excerpt)

- **Workstream:** B3 (progressive loading)
- **Depends on:** plans 10-11
- **Gate:** A/B shows fewer total tokens at equal or better answer accuracy.
  If not, remove the feature and log the rejection.

## Goal

Let the agent pay only for the section it needs on large pages, instead of
receiving a truncated full-page blob that may miss the answer.

## API

- `read_html(..., mode="full"|"outline", offset=0, query=None)`.
- `outline`: header + heading tree with character offsets + the first N chars
  (for example 2,000), plus a marker explaining how to request a section.
- `section`: `offset` + `length` into the cached full extracted text.
- `query`: score paragraphs/sentences by query-term overlap with local context,
  return the top K under the budget, plus `[excerpt for query=...]`. No LLM, no
  new dependency; deterministic tie-breaking.
- Gateway `http_fetch` accepts `mode`, `offset`, `length`, `query`; the
  orchestrator `/fetch` passes them through. `/web-loader` and `browse_page`
  get `query`/`offset` only if the browser path benchmark supports it.
- `smart_web` docstrings and the router/system prompt explain the option in one
  short rule; do not encourage extra calls for small pages.
- Page-type policy: allow progressive mode for `paper`, `docs`, `thread`,
  `table` and `large` pages; keep full mode for short articles by default.

## Adoption test

Run the same research tasks on the corpus (or live A/B in plan 19) three ways:

1. full page at the page-type budget,
2. outline + one section request,
3. query-focused excerpt.

Compare total model tokens (including the extra tool call), tool-call count,
answer accuracy and spread. Adopt only if a progressive mode uses fewer total
tokens at equal or better accuracy for at least one page type. State per-type
results; do not generalize a win on one large paper to all pages.

## Tests

- Outline offsets round-trip: requesting `offset`/`length` returns the expected
  substring; no off-by-one.
- Query excerpt contains the answer for table/code/comment questions in
  fixtures; deterministic output; budget respected.
- No-match query falls back to outline/first N chars with a clear marker.
- Cache hit means no refetch; cache miss/refetch is logged and measured.
- `mode=full` is unchanged; default remains full until the benchmark adopts a
  per-type default.
- Omission/truncation markers mention the actual available options.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_progressive.py
.venv/bin/python scripts/bench_reader.py --progressive --runs 3
.venv/bin/python -m pytest -q
```

Acceptance: correctness tests pass; the benchmark table is in the plan note;
the feature is enabled only for page types where it wins, or removed.

## Risks / notes

- Extra tool calls can cost more tokens than they save; measure total, not just
  page output.
- Query excerpts can miss answers outside the top K; keep the full/section
  escape hatch and mark omissions.
- Do not use an LLM to choose sections in this plan; that adds cost and
  nondeterminism.
