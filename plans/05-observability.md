# Plan 05 - Observability counters and silent-degradation warnings

- **Workstream:** D
- **Depends on:** none for the plumbing; can run alongside plan 01-04. Reason
  enums mark later features as reserved until they exist.
- **Gate:** counters, structured logs and audit detail are unit-tested; the
  Grafana dashboard parses; no full URL/query or PII is logged.

## Goal

Make loader degradation visible where the stack is already inspected
(Prometheus/Grafana, Tempo/Phoenix traces, `orchestrator.browser_audit`) instead
of relying on a user noticing a worse answer.

## Reason vocabulary

Add `reason` and `page_type` to `ReaderResult` (defaults preserve current
behavior until plans 08/15 populate them):

- `reader_ok`
- `reader_empty`
- `fallback_low_coverage`
- `structured_mode`
- `challenge_needs_human`
- `paywall` (reserved; populated when detection ships)
- `pdf_text` / `pdf_empty` (reserved)
- `binary_rejected` (reserved)
- `fetch_failed` (gateway-level)
- `cache_hit` (reserved)

Unknown/missing values are reported as `unknown`, never dropped.

## Counters and logs

Add `shared/metrics.py` with thread-safe counters and sum/count summaries and a
Prometheus text exposition helper. No third-party metrics dependency.

Gateway (`:8000`) and orchestrator (`:8080`) expose `/metrics` on their internal
ports only:

- `web_loader_loads_total{service,reason,page_type,method}`
- `web_loader_tokens_total{service,direction}` (sum)
- `web_loader_chars_total{service,kind}` (sum/count)
- `web_loader_cache_lookups_total{service,result}` (reserved until plan 11)
- `web_loader_fetch_failures_total{service,error_class}`
- `web_loader_reader_empty_large_total{service}`

Labels must stay low-cardinality: no URL, query, host or agent id.

Structured JSON log line per load (stdlib logging, no PII):

```json
{"event":"web_loader_load","service":"gateway","reason":"reader_ok",
 "method":"reader","page_type":"article","chars_in":180000,"chars_out":12000,
 "tokens_in":45000,"tokens_out":3000,"tokenizer":"tiktoken-cl100k",
 "truncated":false,"source_count":12,"cache_hit":false,"duration_ms":42,
 "host":"example.com"}
```

`host` is the only URL component logged; no path/query. Token counts are
model-facing proxies, labelled with the tokenizer; they are not provider usage
(provider usage stays in LiteLLM/Phoenix).

Alert-worthy line:

```text
reader_empty_large_page host=... raw_chars=... content_type=... reason=reader_empty
```

Emitted at WARNING when the extractor returns empty, the raw document exceeds
`READER_EMPTY_ALERT_CHARS` (default 200000), and the page is not a detected
challenge/paywall. Increment `web_loader_reader_empty_large_total`.

## Audit table

Store the same fields as JSON in `orchestrator.browser_audit.detail`; keep
`status` values (`allowed`, `challenge`, `denied`, `approval_required`)
unchanged. No schema migration until a query needs an indexed `reason` column;
log that decision.

## OTel

When the OTel SDK is already configured, set span attributes/events
(`web_loader.reason`, `page_type`, `tokens_out`, `truncated`, `cache_hit`).
Do not add a hard OTel dependency to `shared/`.

## Grafana

Add `observability/grafana/dashboards/ai-stack-web-loader.json` with panels for
reasons, tokens in/out, fetch failures, empty-large-page and cache hit rate.
Add `safeguard-gateway` and `orchestrator` scrape jobs to
`observability/prometheus/prometheus.yml`. Validate the JSON in tests.

## Tests

- `tests/test_metrics.py`: counter/label rendering, reset isolation, no
  high-cardinality labels.
- `tests/test_observability.py`: caplog JSON fields, alert condition and
  non-trigger for challenge pages, audit `detail` via a stub, token counter
  fallback (monkeypatch tiktoken missing), no full URL/query/email in logs.
- Gateway `/metrics` via ASGI transport returns `text/plain` and includes
  expected names.
- Existing suite passes; no network.

## Steps

1. Add `shared/metrics.py`, `shared/tokens.py`, `ReaderResult.reason`.
2. Instrument gateway `_http_fetch` and orchestrator `/fetch`/`/web-loader`;
   add `/metrics`.
3. Add audit detail and structured logs; alert line.
4. Add Prometheus jobs and dashboard.
5. Add tests and a runbook stub for the new counters (full runbook in plan 21).

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_metrics.py tests/test_observability.py
.venv/bin/python -m pytest -q
```

Acceptance: counters and logs are correct in unit tests, no PII, dashboard JSON
parses, and a reader failure on a large page produces the warning.

## Risks / notes

- Multi-worker processes have per-process counters; Prometheus sums them. Do
  not present them as global without that caveat.
- tiktoken is a proxy for DeepSeek; label it. Do not put tiktoken on the hot
  path without caching/size limits.
- Logging cost is trivial compared with extraction; do not log page text.
