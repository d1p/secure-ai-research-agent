# Runbook

Use placeholders (`${APP_DOMAIN}`, `${VM_HOST}`) from an untracked `.env` or
local notes. Never commit real addresses or contact details.

## Deploy

```bash
cd "${COMPOSE_DIR:-/opt/ai-stack}"
git pull --ff-only            # or use scripts/sync-vm.sh from the canonical host
docker compose build gateway orchestrator browser open-webui
docker compose up -d
docker compose ps
```

Wait for health checks:

```bash
curl -sf "http://${ORCHESTRATOR_HOST}:8080/healthz"
curl -sf "http://${GATEWAY_HOST}:8000/healthz"
```

## Scripted verification

```bash
make verify
pytest -q
.venv/bin/python scripts/bench_reader.py --runs 3 --json /tmp/bench.json
```

After a deploy, fetch one known page through `http_fetch` and one through the
browser path, and check `/metrics` on gateway/orchestrator.

## Rollback

1. Revert the bad commit (or restore the previous tag).
2. Sync the committed tree with `scripts/sync-vm.sh` (same VMID/MAC/IP; never
   restore into a different VM).
3. Rebuild/restart gateway, orchestrator, browser, open-webui.
4. Restore Postgres/Open WebUI only if the data changed; use the backup tool
   and verify with `scripts/restore_test.sh`.
5. Re-run `make verify` and the two smoke fetches.

## Diagnose loader regressions

| Symptom | Look at |
|---|---|
| Model gets empty/irrelevant page | `web_loader_loads_total{reason="reader_empty"}`, `reader_empty_large_page` log |
| Too many tokens | `web_loader_tokens_sum{direction="out"}`, page type and budget |
| Table/code lost | `method`, `page_type`, golden test diff; use `links`/budget note |
| Challenge detected on a real article | challenge signature false positive; add a negative fixture before changing the regex |
| Paywall false positive | same; add a long article negative test |
| PDF junk/empty | `reason=pdf_empty`/`pdf_text`; scanned PDFs need OCR (not supported) |
| Repeated fetch costs | `cache_lookups_total`; check `no-store`/`cache=0` |
| Sub-agent context blowup | `budget_exceeded` log/field and `web_loader_budget_exceeded_total` |

## Rollback a loader-only change

If a loader change loses accuracy, revert only that commit and redeploy the two
services. Do not restore databases for a loader-only regression.
