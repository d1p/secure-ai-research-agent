#!/usr/bin/env bash
# Live A/B: restart the loader variant, run tasks, repeat. Run on the VM with
# provider credentials. Not a CI target.
set -euo pipefail
COMPOSE_DIR="${COMPOSE_DIR:-/opt/ai-stack}"
RUNS="${RUNS:-3}"
OUT_DIR="${OUT_DIR:-/tmp/loader-ab}"
mkdir -p "$OUT_DIR"
for variant in legacy new; do
  ( cd "$COMPOSE_DIR" && LOADER_VARIANT="$variant" docker compose up -d gateway orchestrator )
  # wait for health
  for _ in $(seq 1 60); do
    if curl -sf "${ORCHESTRATOR_URL:-http://localhost:8080}/healthz" >/dev/null; then break; fi
    sleep 2
  done
  python scripts/bench_agent.py --variant "$variant" --runs "$RUNS" \
    --out "$OUT_DIR/${variant}.json"
done
python - "$OUT_DIR" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
for name in ("legacy", "new"):
    data = json.loads((out / f"{name}.json").read_text())
    rows = data["rows"]
    grades = [r for r in rows if r["grade"] in {"CORRECT", "INCORRECT"}]
    print(name, "tasks", data["tasks"], "runs", data["runs"],
          "correct", sum(r["grade"] == "CORRECT" for r in grades),
          "success_measured", len(grades),
          "wall_s", round(sum(r["wall_seconds"] for r in rows) / len(rows), 2))
PY
