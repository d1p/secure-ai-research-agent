"""Open WebUI Function — coding approval UI.

When the orchestrator returns a coding plan (needs_approval=true), this Function
renders the plan and the approval id, and wires the Approve / Edit / Reject
actions to the orchestrator's `/approvals/{id}/decision` API.

The interactive button rendering depends on the exact Open WebUI event API of
the installed version; the plan + approval id are always surfaced in the message
so the decision can also be driven programmatically (see README).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        ORCHESTRATOR_URL: str = Field(
            default="http://orchestrator:8080",
            description="Orchestrator base URL",
        )
        ORCHESTRATOR_TOKEN: str = Field(
            default="",
            description="Shared orchestrator token (set from .env)",
        )
        priority: int = Field(default=0, description="Filter priority")

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def outlet(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any],
        __event_emitter__: Any,
    ) -> dict[str, Any]:
        choices = body.get("choices", [])
        if not choices:
            return body
        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, str) and '"needs_approval": true' in content:
            import json

            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                return body

            approval_id = payload.get("approval_id")
            plan = payload.get("plan", {})
            await self._emit_plan(
                __event_emitter__,
                approval_id,
                plan,
                payload.get("allowed_files", []),
            )
        return body

    async def _emit_plan(
        self,
        emitter: Any,
        approval_id: int | None,
        plan: dict[str, Any],
        allowed_files: list[str],
    ) -> None:
        if emitter is None:
            return
        summary = plan.get("summary", "Coding plan")
        steps = plan.get("steps", [])
        text = f"**Coding plan (approval {approval_id})**\n\n{summary}\n\n"
        text += "Files:\n" + "\n".join(f"- `{f}`" for f in allowed_files)
        if steps:
            text += "\n\nSteps:\n" + "\n".join(f"- {s}" for s in steps)
        text += (
            "\n\nApprove / Edit / Reject this plan. "
            f"(orchestrator: POST /approvals/{approval_id}/decision)"
        )
        try:
            await emitter(
                {
                    "type": "status",
                    "data": {
                        "description": "Coding request requires approval",
                        "done": True,
                    },
                }
            )
            await emitter({"type": "message", "data": {"content": text}})
        except Exception:  # noqa: BLE001,S110 - emitter is best-effort UI glue
            pass
