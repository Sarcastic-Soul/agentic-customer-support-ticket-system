"""The Redis LLM cache: same inputs give the same key, any change gives a
new one, and a hit skips the provider. Pure: Redis and the model are faked.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import app.llm.registry as registry
from app.config import settings
from app.llm.cache import cache_active, cache_key
from app.llm.roles import LLMRole


def test_key_is_stable_and_sensitive_to_every_input():
    msgs = [SystemMessage(content="sys"), HumanMessage(content="where is ORD-10432")]
    base = cache_key("groq", "m1", msgs)
    assert base == cache_key("groq", "m1", list(msgs))
    assert base != cache_key("groq", "m2", msgs)
    assert base != cache_key("gemini", "m1", msgs)
    assert base != cache_key("groq", "m1", [msgs[0], HumanMessage(content="where is ORD-10433")])
    assert base != cache_key("groq", "m1", "where is ORD-10432")


def test_stub_provider_is_never_cached(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_enabled", True)
    assert cache_active("stub") is False
    assert cache_active("groq") is True
    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    assert cache_active("groq") is False


async def test_second_identical_call_is_served_from_cache(monkeypatch):
    store: dict[str, dict] = {}
    built = []

    async def fake_get(key):
        return store.get(key)

    async def fake_put(key, value):
        store[key] = value

    def fake_build(provider, model):
        built.append((provider, model))
        return GenericFakeChatModel(messages=iter([AIMessage(content="It ships tomorrow.")]))

    monkeypatch.setattr(settings, "llm_cache_enabled", True)
    monkeypatch.setattr(registry, "cache_get", fake_get)
    monkeypatch.setattr(registry, "cache_put", fake_put)
    monkeypatch.setattr(registry, "_build_model", fake_build)

    client = registry.LLMClient(LLMRole.reason)
    client._candidates = [("groq", "fake-model")]

    first = await client.ainvoke("where is my order")
    second = await client.ainvoke("where is my order")

    assert first.text == second.text == "It ships tomorrow."
    assert first.cached is False
    assert second.cached is True
    assert len(built) == 1  # the provider was called once


async def test_bad_api_key_is_not_retried(monkeypatch):
    calls = []

    class BadKeyModel(GenericFakeChatModel):
        async def ainvoke(self, *args, **kwargs):
            calls.append(1)
            raise RuntimeError("Error code: 401 - {'error': {'code': 'invalid_api_key'}}")

    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    monkeypatch.setattr(
        registry, "_build_model", lambda p, m: BadKeyModel(messages=iter([]))
    )
    client = registry.LLMClient(LLMRole.reason)
    client._candidates = [("groq", "fake-model")]

    try:
        await client.ainvoke("hi")
    except registry.AllProvidersFailedError:
        pass
    assert len(calls) == 1
