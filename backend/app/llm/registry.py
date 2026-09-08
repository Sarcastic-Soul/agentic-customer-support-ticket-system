"""The one place every LLM call in this project goes through. Model ids live
in .env, read here and nowhere else - swapping a deprecated model, or moving
a role from Gemini to Groq, is a config change, not a code change. Two
providers have already been deprecated out from under this project during
planning (see docs/decisions/0002-model-selection.md); this module is why
that cost a config line instead of a refactor.

Retries with jitter on the primary provider, then falls back to the
secondary provider on repeated failure. Every call's timing and token usage
is returned so callers (the graph nodes) can record it into agent_steps.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.config import settings
from app.llm.roles import LLMRole
from app.llm.stub import StubChatModel
from app.logging import get_logger

logger = get_logger(__name__)

# Free-tier RPM ceilings, measured against the real usage dashboards (Google
# AI Studio / Groq console), not documentation guesses - see
# docs/PROGRESS.md Stage 12. Missing from this map (stub, any model not
# listed) means "don't pace it".
_RPM_LIMITS: dict[tuple[str, str], int] = {
    ("gemini", "gemini-3.8-flash"): 5,
    ("gemini", "gemini-3.5-flash-lite"): 15,
    ("groq", "openai/gpt-oss-120b"): 30,
    ("groq", "openai/gpt-oss-20b"): 30,
}


class _RateLimiter:
    """Proactively paces requests per (provider, model) to stay under its
    real RPM ceiling, instead of firing immediately and reactively retrying
    after a 429. Matters because a non-quota transient error (a Gemini 503
    "experiencing high demand", say) doesn't get the fast-fail treatment
    _is_quota_exhausted gives a real 429 - it burns the full retry budget
    with backoff, which live-testing measured at up to ~100s for one call.
    Pacing requests below the ceiling in the first place avoids triggering
    that path from self-inflicted throttling at all.

    A sliding 60s window per key, sized to the model's RPM limit - not a
    token bucket, since RPM ceilings here are small enough (5-30) that the
    difference doesn't matter and a plain window is easier to reason about.
    """

    def __init__(self) -> None:
        self._timestamps: dict[tuple[str, str], list[float]] = {}
        self._lock = asyncio.Lock()

    async def wait(self, provider: str, model: str) -> None:
        limit = _RPM_LIMITS.get((provider, model))
        if limit is None:
            return
        key = (provider, model)
        while True:
            async with self._lock:
                now = time.monotonic()
                window = self._timestamps.setdefault(key, [])
                cutoff = now - 60
                window[:] = [t for t in window if t > cutoff]
                if len(window) < limit:
                    window.append(now)
                    return
                sleep_for = window[0] + 60 - now + 0.05
            # Sleep outside the lock - a long pacing wait for one
            # (provider, model) key must not block unrelated keys from
            # checking their own window in the meantime.
            logger.info(
                "llm_rate_limit_pacing", provider=provider, model=model,
                limit_rpm=limit, sleep_seconds=round(sleep_for, 1),
            )
            await asyncio.sleep(sleep_for)


_rate_limiter = _RateLimiter()

# (setting for primary model, setting for fallback model) per role. verify
# shares classify's tier/fallback, summarize shares reason's - see
# docs/02-tech-stack.md's role table.
_ROLE_MODELS: dict[LLMRole, tuple[str, str]] = {
    LLMRole.classify: (settings.model_classify, settings.fallback_model_classify),
    LLMRole.verify: (settings.model_verify, settings.fallback_model_classify),
    LLMRole.reason: (settings.model_reason, settings.fallback_model_reason),
    LLMRole.summarize: (settings.model_summarize, settings.fallback_model_reason),
    LLMRole.judge: (settings.judge_model, settings.judge_model),
}


@dataclass(frozen=True)
class LLMOutcome:
    text: str | None
    structured: BaseModel | None
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    attempts: int
    tool_calls: list[dict] = field(default_factory=list)


class AllProvidersFailedError(RuntimeError):
    def __init__(self, role: LLMRole, errors: list[Exception]):
        super().__init__(f"all providers failed for role {role!r}: {errors!r}")
        self.errors = errors


def _build_model(provider: str, model: str) -> BaseChatModel:
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "groq":
        return ChatGroq(
            model=model, api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds
        )
    if provider == "stub":
        return StubChatModel()
    raise ValueError(f"unknown LLM provider {provider!r}")


def _extract_text(content: object) -> str:
    """Gemini returns content as a list of content blocks (with 'extras' like
    thought signatures mixed in); Groq/OpenAI-style returns a plain string.
    Normalize both to plain text.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


_QUOTA_MARKERS = (
    "resource_exhausted", "rate_limit", "rate limit", "429", "quota",
)


def _is_quota_exhausted(exc: Exception) -> bool:
    """String-matched rather than an exception-class check: Gemini and Groq
    (OpenAI-style) raise different exception hierarchies for the same kind
    of failure, and matching on the message is simpler than depending on
    both SDKs' internal error taxonomies. A known simplification - a false
    positive just means an unnecessary but harmless early fallback; a false
    negative just means the old (slow but correct) retry-then-fallback path.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


def _usage(message: AIMessage) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return 0, 0
    return usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0


class LLMClient:
    """Bound to one role. Call .ainvoke() for plain text, or
    .ainvoke(structured=Schema) for a validated Pydantic instance.
    """

    def __init__(self, role: LLMRole):
        self.role = role
        primary_model, fallback_model = _ROLE_MODELS[role]
        if settings.llm_provider == "stub":
            self._candidates: list[tuple[str, str]] = [("stub", "stub")]
        elif role == LLMRole.judge:
            # judge_model is deliberately a different provider from the
            # system under test (docs/08-evaluation.md), not the same
            # primary/fallback pair every other role uses - going through
            # llm_provider first would just be a guaranteed-wrong-model
            # attempt burning a retry (and quota) before falling back here
            # anyway.
            self._candidates = [(settings.llm_fallback_provider, primary_model)]
        else:
            self._candidates = [
                (settings.llm_provider, primary_model),
                (settings.llm_fallback_provider, fallback_model),
            ]

    async def ainvoke(
        self,
        prompt: str | list[BaseMessage],
        *,
        structured: type[BaseModel] | None = None,
        tools: list[BaseTool] | None = None,
    ) -> LLMOutcome:
        errors: list[Exception] = []
        attempts = 0

        for provider, model in self._candidates:
            for attempt in range(settings.llm_max_retries):
                attempts += 1
                await _rate_limiter.wait(provider, model)
                start = time.monotonic()
                try:
                    chat = _build_model(provider, model)
                    if tools is not None:
                        chat = chat.bind_tools(tools)

                    if structured is not None:
                        runnable = chat.with_structured_output(structured, include_raw=True)
                        result = await runnable.ainvoke(prompt)
                        if result.get("parsing_error"):
                            raise result["parsing_error"]
                        raw_message: AIMessage = result["raw"]
                        tokens_in, tokens_out = _usage(raw_message)
                        return LLMOutcome(
                            text=None,
                            structured=result["parsed"],
                            provider=provider,
                            model=model,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            latency_ms=int((time.monotonic() - start) * 1000),
                            attempts=attempts,
                        )

                    message = await chat.ainvoke(prompt)
                    tokens_in, tokens_out = _usage(message)
                    return LLMOutcome(
                        text=_extract_text(message.content),
                        structured=None,
                        provider=provider,
                        model=model,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=int((time.monotonic() - start) * 1000),
                        attempts=attempts,
                        tool_calls=list(getattr(message, "tool_calls", []) or []),
                    )

                except Exception as exc:  # noqa: BLE001 - genuinely any provider failure retries
                    errors.append(exc)
                    exhausted = _is_quota_exhausted(exc)
                    logger.warning(
                        "llm_call_failed",
                        role=self.role,
                        provider=provider,
                        model=model,
                        attempt=attempt + 1,
                        error=str(exc),
                        quota_exhausted=exhausted,
                    )
                    if exhausted:
                        # A quota/rate-limit error will not clear on retry
                        # within the seconds this request has to live -
                        # Gemini's own RetryInfo has said as much as 60s.
                        # Move straight to the fallback provider rather than
                        # burning the remaining retries and their backoff
                        # sleeps on a call guaranteed to fail again. Found by
                        # live-testing against a real exhausted free tier
                        # (see docs/PROGRESS.md Stage 5) - the naive retry
                        # loop took 235s for one reply before this fix.
                        break
                    if attempt + 1 < settings.llm_max_retries:
                        await asyncio.sleep(min(2**attempt + random.random(), 10))

        raise AllProvidersFailedError(self.role, errors)


def get_llm(role: LLMRole) -> LLMClient:
    return LLMClient(role)
