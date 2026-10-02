"""Carries out the proposals that survived reconcile. Each one goes back
through execute_tool with propose_only=False, so authorize() runs again on
the current data - nothing is trusted just because it was approved as a
proposal a moment ago. No LLM call here.
"""

from langchain_core.runnables import RunnableConfig

import app.tools  # noqa: F401 - import for its @register_tool side effects
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.tools.context import ToolContext
from app.tools.registry import execute_tool, get_tool_spec


async def commit_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]
    proposals = state.get("to_commit") or []
    if not proposals:
        return {}

    force = set(state.get("force_approval") or [])
    tool_results = list(state["tool_results"])
    for p in proposals:
        step = await record_step(session, run_id=state["run_id"], node="commit", agent=p["agent"])
        ctx = ToolContext(
            session=session,
            customer_id=state["customer_id"],
            ticket_id=state["ticket_id"],
            run_id=state["run_id"],
            force_approval=p["args"].get("txn_ref") in force,
        )
        result = await execute_tool(get_tool_spec(p["tool"]), ctx, p["args"], step_id=step.id)
        step.output = {"proposal": p["id"], "tool": p["tool"], "result": result}
        tool_results.append(
            {"tool": p["tool"], "args": p["args"], "agent": p["agent"], "result": result}
        )
    await session.flush()
    return {"tool_results": tool_results, "to_commit": []}
