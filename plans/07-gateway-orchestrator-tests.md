# Plan 07 - Gateway and orchestrator reliability tests

- **Workstream:** C5/C6
- **Depends on:** plan 01 (large fixture) and plan 05 (reason fields optional)
- **Gate:** gateway tests cover retry/backoff, clean 502, off-loop extraction,
  redirect SSRF and DNS rebinding; orchestrator envelope tests cover success
  and error envelopes. All default tests offline.

## Goal

Prove the security and reliability fixes that currently have no direct tests,
and make the gateway testable without a live browser or network.

## Dev dependencies

Add `requirements-dev.txt` with pinned service + test dependencies:
`-r gateway/requirements.txt`, `-r orchestrator/requirements.txt`,
`pytest-asyncio`, `hypothesis`, `readability-lxml`, `markdownify`, `pypdf`,
`tokenizers`, `pytest` (and `tiktoken` already used). Log every addition and
why in `decision.md`. Update `tests/conftest.py` so both `gateway/` and
`orchestrator/` are importable (their modules use top-level `security`, `agent`
and `tools` imports).

## Small testability change

`_http_fetch(url, max_chars=None, *, transport: httpx.AsyncBaseTransport | None
= None)` passes the transport to `httpx.AsyncClient`; default `None` preserves
behavior. No other production change in this plan unless a test exposes a real
bug.

## Gateway tests (`tests/test_gateway_fetch.py`)

1. **Retry/backoff:** `httpx.MockTransport` raises `ConnectError` twice then
   returns HTML; patch `asyncio.sleep` to record delays; assert success, three
   attempts and backoff `0.25, 0.5`.
2. **Clean 502:** all three attempts raise `ConnectError`; assert
   `HTTPException(502)` and detail contains `ConnectError` (not a traceback).
3. **Extraction off the event loop:** fake transport returns a ~1.5 MB HTML
   document; monkeypatch `gateway.app.read_html` to sleep 0.5 s. Start `/execute`
   with `http_fetch` and concurrently `GET /healthz`; assert the health request
   completes well under 0.2 s. This proves `asyncio.to_thread` is used.
4. **Redirect SSRF:** response is `302 Location: <blocked-private-address>/`
   (use a private/link-local literal in the test); assert 403 and only one
   outbound request. Also cover a public redirect that is allowed (re-validated
   and followed).
5. **Private ranges / DNS rebinding:** monkeypatch `validate_url` to allow the
   first URL and block the redirect target; assert 403. Keep `tests/test_ssrf.py`
   as the lower-level rebinding test.
6. **HTML vs text:** `content-type: text/html` goes through `read_html`;
   `text/plain` is returned as text with the budget/truncation marker.
7. **Auth/tier sanity:** `http_fetch` is Tier 0; missing URL is 400; unknown
   tool is 403 (covered elsewhere but keep one end-to-end check).

Set `GATEWAY_TOKEN` on the imported module or monkeypatch it before requests.
Use `httpx.ASGITransport`; no real sockets. For the off-loop test, patch
`gateway.app.stagehand` only if needed; `http_fetch` does not use it.

## Orchestrator tests (`tests/test_orchestrator_payload.py`)

1. `_unwrap_fetch_payload` returns plain text for
   `{"url","status","content_type","text"}`.
2. Error envelopes (`{"error": ...}`, `{"detail": ...}`) are not mistaken for
   page text and are returned in a form the model can see as an error.
3. Plain text and invalid JSON pass through unchanged.
4. `_extract_mcp_text` joins multiple text chunks and ignores non-text items.
5. A regression test asserts `/fetch` never forwards the JSON wrapper.

No live agent run; pure helper tests plus one ASGI route test with a stubbed
`call_browser` if feasible without DB.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_gateway_fetch.py tests/test_orchestrator_payload.py
.venv/bin/python -m pytest -q
```

Acceptance: all new tests pass offline; full suite green; no real network or
browser; the off-loop test fails if extraction is moved back onto the event
loop.

## Risks / notes

- Importing the FastAPI app creates a `StagehandClient` but makes no network
  call until a tool runs.
- `_init_db` runs on startup; use ASGI transport without lifespan or ensure
  `DATABASE_URL` is empty so the DB pool is skipped.
- Dev requirements are heavier than before; CI installs only what tests need.
