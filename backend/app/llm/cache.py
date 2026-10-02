"""Redis cache for LLM responses, keyed on everything that decides the answer.

Off by default (LLM_CACHE_ENABLED). Live traffic should not be cached: two
customers can send the same words and need different answers, and the key
already covers the full prompt, so hits would be rare anyway. Where it pays
is the eval harness and prompt regression runs - re-running 55 tickets after
changing one prompt only spends quota on the calls that prompt changed, which
matters on a 1000-requests-a-day free tier. See docs/decisions/0008-upgrades.md.

The key is a hash of: provider, model, the full prompt or message list, the
bound tools' schemas and the structured-output schema. Change any of them
and it is a different key. Any Redis error is a miss, never a failure.
"""

import hashlib
import json

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel
from redis.asyncio import Redis

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "llmcache:v1:"
_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
    return _redis


def _prompt_repr(prompt: str | list[BaseMessage]) -> object:
    if isinstance(prompt, str):
        return prompt
    return [
        {
            "type": m.type,
            "content": m.content,
            "tool_calls": getattr(m, "tool_calls", None) or None,
            "tool_call_id": getattr(m, "tool_call_id", None),
        }
        for m in prompt
    ]


def cache_key(
    provider: str,
    model: str,
    prompt: str | list[BaseMessage],
    *,
    structured: type[BaseModel] | None = None,
    tools: list[BaseTool] | None = None,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "prompt": _prompt_repr(prompt),
        "tools": [convert_to_openai_tool(t) for t in tools] if tools else None,
        "structured": structured.model_json_schema() if structured else None,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return _KEY_PREFIX + hashlib.sha256(raw.encode()).hexdigest()


def cache_active(provider: str) -> bool:
    return settings.llm_cache_enabled and provider != "stub"


async def cache_get(key: str) -> dict | None:
    try:
        raw = await _client().get(key)
    except Exception:  # noqa: BLE001 - a cache miss, never a failure
        logger.warning("llm_cache_get_failed", exc_info=True)
        return None
    return json.loads(raw) if raw else None


async def cache_put(key: str, value: dict) -> None:
    try:
        await _client().set(key, json.dumps(value, default=str), ex=settings.llm_cache_ttl_seconds)
    except Exception:  # noqa: BLE001
        logger.warning("llm_cache_put_failed", exc_info=True)
