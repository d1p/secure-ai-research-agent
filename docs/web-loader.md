# Web loader reference

The loader turns an HTML page (plain HTTP fetch or rendered DOM) into model-facing
Markdown. It lives in `shared/reader.py`; gateway/orchestrator call it so both
paths share behavior.

## Pipeline

1. Fetch bytes (SSRF/redirect/DNS validation in the gateway).
2. Classify content: HTML, PDF, text/JSON/XML, or binary.
3. Detect page type: `article`, `news`, `blog`, `docs`, `tutorial`, `thread`,
   `listing`, `table`, `paper`, `pdf`, `product`, `spa`, `paywall`,
   `challenge`, `unknown`.
4. Refuse challenge/paywall pages cleanly; extract PDFs with page markers;
   reject binary with a short message.
5. Extract reader/thread/table content; remove hidden nodes and HTML comments.
6. Prepend title/h1/meta description/canonical URL; preserve tables, code and
   lists where available.
7. Apply the page-type character ceiling (a ceiling, not a target), compact
   links, and append a `Sources:` footer.
8. Log/metric the reason, method, tokens/chars and duration; wrap the text as
   untrusted page content at the service boundary.

## Page-type ceilings

| Page type | Chars |
|---|---:|
| article | 24,000 |
| news, blog, product, spa, unknown | 12,000 |
| docs | 12,000 |
| tutorial | 40,000 |
| thread | 16,000 |
| paper, pdf, table | 24,000 |
| listing | 8,000 |
| paywall, challenge | 2,000 (refusal message) |
| hard maximum | 48,000 |

`READER_BUDGET_OVERRIDES` is a JSON deployment escape hatch keyed by host
suffix, e.g. `{"example.com": 20000}`. It is not a domain allowlist.

## Refusals

- `challenge_needs_human`: bot/CAPTCHA/Cloudflare challenge; gateway returns
  `needs_human` and the human resolves it via noVNC.
- `paywall`: paywall/login wall; loader returns a short `[paywall]` message,
  never the overlay text as an article.
- `binary_rejected`: binary content is not decoded into the model.
- PDFs with no text return `[pdf has no extractable text; OCR is not supported]`.

## Link policy

`links=sources|inline|none` per call (default `sources`):

- `sources`: labels stay inline, unique HTTP(S) URLs appear once under
  `Sources:`, capped by budget; omitted URLs are counted in a marker.
- `inline`: full Markdown links (diagnostic; expensive).
- `none`: labels only.

`javascript:`, `mailto:`, `tel:`, `data:` and fragment links are never sources.
Navigation/footer/cookie links are removed by the extractor; citation URLs are
not rewritten.

## Cache

`http_fetch` uses a short process-local TTL cache keyed by URL, budget and link
policy. `cache=0` bypasses it. `Cache-Control: no-store` and `no-cache` responses
are not stored. The cache does **not** reduce the tokens of text the model reads;
it reduces network/parse/latency cost. Process-local means gateway and
orchestrator do not share entries.

Environment: `WEB_LOADER_CACHE_TTL` (default 300 s), `WEB_LOADER_CACHE_SIZE`
(default 128 entries).

## Output budget for sub-agent runs

`shared/budget.py` tracks cumulative tool-output chars per run id
(`SUBAGENT_OUTPUT_BUDGET_CHARS`, default 150000; TTL
`SUBAGENT_OUTPUT_BUDGET_TTL`, default 900 s). The gateway/orchestrator return
`[budget_exceeded] ...` instead of more page text; the model should summarize.
`X-Run-Id` is forwarded from the Open WebUI tool when metadata provides a stable
session/chat id; otherwise an agent-scoped TTL window applies.

## Observability

Structured line: `web_loader_load` with `reason`, `method`, `page_type`,
`chars_in/out`, `tokens_in/out`, `tokenizer`, `truncated`, `source_count`,
`cache_hit`, `duration_ms`, `host` (no path/query).

Prometheus series (gateway/orchestrator `/metrics`):

- `web_loader_loads_total{service,reason,page_type,method}`
- `web_loader_tokens_sum/_count{service,direction}`
- `web_loader_chars_sum/_count{service,kind}`
- `web_loader_fetch_failures_total{service,error_class}`
- `web_loader_reader_empty_large_total{service}`
- `web_loader_cache_lookups_total{service,result}`
- `web_loader_budget_exceeded_total{service}`

Alert-worthy line: `reader_empty_large_page` when the reader returns empty on a
raw page above `READER_EMPTY_ALERT_CHARS` (default 200000) that is not a
challenge/paywall.

## Counters are proxies

Runtime tokens use tiktoken `cl100k_base` when installed, otherwise chars/4.
They are labelled proxies, not DeepSeek/provider usage. Provider usage stays in
LiteLLM/Phoenix.

## Progressive loading

`mode=outline|section|query` is implemented as an **opt-in** view
(`offset`/`length`/`query`). The default remains `full`. No A/B has shown fewer
total tokens at equal accuracy yet, so do not enable it by default or claim a
saving. Section requests may re-fetch until a full-text cache is added.
