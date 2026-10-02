"""Optional Langfuse tracing for the agent graph.

agent_runs / agent_steps / tool_calls stay the record of truth (CLAUDE.md
non-negotiable #9) - the eval harness and the console read those. Langfuse is
a second, richer view for debugging: every prompt, every LLM response, token
counts and timings, nested under one trace per run. It is off unless both
LANGFUSE_* keys are set, and runs self-hosted (`make langfuse`, port 3001),
so no customer text leaves the machine. See docs/decisions/0008-upgrades.md.

LangGraph passes the callbacks in the graph config down to every LLM call
made inside a node, so nothing in the nodes or the registry has to know
about Langfuse.
"""

from functools import lru_cache

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


def tracing_enabled() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


@lru_cache(maxsize=1)
def _client():
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.env,
    )


def trace_config(*, ticket_id: int, run_id: int | None, channel: str | None) -> dict:
    """Extra graph config (callbacks + metadata) for one run, or {} when
    tracing is off or Langfuse fails to start."""
    if not tracing_enabled():
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        _client()
        handler = CallbackHandler(public_key=settings.langfuse_public_key)
    except Exception:  # noqa: BLE001 - tracing must never block a run
        logger.warning("langfuse_unavailable", exc_info=True)
        return {}
    tags = [t for t in (channel, settings.eval_ablation) if t]
    return {
        "callbacks": [handler],
        "metadata": {
            # Langfuse groups a ticket's runs (first reply, resumes) into one session
            "langfuse_session_id": f"ticket:{ticket_id}",
            "langfuse_tags": tags,
            "run_id": run_id,
        },
    }


def flush_traces() -> None:
    if tracing_enabled():
        try:
            _client().flush()
        except Exception:  # noqa: BLE001
            logger.warning("langfuse_flush_failed", exc_info=True)
