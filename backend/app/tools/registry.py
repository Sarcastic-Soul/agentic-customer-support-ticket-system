"""Tool registration and execution. Tools are plain async functions taking
(ctx: ToolContext, **args) and returning a JSON-serializable dict - never a
raw ORM object. The Pydantic args_schema is what the LLM actually sees;
ctx is injected by build_langchain_tools() via closure, so it is never part
of the schema and the model can never supply it.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.logging import get_logger
from app.models import ToolCall
from app.policy.authorize import Decision
from app.tools.context import ToolContext

logger = get_logger(__name__)

ToolFunc = Callable[..., Awaitable[dict]]


@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: type[BaseModel]
    func: ToolFunc
    write: bool = False  # write tools' results are checked for a policy denial


_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(
    name: str, description: str, args_schema: type[BaseModel], *, write: bool = False
):
    def decorator(func: ToolFunc) -> ToolFunc:
        _REGISTRY[name] = ToolSpec(
            name=name, description=description, args_schema=args_schema, func=func, write=write
        )
        return func

    return decorator


def get_tool_spec(name: str) -> ToolSpec:
    return _REGISTRY[name]


async def execute_tool(
    spec: ToolSpec, ctx: ToolContext, args: dict, *, step_id: int | None = None
) -> dict:
    """Runs one tool call, recording a tool_calls row regardless of outcome.
    Deny/error results are returned as structured dicts, not exceptions -
    the model needs to see *why* a tool call didn't do what it asked, not
    just that something broke.
    """
    start = time.monotonic()
    result: dict
    error: str | None = None
    authorized = True
    deny_reason: str | None = None

    try:
        result = await spec.func(ctx, **args)
        if spec.write and result.get("denied"):
            authorized = False
            deny_reason = result.get("reason")
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as a structured error
        logger.warning("tool_call_failed", tool=spec.name, args=args, error=str(exc))
        result = {"error": "tool_execution_failed", "hint": str(exc)}
        error = str(exc)

    latency_ms = int((time.monotonic() - start) * 1000)

    ctx.session.add(
        ToolCall(
            step_id=step_id,
            ticket_id=ctx.ticket_id,
            tool_name=spec.name,
            arguments=args,
            result=result,
            authorized=authorized,
            deny_reason=deny_reason,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await ctx.session.flush()
    return result


def build_langchain_tools(
    names: list[str], ctx: ToolContext, *, step_id: int | None = None
) -> list[StructuredTool]:
    tools = []
    for name in names:
        spec = get_tool_spec(name)

        async def _invoke(_spec=spec, **kwargs) -> dict:
            return await execute_tool(_spec, ctx, kwargs, step_id=step_id)

        tools.append(
            StructuredTool.from_function(
                coroutine=_invoke,
                name=spec.name,
                description=spec.description,
                args_schema=spec.args_schema,
            )
        )
    return tools


__all__ = [
    "ToolSpec",
    "register_tool",
    "get_tool_spec",
    "execute_tool",
    "build_langchain_tools",
    "Decision",
]
