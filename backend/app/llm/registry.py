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
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.config import settings
from app.llm.roles import LLMRole
from app.llm.stub import StubChatModel
from app.logging import get_logger

logger = get_logger(__name__)

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
        else:
            self._candidates = [
                (settings.llm_provider, primary_model),
                (settings.llm_fallback_provider, fallback_model),
            ]

    async def ainvoke(
        self, prompt: str, *, structured: type[BaseModel] | None = None
    ) -> LLMOutcome:
        errors: list[Exception] = []
        attempts = 0

        for provider, model in self._candidates:
            for attempt in range(settings.llm_max_retries):
                attempts += 1
                start = time.monotonic()
                try:
                    chat = _build_model(provider, model)

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
                    )

                except Exception as exc:  # noqa: BLE001 - genuinely any provider failure retries
                    errors.append(exc)
                    logger.warning(
                        "llm_call_failed",
                        role=self.role,
                        provider=provider,
                        model=model,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    if attempt + 1 < settings.llm_max_retries:
                        await asyncio.sleep(min(2**attempt + random.random(), 10))

        raise AllProvidersFailedError(self.role, errors)


def get_llm(role: LLMRole) -> LLMClient:
    return LLMClient(role)
