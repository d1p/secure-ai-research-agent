---
title: Reader loader - final measured results (corpus v1)
date: 2026-10-26
status: draft
commit_tested: working tree after plans/01-21 implementation
environment: Python 3.13.5; trafilatura 2.3.1; lxml 6.1.3; tiktoken cl100k_base; 21 offline fixtures; 3 runs
---

# Reader loader - final measured results (corpus v1)

## TL;DR

- The loader now classifies **21/21** corpus pages correctly, preserves
  title/description/canonical context, keeps tables/code/lists, has a thread
  mode, extracts PDFs with page markers, rejects binary cleanly, strips hidden
  comments, wraps page text as untrusted, caches HTTP fetches, and budgets
  sub-agent output.
- Accuracy improved where the old loader was weak: Wikipedia/large article
  evidence went from 15/17 to **17/17**, tutorial from 2/4 to **4/4**, PDF from
  0/4 to **4/4**. This cost tokens on long pages because the page-type ceilings
  are higher (article 24k, tutorial 40k); the old 12k caps simply could not hold
  the answers.
- **We still lose one paper fact at the 24k paper ceiling** (`over 4,000
  prompts` sits at ~51k in the extracted paper). Progressive/query loading is
  implemented as an opt-in (`mode=outline|section|query`) but is **not the
  default** because it has no A/B win yet.
- Product/SPA evidence scores (2/4, 3/4) are partly proxy artifacts: the
  bag-of-words evidence check does not match table labels (`Warranty | 2 years`)
  to the reference wording. They are not LLM-graded accuracy.
- **LLM-graded answer accuracy and the live agent A/B were not run** in this
  environment (no benchmark credentials on the host). The note says so; no
  token/accuracy claim beyond the offline metrics.

## Method

- Corpus: `tests/fixtures/` (21 pinned pages; synthetic categories labelled).
- Runs: 3 per extractor; tokenizer tiktoken `cl100k_base` (proxy).
- Budget: resolved page-type ceiling; not full output.
- Precision/recall: word-multiset overlap against `reference.md`.
- Evidence presence: >=80% of a question's evidence tokens in the output
  (bag of words). This is a recall proxy, not answer accuracy.
- No LLM grading (`--grade`), no live A/B.

## Per-page-type best on this run

Selected by evidence presence first, then tokens. This is not a final config
switch where the metric is a proxy.

| Page type | Best | Evidence | Tokens | Note |
|---|---|---:|---:|---|
| article | `reader-precision` | 17/17 | 6,420 | article ceiling 24k; long pages need it |
| blog | `readability` | 4/4 | 904 | reader 4/4 at 987 |
| docs | `reader-precision` | 8/8 | 2,872 | docs ceiling 12k |
| listing | `tag-strip` | 4/4 | 93 | reader 4/4 at 122 |
| news | `readability` | 4/4 | 517 | reader 4/4 at 623 |
| paper | `tag-strip` | 4/4 | 6,527 | reader 3/4 at 6,592 (deep fact beyond ceiling) |
| pdf | `reader-default` | 4/4 | 7,142 | page markers + text |
| product | `reader-no-tables` | 2/4 | 83 | proxy artifact; reader 2/4 at 112 |
| spa | `tag-strip` | 3/4 | 39 | rendered path; reader 3/4 at 68 |
| table | `readability` | 9/9 | 3,253 | reader 9/9 at 8,439; table mode for XBRL |
| thread | `tag-strip` | 13/13 | 2,084 | thread mode 13/13 at 2,416, better structure |
| tutorial | `stagehand-innertext` | 4/4 | 9,382 | reader 4/4 at 10,198 (40k ceiling) |
| paywall/challenge | excluded | - | - | judged by clean refusal, not P/R |

## Default reader per fixture (one run of three)

| Fixture | Evidence | Tokens |
|---|---:|---:|
| blog-longform-cc | 4/4 | 987 |
| captcha-mention | 4/4 | 6,218 |
| challenge-bot | 0/3 (refusal) | 0 |
| data-table | 5/5 | 8,439 |
| docs-reference | 4/4 | 2,918 |
| forum-hackernews | 5/5 | 3,245 |
| github-issue | 4/4 | 966 |
| github-readme | 4/4 | 2,847 |
| large-page | 5/5 | 6,434 |
| listing-search | 4/4 | 122 |
| news-public-domain | 4/4 | 623 |
| non-english | 4/4 | 6,863 |
| paper-arxiv-html | 3/4 | 6,592 |
| paper-arxiv-pdf | 4/4 | 7,142 |
| paywall-cookie | 0/3 (refusal) | 20 |
| product-reviews | 2/4 | 112 |
| qa-stackoverflow | 4/4 | 3,036 |
| spa-rendered | 3/4 | 68 |
| tutorial-code | 4/4 | 10,198 |
| wikipedia-encyclopedia | 4/4 | 6,413 |
| xbrl-statement | 4/4 | 104 |

## Baseline -> final

| Page type / fixture | Before (baseline note) | After | Change |
|---|---|---|---|
| article aggregate | 16/17; 3.2k tok (`reader-precision`) | 17/17; 6.4k tok | accuracy fixed; tokens up with 24k ceiling |
| large-page | 0/5 at 12k | 5/5 at 24k | accuracy fixed |
| non-english | 2/4 before header/budget | 4/4 at 24k | accuracy fixed |
| tutorial | 2/4 at 12-16k | 4/4 at 40k | accuracy fixed; expensive |
| PDF | 0/4 (not implemented) | 4/4; 7.1k | new |
| thread | 3/4-4/4 reader | 13/13 aggregate; structured thread | structure + accuracy |
| XBRL | table mode; proxy 0/4 | 4/4 table questions | metric + format |
| paper | 3/4 | 3/4 at 24k | **still loses one deep fact** |
| product/SPA | 1-3/4 | 2-3/4 | proxy artifacts; QA not measured |

## What changed (behavior)

- Page-type detection and page-type ceilings (no finance domain table).
- Context header; duplicate leading heading removed.
- Thread mode (HN/Stack Exchange/generic) with author/order/depth, low-signal
  collapse, quote stripping and caps.
- PDF extraction with `[page N]` markers; encrypted/no-text/corrupt/binary
  clean messages.
- Link policy per call; source-cap marker; navigation/footer/cookie links
  stripped.
- Hidden nodes/comments stripped; untrusted-content wrapper at service boundary.
- TTL HTTP cache (gateway) with `no-store`/`no-cache` bypass; sub-agent
  cumulative output budget and `budget_exceeded` marker.
- Counters/logs: reasons, methods, page types, chars/tokens, cache, failures,
  empty-large-page warning; `/metrics` + Grafana dashboard.
- Tests: 197 passed, 1 skipped (before: 104 passed). Golden snapshots,
  fixtures, ground truth, fuzz, gateway reliability, injection, PDF, cache,
  thread, budget, page type and privacy tests.

## What was tried and rejected / not shipped

- `reader-no-tables` looked cheaper on table pages under the bag-of-words
  proxy; rejected because it removes table structure and the proxy can be
  satisfied by adjacent prose.
- `readability` wins news/blog tokens on this run, but losing deep facts on
  other page types keeps it a candidate, not the default.
- Progressive outline/section/query loading: implemented opt-in
  (`mode=...`, default `full`), **not enabled by default** because no A/B
  showed fewer total tokens at equal accuracy. It is the likely fix for the
  paper 3/4 and expensive tutorial/table budgets.
- Orchestrator browser-path cache: not shipped; only the gateway HTTP cache is
  implemented. Repeated `browse_page` calls still navigate.
- No finance-specific logic; XBRL remains a table page with a larger ceiling.

## Not measured

- LLM-graded answer accuracy (needs LiteLLM/provider credentials).
- Live agent-level A/B old vs new (`scripts/bench_ab.sh`; needs deployed
  services). Total-token and success-rate claims are therefore not made.
- Pre-commit, GitHub Actions, `pip-audit`, `npm audit` and markdown link check
  were not executed here (no node/docker/network in this shell); configs parse.
- PDF OCR, scanned PDFs; encrypted PDFs return a clean refusal.

## Reproduction

```bash
.venv/bin/python scripts/bench_reader.py --runs 3 \
  --json /tmp/bench-final2.json --markdown /tmp/bench-final2.md
.venv/bin/python scripts/bench_reader.py --page-type-report
.venv/bin/python scripts/repro_trafilatura_dedup.py --fixture docs-reference --calls 8
pytest -q
```

Data source: `/tmp/bench-final2.json` from the run on 2026-10-26; fixtures and
hashes are committed. Baseline comparison: `notes/reader-benchmark-2026-10-26.md`.
