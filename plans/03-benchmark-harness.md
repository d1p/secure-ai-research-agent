# Plan 03 - Benchmark harness

- **Workstream:** A3
- **Depends on:** plans 01-02
- **Gate:** one offline command produces the per-page-type table, JSON and
  spread; the default test suite still passes.

## Goal

Turn `scripts/measure_reader.py` into a reproducible comparison harness for
extractors/configs, with metrics that can judge every later loader change.

## Extractors and configs

Keep the grid small and honest:

| Name | What it is |
|---|---|
| `reader-default` | current `read_html` / trafilatura settings |
| `reader-recall` | `favor_recall=True`, tables on |
| `reader-precision` | `favor_precision=True`, tables on |
| `reader-no-tables` | tables off, to measure table loss |
| `reader-comments` | comments on, for thread pages |
| `reader-links-inline` | inline links instead of sources |
| `readability` | readability-lxml summary -> Markdown/text |
| `tag-strip` | current regex tag-strip baseline |
| `stagehand-innertext` | captured `innertext.txt` (browser path) |

- Add a `ReaderConfig` dataclass to `shared/reader.py` (favor recall/precision,
  tables, comments, links, deduplicate) with the current values as defaults.
  `read_html(..., config=None)` must behave exactly as today; existing tests
  are the guard.
- `readability` conversion uses `readability-lxml` + `markdownify` (new
  benchmark/dev deps; logged in `decision.md`). If either is missing, that
  extractor is reported as skipped, not a failure.
- `stagehand-innertext` reads the captured text; it does not start a browser.
  Non-browser captures are labelled.

## Metrics

1. **Tokens:** DeepSeek tokenizer if `tokenizers` can load a pinned
   `tokenizer.json`; otherwise tiktoken `cl100k_base`; otherwise chars/4. The
   output records the tokenizer name and version. Never mix tokenizers in one
   comparison.
2. **Main-content precision/recall:** normalise (NFKC, lowercase, collapse
   whitespace, strip Markdown/HTML punctuation), then compare word multisets
   against `reference.md`:
   - precision = matched extracted words / extracted words (penalises
     boilerplate),
   - recall = matched reference words / reference words (penalises omissions).
   Report both, per fixture and per page type. For sample-scoped references,
   label the result.
3. **Question-answer accuracy (optional, off by default, cached):** with
   `--grade`, ask the benchmark model (LiteLLM; default `deepseek-flash`,
   temperature 0) to answer each question using only the extracted text
   ("NOT_FOUND" if absent), then grade the answer against ground truth. Cache
   both calls by hash of model + prompt version + fixture + config + question.
   Record model, prompt version and cache location. `--no-cache` bypasses.
4. **Spread:** N runs per fixture/config (default 3). Extraction should be
   deterministic; record min/median/max tokens and P/R, and a hash of each
   output. If hashes differ, report instability instead of hiding it.
5. **Context:** fixture, page type, budget, method, truncated, source count,
   chars in/out.

Fact-presence (evidence substring) is reported separately from LLM-graded
accuracy and is never called "accuracy".

## Output

- Markdown: one table per page type, then a per-fixture appendix.
- JSON: full results plus a `meta` block (date, commit, tokenizer, Python,
  trafilatura/lxml versions, runs, extractor versions, prompt version).
- `--json PATH` and `--markdown PATH`; stdout remains readable.
- Later plans add report modes (`--page-type-report`, `--budget-scan`,
  `--link-report`, `--progressive`) through the same extractor/config registry;
  they must not fork the runner.
- `scripts/measure_reader.py` becomes a thin compatibility wrapper or is
  removed in favour of `scripts/bench_reader.py`; update docs links.

Example commands:

```bash
.venv/bin/python scripts/bench_reader.py --runs 3 --json /tmp/bench.json
.venv/bin/python scripts/bench_reader.py --fixtures qa-stackoverflow,forum-hackernews \
  --extractors reader-default,reader-comments,tag-strip --runs 3
.venv/bin/python scripts/bench_reader.py --grade --runs 1 --fixtures wikipedia-encyclopedia
```

## Dependencies

Benchmark/dev only unless a later plan proves otherwise: `readability-lxml`,
`markdownify`, `tokenizers`, `hypothesis` (tests), `pytest-asyncio` (gateway
tests). Runtime token counting uses tiktoken or chars/4. Every new dependency
gets a reason in `decision.md`.

## Steps

1. Add the fixture loader helper (transparent `.html.gz`, `.pdf`, meta) used by
   scripts and tests.
2. Add `ReaderConfig` with defaults unchanged; add config-aware extraction.
3. Implement extractors, metrics, cache and Markdown/JSON output.
4. Add a fast offline smoke test for the harness (one fixture, two extractors,
   one run) and keep it in the default suite.

## Verification

```bash
.venv/bin/python scripts/bench_reader.py --fixtures wikipedia-encyclopedia \
  --extractors reader-default,tag-strip --runs 2
.venv/bin/python -m pytest -q
```

Acceptance: the smoke run is reproducible, reports the tokenizer, uses no
network, and the baseline suite still passes.

## Risks / notes

- LLM grading costs money and is nondeterministic; it is opt-in and cached.
  Answerer/grader prompts must not see the ground-truth answer while
  answering.
- readability-lxml is a candidate, not a production dependency unless it wins.
- DeepSeek tokenizer download is network-only and recorded; the fallback is
  clearly labelled.
