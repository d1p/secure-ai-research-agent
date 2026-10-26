# Testing

## Default suite

```bash
make verify                 # lint + privacy + tests + compose config (if docker)
pytest -q
```

The default suite is offline and excludes `network`, `llm` and `slow` markers.
Opt in explicitly:

```bash
pytest -q --run-slow
pytest -q --run-network
pytest -q --run-llm
```

## Fixtures

`tests/fixtures/` holds pinned pages and metadata; see its README. Do not
silently refresh them. Add a fixture with `scripts/capture_fixtures.py
--allow-network --only <slug>`, add questions in `scripts/build_questions.py`,
then run:

```bash
pytest -q tests/test_fixtures.py tests/test_ground_truth.py
```

Ground truth questions are answered from the page/reference, not from the
current extractor. Each fixture has 3-5 questions, including a deep answer and
a structured (table/list/code/comment) answer where the page supports it.

## Golden snapshots

`tests/test_golden.py` compares extraction output. Intentional changes require:

```bash
UPDATE_GOLDEN=1 pytest tests/test_golden.py
git diff tests/golden
```

Review the diff before accepting it; a version bump in the golden header means
the parser changed.

## Fuzz/property tests

`tests/test_properties.py` uses hypothesis: malformed HTML never raises, output
honors the budget and repeated calls are deterministic. Keep example counts
modest so the default suite stays fast.

## Network/LLM tests

These are not run by default. The agent-level A/B is `scripts/bench_agent.py`
plus `scripts/bench_ab.sh`; it needs deployed services and provider credentials.
Report "not measured" if it was not run.
