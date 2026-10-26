# Plan 06 - Regression stability, test markers and minimal Makefile

- **Workstream:** C1
- **Depends on:** plan 01 (fixtures); plan 05 optional for metrics
- **Gate:** 20+ repeated calls on the same HTML are stable offline; default
  suite stays fast and green; `make verify` exists.

## Goal

Lock in the trafilatura `deduplicate=True` regression (stateful empty output
after repeated calls) and stop the default suite from accidentally depending on
network/LLM tests.

## Tests

`tests/test_reader_stability.py`:

1. **Default fast:** 25 repeated `read_html` calls on a medium-large pinned
   fixture (target 150-400 KB) with the real trafilatura path. Assert every
   result is non-empty, `method` is stable, and text hashes are identical.
   Target runtime under 5 seconds; if it exceeds that on the dev machine, keep
   the 25-call test but mark it `slow` and add a 10-call fast variant.
2. **Large/slow:** 25 calls on the >1 MB fixture, marked `slow`; assert
   non-empty/stable and report runtime. Run with `--run-slow`.
3. **No stateful dedup:** assert the configured extractor has
   `deduplicate=False`; a source-level guard test makes the reason explicit.
4. **Fallback boundary is not triggered by repeats:** assert method does not
   drift from `reader` to `tag-strip` across calls.

## Test selection

Use explicit conftest options instead of a fragile `addopts -m`:

- markers: `network`, `llm`, `slow`.
- default: skip `network` and `llm`; `slow` runs by default only if it stays
  under the fast budget, otherwise skip unless `--run-slow`.
- options: `--run-network`, `--run-llm`, `--run-slow`.
- `pytest -q` remains the fast default; `pytest -q --run-slow` includes heavy
  offline tests. Document in README (plan 21).

## Minimal Makefile

Create a small `Makefile` now so every later plan can run `make verify`:

```make
PY ?= .venv/bin/python
RUFF ?= .venv/bin/ruff

.PHONY: test lint fmt verify
test:
	$(PY) -m pytest -q
lint:
	$(RUFF) check .
fmt:
	$(RUFF) format .
verify: lint test
```

Do not add `ruff format --check` to `verify` until the repo-wide format commit
in plan 20; before that it would fail on pre-existing drift. Plan 20 extends
this file with bench/up/down/docs/privacy targets.

## Verification

```bash
make verify
.venv/bin/python -m pytest -q --run-slow tests/test_reader_stability.py
.venv/bin/python -m pytest -q --run-network   # should collect none/only marked
```

Acceptance: 25/25 stable on the medium fixture; large fixture stable under
`--run-slow`; default suite unchanged in count except new fast tests; no
network.

## Risks / notes

- 25 calls on >1 MB can take several seconds; keep it opt-in so the default
  suite stays useful.
- The regression can reappear if any future config sets `deduplicate=True`;
  the guard test is intentionally explicit.
