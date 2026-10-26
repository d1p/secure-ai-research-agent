# Plan 16 - Cumulative sub-agent tool-output budget

- **Workstream:** B8
- **Depends on:** plans 05, 11, 12; Open WebUI sub-agent behavior
- **Gate:** cumulative budget forces a summarize marker, resets per run/new
  run id, and does not break a normal short run. Agent-level savings are only
  claimed if measured.

## Goal

Bound total tool output per sub-agent run, not just the 40-iteration count, so
a model that keeps fetching cannot grow context without limit.

## Design

- `shared/budget.py`: thread-safe `OutputBudget` keyed by run id, TTL (for
  example 15 min), cumulative chars/tokens, configurable ceiling
  `SUBAGENT_OUTPUT_BUDGET_CHARS` (default conservative; measure before setting).
- Gateway `/execute` accepts optional `X-Run-Id`. For `http_fetch`,
  `stagehand_content` and `stagehand_read`, consume the returned text before
  sending it. When the ceiling is crossed, return a short result:
  `[budget_exceeded] Tool-output budget reached; summarize what you have and stop fetching.`
  with `budget_exceeded: true`; do not return the page body.
- Orchestrator forwards `X-Run-Id` to the gateway and applies the same check to
  `/fetch` and `/web-loader`.
- `smart_web` derives a run id from Open WebUI `__metadata__` (stable chat/
  session id + a TTL window) when available and sends it. When metadata is
  missing, the gateway falls back to a per-agent sliding window
  (`OUTPUT_BUDGET_SCOPE=agent`) so the cap still applies.
- Update the sub-agent system prompt: after a budget marker, summarize and stop.
  The marker is the enforcement; prompt text alone is not.
- Reset: a new run id starts a fresh budget; TTL expiry starts fresh. Record run
  id as a hash, not raw metadata, to avoid PII in logs.

## Tests (`tests/test_budget.py`)

- Under ceiling: multiple outputs pass; accumulator counts chars/tokens.
- Crossing ceiling: next call gets marker, no body; subsequent calls stay
  blocked.
- New run id resets; TTL expiry resets; agent-scope fallback works.
- Concurrent calls do not lose counts (thread/async safety).
- Gateway route returns `budget_exceeded` and audit/log fields; no full URL/PII.
- Orchestrator forwarding and `/fetch` behavior with a stub gateway.
- A normal 5-call run is unaffected.

## Agent-level measurement

Run the same sub-agent task N times with the budget off/on (plan 19 live A/B or
a controlled Open WebUI run). Report total tool-output chars/tokens, tool calls,
answer success and variance. If not run, label the end-to-end effect "not
measured"; unit behavior is still verified.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_budget.py
.venv/bin/python -m pytest -q
```

Acceptance: cap and reset tests pass; normal run unaffected; no raw metadata or
PII logged; default suite green.

## Risks / notes

- Open WebUI metadata may not expose a stable sub-agent run id. The
  agent-scoped TTL fallback is a coarser approximation; document it.
- A too-low ceiling can cut off a legitimate long research task; make it
  configurable and measure before choosing a default.
- Returning a marker is a forced summarize step, not a guarantee the model
  obeys; it cannot fetch more content through the capped tools.
