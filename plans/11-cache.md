# Plan 11 - Fetch and extraction cache

- **Workstream:** B7 (moved before progressive loading; see `decision.md`)
- **Depends on:** plans 05, 10
- **Gate:** TTL/no-store/revalidation/hit-rate tested; no stale content shown
  after `no-store`; default suite green.

## Goal

Make repeated loads in one research session cheap without hiding staleness or
bypassing the security boundary. This also enables progressive section requests
(plan 12) without a refetch per section.

## Design

- `shared/cache.py`: thread-safe TTL + bounded LRU. Backend is process memory by
  default. Add a Redis backend only if the benchmark shows cross-process misses
  are material; do not add a dependency speculatively.
- **HTTP fetch cache:** key by URL (method GET). Store status, content-type,
  decoded body, ETag/Last-Modified, stored-at. Default TTL 300 s, configurable
  by env. Respect `Cache-Control: no-store` (do not store), `no-cache`
  (revalidate), and `Vary` (skip caching when it cannot be honoured safely).
- **Extraction cache:** key by URL + SHA-256 of the raw body (or rendered DOM
  hash for the browser path). Store extracted text, reason, page type,
  truncated flag. This avoids re-parsing identical bytes.
- **Browser path:** orchestrator caches extracted text keyed by URL + DOM hash;
  the gateway's `stagehand_content` response may be cached with the same key if
  it is cheap and safe. Do not cache challenge/paywall results as success.
- **Bypass:** `cache=0` per call; default is on. Never cache authenticated or
  `Set-Cookie` responses for the personal profile; document the limitation for
  the anonymous profile.
- **Logging/metrics:** `cache_hit`, `cache_miss`, `cache_revalidated`,
  `cache_bypass`, `cache_store`; log `cache_hit` in the `reason` field only when
  the returned text came from cache; still count output tokens (the model sees
  the same text) and report network/parse time saved separately.

## Honesty about savings

A cache does not reduce the tokens of text the model reads. It reduces network,
parse and latency cost, and makes progressive section requests viable. The note
must state model-token savings separately (if any) from fetch/parse savings.

## Tests (`tests/test_cache.py`)

- TTL expiry; LRU bound; thread-safety smoke.
- `no-store` not stored; `no-cache` revalidates; 304 uses cached body.
- URL+content-hash key changes when body changes.
- Challenge/paywall not cached as success.
- `cache=0` bypass.
- Metrics hit/miss/revalidated labels.
- No network; monkeypatch time and transport.

## Steps

1. Implement cache module and tests.
2. Wire HTTP fetch cache and extraction cache into gateway/orchestrator with
   metrics/logging.
3. Document env knobs and the anonymous-profile limitation.
4. Run repeated-load measurement (latency and bytes) and log it; do not claim
   model-token savings.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_cache.py
.venv/bin/python -m pytest -q
```

Acceptance: all cache tests pass; repeated loads hit the cache; no-store and
challenge paths never serve cached success; default suite green.

## Risks / notes

- Staleness: short TTL; respect no-store/no-cache; bypass available.
- Process-local cache is not shared across gateway/orchestrator. If cross-path
  misses matter in the A/B, revisit Redis with measured hit rates.
- Do not cache personal/authenticated content across sessions.
