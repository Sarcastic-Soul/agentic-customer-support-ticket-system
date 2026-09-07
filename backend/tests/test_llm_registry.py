"""Tests run against LLM_PROVIDER=stub, not real APIs - deterministic, free,
and fast. The fallback-on-failure and structured-output-parsing-error paths
are exercised directly against the registry's retry loop rather than by
actually breaking a live provider (that was verified manually - see
docs/PROGRESS.md Stage 4 - and isn't worth re-running on every test pass).
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.llm.registry import AllProvidersFailedError, LLMClient
from app.llm.roles import LLMRole


class Classification(BaseModel):
    intent: str
    confidence: float


async def test_stub_plain_text(monkeypatch):
    # Real keys are configured in .env (LLM_PROVIDER=gemini) - force stub
    # explicitly so this test stays free, fast and deterministic rather than
    # silently hitting the live API.
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")
    client = LLMClient(LLMRole.classify)
    outcome = await client.ainvoke("anything")
    assert outcome.provider == "stub"
    assert outcome.text
    assert outcome.structured is None


async def test_stub_structured_output(monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")
    client = LLMClient(LLMRole.classify)
    outcome = await client.ainvoke("anything", structured=Classification)
    assert isinstance(outcome.structured, Classification)
    assert outcome.structured.intent == "stub"
    assert outcome.structured.confidence == 0.5


async def test_falls_back_to_second_provider_after_primary_fails(monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "gemini")
    monkeypatch.setattr("app.llm.registry.settings.llm_fallback_provider", "groq")
    monkeypatch.setattr("app.llm.registry.settings.llm_max_retries", 1)

    client = LLMClient(LLMRole.classify)
    assert client._candidates[0][0] == "gemini"
    assert client._candidates[1][0] == "groq"

    calls = []

    def fake_build(provider, model):
        calls.append(provider)
        if provider == "gemini":
            raise RuntimeError("simulated primary provider failure")
        mock = AsyncMock()
        mock.ainvoke.return_value.content = "pong"
        mock.ainvoke.return_value.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
        return mock

    with patch("app.llm.registry._build_model", side_effect=fake_build):
        outcome = await client.ainvoke("anything")

    assert calls == ["gemini", "groq"]
    assert outcome.provider == "groq"
    assert outcome.text == "pong"


async def test_quota_exhaustion_skips_remaining_retries_and_falls_back(monkeypatch):
    # Real bug found live-testing Stage 5 against a genuinely exhausted free
    # tier: without this, a 429 gets retried llm_max_retries times (with
    # backoff sleeps) before falling back, even though a quota error will
    # not clear in the seconds this request has to live. See
    # docs/PROGRESS.md Stage 5 - one reply took 235s before this fix.
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "gemini")
    monkeypatch.setattr("app.llm.registry.settings.llm_fallback_provider", "groq")
    monkeypatch.setattr("app.llm.registry.settings.llm_max_retries", 3)

    client = LLMClient(LLMRole.classify)
    gemini_attempts = 0

    def fake_build(provider, model):
        nonlocal gemini_attempts
        if provider == "gemini":
            gemini_attempts += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded, retry in 49s")
        mock = AsyncMock()
        mock.ainvoke.return_value.content = "pong"
        mock.ainvoke.return_value.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
        return mock

    with patch("app.llm.registry._build_model", side_effect=fake_build):
        outcome = await client.ainvoke("anything")

    assert gemini_attempts == 1  # not llm_max_retries (3) - quota errors don't get retried
    assert outcome.provider == "groq"


async def test_raises_when_every_provider_fails(monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "gemini")
    monkeypatch.setattr("app.llm.registry.settings.llm_fallback_provider", "groq")
    monkeypatch.setattr("app.llm.registry.settings.llm_max_retries", 1)

    client = LLMClient(LLMRole.classify)

    def always_fails(provider, model):
        raise RuntimeError(f"{provider} is down")

    with patch("app.llm.registry._build_model", side_effect=always_fails):
        with pytest.raises(AllProvidersFailedError):
            await client.ainvoke("anything")
