# Plan 13 - Configurable link policy and link hygiene

- **Workstream:** B4
- **Depends on:** plans 09, 10
- **Gate:** URL count preserved; navigation/footer/cookie links stripped;
  default policy benchmarked; per-call policy works end to end.

## Goal

Keep citations useful at the lowest token cost, with a policy the caller can
choose, and prove no unique source URL is lost by compaction.

## Policy

`links = sources | inline | none` (current default `sources`).

- `sources`: keep link labels inline, append unique HTTP(S) URLs once under
  `Sources:`, dedupe, cap by budget, add `[N source links omitted by the link
  cap]` when capped.
- `inline`: keep `[label](url)`; test-only/diagnostic, expensive.
- `none`: labels only; no URLs; add a marker that citations were removed.
- Strip `javascript:`, `mailto:`, `tel:`, `data:` and fragment-only links to
  labels; never emit them as sources.
- Resolve relative URLs against the page URL when possible; record unresolved
  counts.
- Per call: gateway `http_fetch` args, orchestrator `/fetch`, `WebLoaderRequest`
  optional `links`, and `smart_web` optional `links` argument. Default remains
  `sources`.

## URL preservation

For each fixture, compare the unique set of HTTP(S) URLs in the raw main
content (hand-marked or reader output) against the output body + Sources:

- no unique URL lost below the cap,
- duplicates removed,
- cap omission reported,
- navigation/footer/cookie-banner links absent from both body and Sources.

Report exact counts per fixture; do not claim "all links preserved" without the
comparison.

## Tests (`tests/test_links.py`)

- Labels stay in body; sources dedupe; relative URL resolution.
- `javascript:`/`mailto:`/`tel:`/fragment links stripped.
- Cap marker accurate; URL count equals min(unique, cap).
- Navigation/footer/cookie links stripped on a fixture with those regions.
- Configurable policy through gateway/orchestrator helper without a live
  server; one ASGI route test for the argument plumbing.
- Budget includes the Sources block and marker.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_links.py tests/test_reader.py
.venv/bin/python scripts/bench_reader.py --link-report --runs 3
.venv/bin/python -m pytest -q
```

Acceptance: URL-preservation report in the plan note; no unique URL lost under
the cap; default benchmark no worse; suite green.

## Risks / notes

- Sources can be the largest token block on citation-heavy pages; the cap is a
  budget decision, not "all sources". State the cap in the omission marker.
- Some pages have tracking URLs; do not rewrite URLs (except canonical header
  tracking parameters in plan 09) because citations must remain exact.
