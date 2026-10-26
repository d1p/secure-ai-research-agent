#!/usr/bin/env python3
"""Scaffold for the live agent-level A/B (network/LLM, not default CI).

Runs research tasks through the orchestrator's OpenAI-compatible endpoint with
LOADER_VARIANT=legacy|new (set on the deployed services) and records wall time,
response size, usage when the server returns it, and an optional LLM grade.
Total provider tokens must come from LiteLLM usage/spend; if the response has no
usage block, the report says "not measured" rather than guessing.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx


def grade(answer: str, truth: str, base_url: str, key: str, model: str) -> str:
    if not key:
        return "not_measured"
    prompt = (
        "Grade the candidate answer against the ground truth. Reply exactly "
        f"CORRECT or INCORRECT.\nQuestion answer: {truth}\nCandidate: {answer}"
    )
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
            )
        text = resp.json()["choices"][0]["message"]["content"]
        return "CORRECT" if text.strip().upper().startswith("CORRECT") else "INCORRECT"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:{type(exc).__name__}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("tests/tasks/research.json"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--variant", choices=["legacy", "new"], required=True)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ORCHESTRATOR_URL", "http://localhost:8080"),
    )
    parser.add_argument("--token", default=os.environ.get("ORCHESTRATOR_TOKEN", ""))
    parser.add_argument("--grade-url", default=os.environ.get("LITELLM_URL", ""))
    parser.add_argument("--grade-key", default=os.environ.get("LITELLM_MASTER_KEY", ""))
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--out", type=Path, default=Path("/tmp/bench-agent.json"))
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("ORCHESTRATOR_TOKEN/--token is required")
    tasks = json.loads(args.tasks.read_text())
    rows = []
    for task in tasks:
        for run in range(args.runs):
            started = time.perf_counter()
            with httpx.Client(timeout=600.0) as client:
                resp = client.post(
                    f"{args.base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {args.token}"},
                    json={
                        "model": args.model,
                        "messages": [{"role": "user", "content": task["prompt"]}],
                    },
                )
            elapsed = time.perf_counter() - started
            data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            answer = (
                (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            )
            usage = data.get("usage") or {}
            rows.append(
                {
                    "task": task["id"],
                    "run": run,
                    "variant": args.variant,
                    "status_code": resp.status_code,
                    "wall_seconds": round(elapsed, 3),
                    "answer_chars": len(answer),
                    "usage": usage or "not_measured",
                    "grade": grade(
                        answer,
                        task["answer"],
                        args.grade_url,
                        args.grade_key,
                        args.model,
                    )
                    if args.grade_url
                    else "not_measured",
                    "answer": answer[:2000],
                }
            )
    summary = {
        "variant": args.variant,
        "runs": args.runs,
        "tasks": len(tasks),
        "usage_note": "Provider tokens must come from LiteLLM spend if usage is absent.",
        "rows": rows,
    }
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
