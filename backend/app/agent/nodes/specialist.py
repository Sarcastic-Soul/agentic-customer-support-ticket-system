"""One specialist agent: a bounded tool loop over its own domain's tools,
with its own prompt. Several run in parallel for a message that asks for
more than one thing ("where is my order, and refund the duplicate charge").

Specialists never change anything. Write tools run with propose_only=True:
they check eligibility and authorize() as usual and say what they *would*
do. reconcile decides which proposals survive when specialists disagree,
and commit does them for real. That is what makes a conflict between two
agents something to resolve rather than something already done twice.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

import app.tools  # noqa: F401 - import for its @register_tool side effects
from app.agent.progress import DEFAULT_TOOL_LABEL, TOOL_LABELS, emit_progress
from app.agent.prompts import load_prompt
from app.agent.specialists import prompt_for, tools_for
from app.agent.steps import record_step, session_lock
from app.llm.registry import get_llm
from app.llm.roles import LLMRole
from app.tools.context import ToolContext
from app.tools.registry import build_langchain_tools, execute_tool, get_tool_spec


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    return "\n".join(f"{m['role']}: {m['body']}" for m in history)


async def specialist_node(state: dict, config: RunnableConfig) -> dict:
    """`state` is the Send payload from supervisor.dispatch: the graph state
    plus "agent" (which specialist this branch is) and "budget" (its share
    of MAX_TOOL_CALLS). Returns one report for reconcile.
    """
    session = config["configurable"]["session"]
    lock = session_lock(session)
    agent: str = state["agent"]
    budget: int = state["budget"]
    tool_names = tools_for(agent)

    ctx = ToolContext(
        session=session,
        customer_id=state["customer_id"],
        ticket_id=state["ticket_id"],
        run_id=state["run_id"],
        propose_only=True,
    )

    system_prompt = load_prompt(
        prompt_for(agent),
        intent=state["intent"],
        secondary_intent=state.get("secondary_intent") or "none",
        history=_format_history(state["history"]),
        message=state["latest_message"],
    )
    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["latest_message"]),
    ]

    tool_results: list[dict] = []
    proposals: list[dict] = []
    note: str | None = None
    call_count = 0
    client = get_llm(LLMRole.reason)

    while call_count < budget:
        async with lock:
            step = await record_step(
                session, run_id=state["run_id"], node="specialist", agent=agent
            )
        langchain_tools = build_langchain_tools(tool_names, ctx, step_id=step.id)

        outcome = await client.ainvoke(messages, tools=langchain_tools)

        step.model = f"{outcome.provider}:{outcome.model}"
        step.tokens_in = outcome.tokens_in
        step.tokens_out = outcome.tokens_out
        step.latency_ms = outcome.latency_ms
        step.output = {
            "tool_calls": [tc["name"] for tc in outcome.tool_calls], "text": outcome.text,
        }
        async with lock:
            await session.flush()

        if not outcome.tool_calls:
            note = outcome.text
            break

        messages.append(AIMessage(content=outcome.text or "", tool_calls=outcome.tool_calls))

        for tool_call in outcome.tool_calls:
            if call_count >= budget:
                break
            call_count += 1
            try:
                spec = get_tool_spec(tool_call["name"])
            except KeyError:
                spec = None
            if spec is None or spec.name not in tool_names:
                # A model can call a tool name outside the bound schema -
                # found live during Stage 11 (gemini-3.5-flash-lite
                # hallucinated one). Tell it, don't crash the graph.
                result = {
                    "error": "unknown_tool",
                    "hint": f"{tool_call['name']!r} is not one of your tools",
                }
            else:
                await emit_progress(
                    config, "specialist",
                    TOOL_LABELS.get(spec.name, DEFAULT_TOOL_LABEL), agent=agent,
                )
                async with lock:
                    result = await execute_tool(spec, ctx, tool_call["args"], step_id=step.id)

            entry = {"tool": tool_call["name"], "args": tool_call["args"], "result": result}
            if result.get("proposed"):
                proposals.append({**entry, "agent": agent, "id": f"{agent}:{len(proposals) + 1}"})
                # The model is told the action is queued, so it doesn't
                # retry it hoping for a "done".
                shown = {**result, "note": "queued - it will be carried out after review"}
            else:
                tool_results.append(entry)
                shown = result
            messages.append(ToolMessage(content=str(shown), tool_call_id=tool_call["id"]))

    return {
        "specialist_reports": [{
            "agent": agent,
            "tool_results": tool_results,
            "proposals": proposals,
            "note": note,
            "tool_calls": call_count,
            "budget": budget,
        }]
    }
