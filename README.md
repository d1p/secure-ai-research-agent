# Homelab AI Stack

Self-hosted AI stack (chat, web/product research, document RAG, coding
assistance) running on a Proxmox VM. Git is the source of truth; Docker Compose
is the deployment mechanism.

## What this is

- **Open WebUI** — chat/RAG UI (PWA).
- **LiteLLM** — the *only* route to cloud LLMs (Bedrock/OpenAI/Gemini/DeepSeek).
- **Ollama** — embeddings only (`nomic-embed-text`), no local chat LLM.
- **PostgreSQL (pgvector)** — app + vector + budget/approval/audit state.
- **Redis** — cache/queue.
- **Browser** — headed Chrome + Xvfb + noVNC + Playwright MCP.
- **Safeguard gateway** — SSRF/tier/rate-limit security boundary for the browser.
- **Orchestrator** — LangGraph agent (research / browser / coding approval).
- **Ephemeral coding runner** — aider/opencode in a hardened throwaway container.
- **pgbackup** — nightly Postgres + Open WebUI backups with restore verification.

## Intentionally NOT deployed

Tailscale, Caddy, Authentik, Kubernetes, local chat LLM, GPU services. These
already exist externally or are out of scope.

## Architecture

```mermaid
flowchart LR
    subgraph LAN
        user[User] --> caddy[Caddy (external)]
        caddy -->|:3000| webui[Open WebUI]
        user -->|:6080 noVNC| browser[Browser]
    end
    subgraph vm[AI VM]
        webui --> litellm[LiteLLM]
        webui --> ollama[Ollama embeddings]
        webui --> pg[(Postgres/pgvector)]
        orchestrator[Orchestrator] --> litellm
        orchestrator --> gw[Safeguard Gateway]
        orchestrator --> proxy[Docker socket proxy]
        gw --> browser
        browser --> proxyweb[proxy-web]
        litellm --> cloud[Cloud LLMs]
        proxyweb --> internet[Internet]
        proxydev[proxy-dev] --> internet
    end
```

### Networks

| Network   | Members                              | Internal |
|-----------|--------------------------------------|----------|
| `frontend`| Open WebUI (publishes `:3000`)        | no       |
| `internal`| postgres, redis, litellm, ollama, orchestrator, gateway | yes |
| `browser` | gateway, browser, proxy-web           | yes      |
| `agents`  | litellm, proxy-dev, coding runners    | yes      |
| `egress`  | litellm, proxy-web, proxy-dev, gateway (DNS only) | no (outbound only) |
| `novnc`   | browser (publishes `:6080` noVNC)     | no       |

`novnc` exists only because Docker cannot publish ports from `internal: true`
networks; the browser's automation/egress traffic stays on the internal
`browser` network, and Chrome is forced through `proxy-web`.

Containers have no direct Internet access unless on the `egress` network. The
browser reaches the Internet only through `proxy-web`; coding runners only
through `proxy-dev` (allowlisted domains) and LiteLLM.

### Storage

| Path  | Backing                        | Contents                                  |
|-------|--------------------------------|-------------------------------------------|
| `/fast`| VM NVMe disk (Docker data-root)| images + named volumes (`pgdata`, `openwebui-data`, `ollama-data`, `browser-profile`) |
| `/data`| NFS mount of host `/mnt/nasdata/ai` | `uploads`, `workspaces`, `backups`, `bulk` |

`/data` bind mounts use `bind: { create_host_path: false }` so a missing mount
fails instead of writing to the root filesystem. `browser-profile` is never
backed up.

### Resource limits

Total `mem_limit` ≤ 13 GB. See `docker-compose.yml` for per-service limits.

| Service | Limit |
|---|---|
| open-webui | 2 GB |
| litellm | 1.5 GB |
| ollama | 1 GB |
| postgres | 2 GB |
| redis | 256 MB |
| browser | 2.5 GB |
| safeguard-gateway | 256 MB |
| orchestrator | 1 GB |
| docker-socket-proxy | 64 MB |
| proxy-web / proxy-dev | 64 MB each |
| pgbackup | 128 MB |
| agent-runner (ephemeral) | 1.5 GB |

## Setup

1. Provision the VM (see below).
2. `git clone` this repo on the VM.
3. Copy `.env.example` to `.env` and fill in real values (never commit `.env`).
4. `docker compose config` → `docker compose build` → `docker compose up -d`.
5. Create the first Open WebUI admin manually (signup is disabled).

### Required `.env` values

All values are documented with placeholders in `.env.example`. The
security-relevant ones: `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`WEBUI_SECRET_KEY`, `LITELLM_MASTER_KEY`, `GATEWAY_TOKEN`,
`ORCHESTRATOR_TOKEN`, `VNC_PASSWORD`, and the cloud provider keys. Cloud
credentials live **only** in `.env`.

### VM provisioning

The target VM (8 vCPU / 14 GB / 50 GB NVMe root):

```bash
qm create 119 --name ai-stack-vm --memory 14336 --cores 8 --sockets 1 \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-pci --ostype l26 \
  --agent enabled=1 --serial0 socket --vga serial0 --onboot 1
# import Ubuntu 24.04 cloud image, resize to 50G, attach as scsi0
qm set 119 --ipconfig0 ip=10.0.0.210/24,gw=10.0.0.138
qm set 119 --nameserver 10.0.0.14 --ciuser root --sshkeys /root/.ssh/id_rsa.pub
```

Inside the VM: Docker data-root is `/fast/docker`; `/data` is an NFS mount of
`10.0.0.200:/mnt/nasdata/ai`.

### Firewall requirement

The VM firewall must allow **only** ports `3000` and `6080`, and only from the
Caddy PCT IP (`${CADDY_PCT_IP}`, default `10.0.0.28`). No other service may be
reachable from the LAN. PostgreSQL, Redis, LiteLLM, Ollama, gateway and
orchestrator are on `internal` networks and must not be LAN-accessible.

### Caddy integration

Add a Caddyfile entry in CT 110 proxying `ai.debashis.xyz` (or your domain) to
`${BIND_IP}:3000`, e.g.:

```caddy
ai.debashis.xyz {
    reverse_proxy 10.0.0.210:3000
}
```

Restart Caddy (`pct exec 110 -- systemctl restart caddy`), never reload.

## Browser / noVNC

The browser runs headed Chrome under Xvfb, exposed via noVNC on port `6080`
with the VNC password from `.env`. Cookies, history, localStorage and
preferences persist in the `browser-profile` named volume and never leave the
container. Reset with `scripts/browser_reset.sh --yes`.

Two profiles exist conceptually: `anon` (default, persistent, never logged in)
and `personal` (optional, human-managed, only after explicit per-session
approval and only for `PERSONAL_ALLOW_DOMAINS`).

The gateway enforces: SSRF blocking (all RFC1918/link-local/metadata ranges,
`localhost`, internal hostname suffixes, `file://`/`chrome://`/`about:` schemes),
DNS rebinding re-validation on every redirect, URL-length/query/base64
exfiltration limits, tool tiers, 30 req/min/agent, and one page load per 5 s per
domain. Every browser action is audited to `orchestrator.browser_audit`.

On a CAPTCHA / Cloudflare challenge / login wall, the gateway stops and returns
`needs_human: true`; the human resolves it through noVNC.

## Security model

- LiteLLM is the only egress to cloud providers; all other cloud access is
  blocked at the network layer.
- A **secret guard** (LiteLLM pre-call callback) rejects prompts containing AWS
  keys, `sk-...`, GitHub tokens, PEM private keys, or `.env`-style `KEY=`
  assignments with long values. RAG chunks pass unless they match these rules.
- The **gateway** is the browser security boundary (Playwright MCP is not).
  Tier 3 tools (evaluate, cookies, storage, devtools, downloads) return 403;
  sensitive fields are blocked; Tier 2 actions require approval.
- Coding runners are ephemeral, non-root, `cap_drop: ALL`,
  `no-new-privileges`, `pids_limit`, 1.5 GB, `agents` network only, no push
  credentials, never merge/push.

## Approval workflow

1. A coding request is analyzed and a plan is generated.
2. An `approvals` row is created with status `pending`; the workspace is **not**
   modified.
3. Open WebUI surfaces the plan + `approval_id` (see
   `open-webui/functions/approval.py`).
4. Approve → the orchestrator spawns one ephemeral runner on a throwaway
   worktree. Reject → task ends with no retry. Edit → re-planning.
5. After execution, `git diff --name-only` must contain only approved files;
   otherwise the worktree is discarded and the task fails.

## Backups

`pgbackup` runs nightly (2:00 AM) and writes to `/data/backups`, retaining 7
days. It dumps every database and tars Open WebUI data. It refuses to run
unless `/data` is a real NFS mountpoint. Verify restores with
`scripts/restore_test.sh`. Off-site backup is left as a documented hook (e.g.
rclone) — no always-on off-site service is deployed.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pytest ruff
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
```

## Deviations from the original specification

1. **Storage sizing** — the 512 GB NVMe is the Proxmox boot disk; the VM root
   disk (which doubles as `/fast`) is 50 GB. `/data` is a dedicated NFS
   subdirectory of the host's existing 4 TB DAS (`/mnt/nasdata/ai`), not a
   separate disk.
2. **Open WebUI env names** — `ENABLE_TAGS_GENERATION` (plural), `RAG_OLLAMA_BASE_URL`
   (not `RAG_EMBEDDING_BASE_URL`), `VECTOR_DB=pgvector`. `DO_NOT_TRACK`/
   `ANONYMIZED_TELEMETRY`/`SCARF_NO_ANALYTICS` are set per policy but are
   vestigial in current Open WebUI (telemetry is opt-in OTel, off by default).
3. **LiteLLM** — `drop_params` lives under `litellm_settings` (not
   `general_settings`). Self-hosted LiteLLM runs no telemetry by default. Model
   IDs are set from current docs (`bedrock/us.anthropic.claude-sonnet-5`,
   `openai/gpt-5`, `gemini/gemini-2.5-pro`, `deepseek/deepseek-flash`) and should
   be re-verified against provider docs at deploy time.
4. **docker-socket-proxy** — its `CONTAINERS=1` bundles create/start/stop/list
   under one flag; finer separation is not possible in that image.
5. **Open WebUI approval buttons** — the Function renders the plan + approval id;
   interactive Approve/Edit/Reject buttons depend on the exact Open WebUI event
   API of the installed version. The decision API
   (`POST /approvals/{id}/decision`) is always available programmatically.
6. **Scroll tool** — Playwright MCP has no `scroll`; scrolling is
   `browser_mouse_wheel` (via `--caps=vision`). Coordinate-based mouse tools are
   Tier-3 (blocked).
7. **noVNC port + `novnc` network** — Docker cannot publish ports from
   `internal: true` networks, so the browser also attaches to a dedicated
   non-internal `novnc` network solely to publish noVNC (`:6080`). Chrome is
   forced through `proxy-web` and the gateway's SSRF rules remain the tested
   security boundary.
8. **Gateway DNS** — `internal: true` networks do not forward external DNS, so
   the safeguard gateway also joins the `egress` network solely to resolve
   hostnames for SSRF validation. The gateway is trusted, publishes no ports,
   and remains LAN-inaccessible.

## Known limitations

- End-to-end cloud chat and coding-runner execution require provider
  credentials in `.env` (DeepSeek at minimum) and were not fully exercised
  without them.
- The coding-runner workspace permission model (orchestrator root vs runner
  uid 1000 on the NFS mount) needs a shared GID for multi-user use; single-user
  works with `chown` on the worktree.
- Browser profile switching (`anon` vs `personal`) is human-managed via noVNC.
