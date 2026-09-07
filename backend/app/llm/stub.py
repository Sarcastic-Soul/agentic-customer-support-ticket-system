"""Offline deterministic fake model. `LLM_PROVIDER=stub` runs the whole
pipeline with no API key and no network call - for UI work, for the Stage 12
concurrency check (which must never spend real quota), and for anyone
running this project without wanting to sign up for anything.

Not a general-purpose LLM test double: structured output is synthesized from
the Pydantic schema's field defaults/types, not from the actual prompt. Good
enough to prove the plumbing works end to end; not a substitute for real
model behaviour in an eval.
"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

STUB_TEXT = "This is a stub response (LLM_PROVIDER=stub) - no model was called."


def _synthesize(schema: type[BaseModel]) -> BaseModel:
    values: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        # is_required() is pydantic v2's correct check - field.default is the
        # PydanticUndefined sentinel (not None) for genuinely required fields,
        # so `default is not None` alone incorrectly treats them as defaulted.
        if not field.is_required():
            values[name] = field.default
            continue
        annotation = field.annotation
        if annotation is str:
            values[name] = "stub"
        elif annotation is float:
            values[name] = 0.5
        elif annotation is int:
            values[name] = 0
        elif annotation is bool:
            values[name] = False
        elif annotation is list or getattr(annotation, "__origin__", None) is list:
            values[name] = []
        elif annotation is dict or getattr(annotation, "__origin__", None) is dict:
            values[name] = {}
        else:
            values[name] = None
    return schema.model_construct(**values)


class StubChatModel(BaseChatModel):
    """Minimal BaseChatModel implementation - just enough surface for
    .invoke() and .with_structured_output() to work in the graph.
    """

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=STUB_TEXT))])

    def bind_tools(self, tools, **kwargs) -> "StubChatModel":
        # The stub never actually calls a tool - it always returns the canned
        # response with no tool_calls, which act_node correctly reads as
        # "no more tools needed" and ends the loop.
        return self

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs
    ) -> Runnable:
        if include_raw:
            return RunnableLambda(
                lambda _input: {
                    "raw": AIMessage(content=STUB_TEXT),
                    "parsed": _synthesize(schema),
                    "parsing_error": None,
                }
            )
        return RunnableLambda(lambda _input: _synthesize(schema))
