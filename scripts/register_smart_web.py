#!/usr/bin/env python3
"""Register the ``smart_web`` tool and the ``deepseek-router`` model in Open WebUI.

The tool source lives in this repo (``open-webui/tools/smart_web.py``); Open WebUI
loads tools from its database, so this script performs the one-time DB upsert.

Run it *inside* the open-webui container:

    docker cp open-webui/tools/smart_web.py ai-stack-open-webui-1:/tmp/smart_web.py
    docker cp scripts/register_smart_web.py ai-stack-open-webui-1:/tmp/register_smart_web.py
    docker exec -e PYTHONPATH=/app/backend -w /app/backend ai-stack-open-webui-1 \
        python /tmp/register_smart_web.py

Idempotent: re-running updates the existing tool/model rows in place.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from open_webui.internal.db import get_async_db_context
from open_webui.models.config import Config
from open_webui.models.models import ModelForm, ModelMeta, Models
from open_webui.models.tools import ToolForm, ToolMeta, Tools
from open_webui.models.users import User
from open_webui.utils.plugin import load_tool_module_by_id
from open_webui.utils.tools import get_tool_specs
from sqlalchemy import select

TOOL_ID = "smart_web"
MODEL_ID = "deepseek-router"
TOOL_PATH = os.environ.get("SMART_WEB_TOOL_PATH", "/tmp/smart_web.py")
BASE_MODEL_ID = os.environ.get("SMART_WEB_BASE_MODEL", "deepseek-flash")

TOOL_DESCRIPTION = (
    "Smart web access: web_search (snippets), http_fetch (plain HTTP, static "
    "pages/files) and browse_page (sandboxed browser for JS/interactive sites). "
    "Pick the cheapest tool that works."
)

SYSTEM_PROMPT = """\
You are a careful research assistant with three web tools. Choose the cheapest tool that actually gets the job done:
- web_search: DuckDuckGo results (titles, URLs, snippets). Use FIRST for general or factual questions.
- http_fetch: plain HTTP GET of one specific URL. Use for static pages, docs, articles and direct files. It does NOT run JavaScript.
- browse_page: opens a URL in a real browser. Use ONLY for JavaScript-heavy, interactive or shopping sites (e.g. eBay listings, sites needing login/cookies).

Rules:
1. Start with web_search; answer from the snippets when they are sufficient.
2. Fetch a full page only when the snippets are not enough.
3. Prefer http_fetch; escalate to browse_page only if http_fetch returns little content or the site needs JS/interaction.
4. Never call web_search and a page fetch for the same thing in one step. If search already answered, stop.
5. Always cite the URLs you used.
"""

# Sub-agent runtime budget + behaviour.  Open WebUI sub-agents inherit the
# selected model and tool IDs, but not the workspace model's system prompt, so
# give them explicit routing/efficiency rules.  Without this they use the
# unbounded builtin fetch_url, burn the 30-iteration cap, and overflow context.
SUBAGENT_SYSTEM_PROMPT = """\
You are a sub-agent working on one focused task assigned by the lead agent. Work efficiently and then stop.

Tool rules (cheapest sufficient tool first):
1. Use web_search for discovery and snippets; answer from snippets when they are enough.
2. For a static page use http_fetch (bounded output). Prefer http_fetch over fetch_url. Leave max_chars at 0 so papers/tables/docs get their page-type budget.
3. Use browse_page only for JavaScript-heavy, interactive, or challenge-protected sites.
4. Do not fetch the same URL twice and do not chase tangents. Keep total tool calls under 20.
5. Cite the URLs and publication dates you used.

When the task is answered, stop calling tools and end with:
- What you did
- Key facts (with source URLs and dates)
- Files changed (if any)
- Gaps or open questions
"""

RUNTIME_CONFIG = {
    # Cap builtin fetch_url output. The orchestrator already applies the real
    # page-type budget (8k-40k); this only stops
    # Open WebUI from truncating those larger budgets again.
    "web.fetch.max_content_length": 48000,
    # Open WebUI sub-agents: on, foreground only, bounded concurrency/iterations.
    "subagents.enable": True,
    "subagents.background_enabled": False,
    "subagents.max_concurrent": 3,
    "subagents.max_iterations": 40,
    "subagents.max_output": 30000,
    "subagents.system_prompt": SUBAGENT_SYSTEM_PROMPT,
}


async def _admin_user_id() -> str:
    async with get_async_db_context() as db:
        result = await db.execute(select(User).where(User.role == "admin").limit(1))
        admin = result.scalars().first()
    if admin is None:
        raise SystemExit("no admin user found; create the Open WebUI admin first")
    return admin.id


async def register_tool(user_id: str, content: str) -> None:
    tool_instance, _, _ = await load_tool_module_by_id(TOOL_ID, content=content)
    specs = get_tool_specs(tool_instance)
    meta = ToolMeta(description=TOOL_DESCRIPTION, manifest={}, has_user_valves=False)

    if await Tools.get_tool_by_id(TOOL_ID):
        await Tools.update_tool_by_id(
            TOOL_ID, {"content": content, "specs": specs, "meta": meta.model_dump()}
        )
        print(f"updated tool {TOOL_ID}")
    else:
        form = ToolForm(
            id=TOOL_ID, name="Smart Web", content=content, meta=meta, access_grants=None
        )
        await Tools.insert_new_tool(user_id, form, specs)
        print(f"created tool {TOOL_ID}")


async def register_model(user_id: str) -> None:
    form = ModelForm(
        id=MODEL_ID,
        base_model_id=BASE_MODEL_ID,
        name="DeepSeek Router",
        meta=ModelMeta(
            description="DeepSeek Flash with smart web routing: search -> plain HTTP -> browser.",
            toolIds=[TOOL_ID],
            capabilities={"citations": True, "web_search": False, "vision": False},
        ),
        params={"system": SYSTEM_PROMPT, "temperature": 0.3},
        access_grants=None,
        is_active=True,
    )

    if await Models.get_model_by_id(MODEL_ID):
        await Models.update_model_by_id(MODEL_ID, form)
        print(f"updated model {MODEL_ID}")
    else:
        await Models.insert_new_model(form, user_id)
        print(f"created model {MODEL_ID}")


async def configure_runtime() -> None:
    await Config.upsert(RUNTIME_CONFIG)
    print("updated sub-agent + web fetch config")


async def main() -> None:
    content = await asyncio.to_thread(Path(TOOL_PATH).read_text, encoding="utf-8")
    user_id = await _admin_user_id()
    await register_tool(user_id, content)
    await register_model(user_id)
    await configure_runtime()


if __name__ == "__main__":
    asyncio.run(main())
