# Decisions and findings

Append-only. Newest at the bottom. Keep entries short and link plans/notes.
Never put secrets, personal emails, internal IPs or internal hostnames here.

## 2026-10-26

- **Surprise:** repo guidance files `agent.md` and `decision.md` were absent at
  HEAD `8d51cf3`. Started this log; used `README.md` plus the host-level
  `AGENTS.md` for conventions. If an `agent.md` exists outside the repo,
  reconcile it before executing.
- **Baseline (measured):** Python 3.13.5, trafilatura 2.3.1, lxml 6.1.3.
  `.venv/bin/python -m pytest -q` -> **104 passed**; `.venv/bin/ruff check .`
  -> clean. `.venv/bin/ruff format --check .` reports **16 files** would be
  reformatted (pre-existing drift); format repo-wide in an isolated commit
  before enforcing format.
- **Planning only:** no loader, test, fixture or doc behavior changed yet.
  Plans live in `plans/`; work stops for approval.
- **Corpus licensing:** prefer public-domain/CC/OSS sources; use synthetic,
  clearly labelled fixtures where a real capture's license is unclear
  (product page, paywall, bot challenge, search listing). Scrub emails, phone
  numbers and private IPs from stored fixtures; record source URL, capture
  date, license and capture method.
- **Fixture scope:** use Hacker News + Stack Overflow for forum/Q&A
  (predictable licenses); do not depend on Reddit. Keep one XBRL fixture as a
  data-table page, not a finance workstream.
- **Token accounting:** use the DeepSeek tokenizer if it can be fetched and
  pinned; otherwise tiktoken `cl100k_base`; label every number with the
  tokenizer. Never compare counts from different tokenizers. Runtime counters
  may use a tiktoken/chars-4 proxy, labelled.
- **Observability:** prefer Prometheus counters via a new internal `/metrics`
  endpoint plus structured JSON logs and audit `detail` JSON. No DB migration
  until a query needs a `reason` column. Add OTel span attributes where the SDK
  is already available.
- **Finance:** no new finance-specific logic. XBRL is one page type;
  budgets/routing generalise by page type, with optional deployment env
  overrides.
- **Rejected:** LLM summarisation inside the loader (cost, nondeterminism);
  browser-only loading (slower, more tokens); storing untrimmed third-party
  pages (license/size); adding heavy parser deps to production unless a
  benchmark or content type requires them. PDF support (`pypdf`) is the
  exception because PDF is a first-class input.
- **Progressive loading:** design now, adopt only if the A/B shows fewer total
  tokens at equal or better answer accuracy.
- **Cache order:** implement the fetch/extraction cache before progressive
  loading (plans run 11 then 12) so section requests can be served without a
  refetch; otherwise progressive loading could fail the token test for the
  wrong reason.
- **Legacy loader:** keep only behind a benchmark-only `LOADER_VARIANT=legacy`
  path for the A/B; not a supported deployment mode.
- **Open question for approval:** whether to run the end-to-end A/B against
  live pages/services (needed for true agent-level token and accuracy numbers),
  or ship the offline loader benchmark and label end-to-end numbers as not
  measured until a later run.
- **Planned dependencies (not installed yet):**
  - `readability-lxml` + `markdownify`: benchmark candidates and dev only; a
    fair structural comparison against trafilatura. Remove if they lose.
  - `tokenizers`: benchmark only, to load a pinned DeepSeek tokenizer; tiktoken
    is the fallback and runtime proxy.
  - `pypdf`: runtime PDF text extraction (plan 15); lazy-imported because PDF is
    a first-class research input and trafilatura cannot read PDFs.
  - `tiktoken`: runtime token counter proxy in gateway/orchestrator (plan 05);
    lazy/cached, with a chars/4 fallback when absent.
  - `hypothesis`, `pytest-asyncio`: test-only for fuzz and async gateway tests.
  - `redis`: not added speculatively; only if measured cross-process cache
    misses justify it (plan 11).
  - pre-commit/CI tools: dev-only; pinned revisions/SHAs.
- **Baseline benchmark (measured, 2026-10-26):** 21 fixtures, 3 runs,
  tiktoken cl100k, evidence-token presence (not LLM accuracy). Pre-change
  results and provisional per-page-type winners are in
  `notes/reader-benchmark-2026-10-26.md`. LLM-graded accuracy and PDF extraction
  were **not measured**; the note says so.
- **Bug found during corpus capture:** the CAPTCHA Wikipedia article was
  classified as a bot challenge because the structural regex matched any
  `captcha` class. Removed the generic `captcha` marker; true challenge markers
  (`cf-challenge`, `challenge-form`, `g-recaptcha`, etc.) remain. The article
  now extracts 4/4 evidence. This is a behavior fix, not a finance rule.
- **Metric caveat:** bag-of-words evidence presence can be satisfied by prose
  near a table, so `reader-no-tables` appearing cheaper on table pages is not a
  reason to remove tables. Table-aware QA/tests are required before adopting.
- **Provisional winners:** article/docs `reader-precision`; blog/listing/thread
  `reader-default`; news `readability` (tokens only); tutorial/SPA Stagehand
  innerText; PDF not measured; paywall/challenge excluded. No default config
  switch is made from this baseline alone.
- **Final benchmark (measured, 2026-10-26):** 21 fixtures, 3 runs, tiktoken
  cl100k, evidence-token presence. Results and limitations are in
  `notes/reader-loader-final-2026-10-26.md`; baseline is
  `notes/reader-benchmark-2026-10-26.md`. LLM-graded accuracy and live A/B were
  **not measured**; no agent-level token claim is made.
- **Page-type ceiling adjustment after measurement:** article 24k (large/
  non-English deep facts), tutorial 40k (late lambda/defaults sections), docs
  12k (all docs facts fit), hard maximum 48k. This raised tokens on long pages
  but fixed 15/17 -> 17/17 article and 2/4 -> 4/4 tutorial evidence. Ceilings
  remain ceilings; short pages are unaffected.
- **Paper limitation accepted, not hidden:** at the 24k paper ceiling the
  reader loses the `over 4,000 prompts` fact (~51k in the extracted paper).
  Progressive/query loading is the intended fix; it is implemented as an opt-in
  view (default full) because no A/B showed fewer total tokens at equal
  accuracy. The final note says so.
- **Proxy artifacts:** product 2/4 and SPA 3/4 are bag-of-words mismatches
  against table labels/reference wording, not proven answer errors. Table
  `reader-no-tables` looks cheaper on the proxy; rejected because removing
  tables loses structure and the proxy can be satisfied by adjacent prose.
- **Implemented in this pass:** page-type detection (21/21 corpus), context
  header, structured tables/code/lists, thread mode, PDF/page markers, binary
  rejection, per-call link policy, hidden-content stripping, untrusted wrapper,
  gateway HTTP TTL cache, sub-agent output budget, counters/logs/metrics,
  Grafana dashboard, fixtures/ground truth, golden/fuzz/injection/gateway tests,
  Makefile/pre-commit/CI configs, docs/runbook, privacy checker.
- **Cache scope:** only the gateway HTTP cache is implemented. The orchestrator
  browser path still navigates on repeat; a browser-path cache is deferred
  (would need measured cross-path hit rates). Do not claim browser caching.
- **Not executed here:** pre-commit, GitHub Actions, `pip-audit`, `npm audit`,
  markdown link check (no node/docker/network in this shell). Configs parse;
  label them unverified until CI runs.
- **Test count:** 197 passed, 1 skipped (slow large-page stability) at the end;
  before this work: 104 passed. `make verify` = ruff check + format check +
  privacy + pytest + compose config (skipped when docker is absent).
- **Docs/PII:** renamed the old note to a slug, added front matter, created
  docs/notes indexes and runbook, scrubbed real emails/IPs/domains to documented
  placeholders. `scripts/check_privacy.py` passes.
- **Upstream repro measured:** trafilatura 2.3.1 with `deduplicate=True` on the
  docs fixture gives 56,913 chars for calls 1-3, 41,591 for 4-6, 0 for 7-8;
  `deduplicate=False` is stable. Draft issue is in `docs/upstream/`; not posted.
- **Progressive loading:** implemented as an opt-in `mode=outline|section|query`
  view (default `full`). Tests cover offsets, query selection and budgets. It is
  not enabled by default because the A/B has not shown fewer total tokens; a
  full-text cache is still needed to avoid refetch on section requests.
- **Browser-path cache:** still deferred; only the gateway HTTP cache is live.
- **Docs budget final:** article 24k, docs 12k, tutorial 40k, hard max 48k after
  measured deep-fact checks; the final note records the token cost and the paper
  limitation.
