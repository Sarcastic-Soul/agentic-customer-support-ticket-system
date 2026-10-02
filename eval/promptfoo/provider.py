"""promptfoo provider: runs one prompt through the project's own LLM stack.

Goes through app/llm/registry.py like the agent does, so model ids still
come only from .env (CLAUDE.md non-negotiable #6) and the same retries and
fallback apply. The prompt files are the real ones in
backend/app/agent/prompts/ - this checks the prompts the agent ships with,
not copies of them.

Two tasks, picked by the `task` var:
- classify: vars.message (+ optional vars.history) -> the Classification JSON
- verify:   vars.context, vars.tool_results, vars.message, vars.draft -> the
            VerifyVerdict JSON

The LLM cache (app/llm/cache.py) is on, so a re-run only spends quota on
prompts that changed. Needs Redis for that; without it every call is a miss.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agent.nodes.classify import Classification  # noqa: E402
from app.agent.nodes.verify import VerifyVerdict  # noqa: E402
from app.agent.prompts import load_prompt  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm.registry import get_llm  # noqa: E402
from app.llm.roles import LLMRole  # noqa: E402

settings.llm_cache_enabled = True

# One loop for the life of the process: the registry's rate limiter and the
# cache's Redis client are bound to the loop they were first used on.
_loop = asyncio.new_event_loop()


async def _classify(vars: dict) -> dict:
    prompt = load_prompt(
        "classify",
        history=vars.get("history") or "(no prior messages)",
        message=vars["message"],
    )
    outcome = await get_llm(LLMRole.classify).ainvoke(prompt, structured=Classification)
    return {"result": outcome.structured, "outcome": outcome}


async def _verify(vars: dict) -> dict:
    prompt = load_prompt(
        "verify",
        context=vars.get("context") or "(none)",
        tool_results=vars.get("tool_results") or "(none)",
        message=vars["message"],
        draft=vars["draft"],
    )
    outcome = await get_llm(LLMRole.verify).ainvoke(prompt, structured=VerifyVerdict)
    return {"result": outcome.structured, "outcome": outcome}


_TASKS = {"classify": _classify, "verify": _verify}


def call_api(prompt: str, options: dict, context: dict) -> dict:
    vars = context.get("vars", {})
    try:
        done = _loop.run_until_complete(_TASKS[vars.get("task", "classify")](vars))
    except Exception as exc:  # noqa: BLE001 - reported as a failed case, not a crash
        return {"error": f"{type(exc).__name__}: {exc}"}
    result, outcome = done["result"], done["outcome"]
    return {
        "output": json.dumps(result.model_dump() if result else None),
        "tokenUsage": {
            "prompt": outcome.tokens_in,
            "completion": outcome.tokens_out,
            "total": outcome.tokens_in + outcome.tokens_out,
        },
        "cached": outcome.cached,
        "metadata": {"model": f"{outcome.provider}:{outcome.model}"},
    }
