from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

import app.tools  # noqa: F401 - import for its @register_tool side effects
from app.agent.nodes.plan import tools_for_group
from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.config import settings
from app.llm.registry import get_llm
from app.llm.roles import LLMRole
from app.tools.context import ToolContext
from app.tools.registry import build_langchain_tools, execute_tool, get_tool_spec


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    return "\n".join(f"{m['role']}: {m['body']}" for m in history)


async def act_node(state: AgentState, config: RunnableConfig) -> dict:
    """Bounded tool loop: the model decides which tools to call (if any),
    they're executed through the policy-checked registry, and their results
    feed back in until the model stops calling tools or MAX_TOOL_CALLS is
    hit - whichever comes first. The "none"/"knowledge" tool groups skip
    this node entirely; there is nothing to call.
    """
    session = config["configurable"]["session"]
    tool_names = tools_for_group(state["tool_group"])
    if not tool_names:
        return {"tool_results": []}

    ctx = ToolContext(
        session=session,
        customer_id=state["customer_id"],
        ticket_id=state["ticket_id"],
        run_id=state["run_id"],
    )

    system_prompt = load_prompt(
        "act",
        intent=state["intent"],
        history=_format_history(state["history"]),
        message=state["latest_message"],
    )
    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["latest_message"]),
    ]

    tool_results: list[dict] = []
    call_count = 0
    client = get_llm(LLMRole.reason)

    while call_count < settings.max_tool_calls:
        step = await record_step(session, run_id=state["run_id"], node="act")

        langchain_tools = build_langchain_tools(tool_names, ctx, step_id=step.id)
        outcome = await client.ainvoke(messages, tools=langchain_tools)

        step.model = f"{outcome.provider}:{outcome.model}"
        step.tokens_in = outcome.tokens_in
        step.tokens_out = outcome.tokens_out
        step.latency_ms = outcome.latency_ms
        step.output = {
            "tool_calls": [tc["name"] for tc in outcome.tool_calls],
            "text": outcome.text,
        }
        await session.flush()

        if not outcome.tool_calls:
            break

        messages.append(
            AIMessage(content=outcome.text or "", tool_calls=outcome.tool_calls)
        )

        for tool_call in outcome.tool_calls:
            if call_count >= settings.max_tool_calls:
                break
            call_count += 1
            try:
                spec = get_tool_spec(tool_call["name"])
            except KeyError:
                # A model can call a tool name outside the bound schema -
                # found live during Stage 11's eval run (gemini-3.5-flash-lite
                # hallucinated a tool name that was never offered). Same
                # shape of recovery as execute_tool's own error handling:
                # tell the model, don't crash the graph over it.
                result = {
                    "error": "unknown_tool",
                    "hint": f"{tool_call['name']!r} is not an available tool",
                }
                tool_results.append(
                    {"tool": tool_call["name"], "args": tool_call["args"], "result": result}
                )
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )
                continue
            result = await execute_tool(spec, ctx, tool_call["args"], step_id=step.id)
            tool_results.append(
                {"tool": tool_call["name"], "args": tool_call["args"], "result": result}
            )
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_call["id"])
            )

    return {"tool_results": tool_results, "tool_call_count": call_count}
