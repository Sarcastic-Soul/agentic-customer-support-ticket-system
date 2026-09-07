"""The entrypoint the worker calls: creates the agent_runs row, builds
initial state, invokes the graph, and returns the final state. Owns the
commit-vs-flush decision so individual nodes don't have to know whether
they're running in production or against a test's injected session - see
app/agent/nodes/respond.py and app/workers/tasks.py for why that matters.
"""

from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_graph
from app.agent.state import AgentState
from app.models import AgentRun


async def run_agent(
    session: AsyncSession,
    *,
    ticket_id: int,
    conversation_id: int,
    customer_id: int,
    channel: str,
    external_thread_id: str,
    message_id: int | None,
    latest_message: str,
    trigger: str = "inbound_message",
    owns_session: bool = True,
) -> AgentState:
    run = AgentRun(
        ticket_id=ticket_id,
        message_id=message_id,
        thread_id=f"ticket:{ticket_id}",
        trigger=trigger,
    )
    session.add(run)
    await session.flush()

    initial_state: AgentState = {
        "run_id": run.id,
        "ticket_id": ticket_id,
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "channel": channel,
        "external_thread_id": external_thread_id,
        "latest_message": latest_message,
        "history": [],
        "intent": None,
        "intent_confidence": None,
        "tool_group": None,
        "retrieved": [],
        "tool_results": [],
        "tool_call_count": 0,
        "draft": None,
        "citations": [],
        "verify_repair_attempted": False,
        "verify_feedback": None,
        "verify_passed": None,
        "ai_turns": 0,
        "escalation_reason_code": None,
        "escalation_priority": None,
        "human_note": None,
        "outcome": None,
    }

    graph = await get_graph()
    config = {
        "configurable": {"thread_id": run.thread_id, "session": session},
    }

    try:
        final_state = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        run.outcome = "failed"
        run.error = str(exc)
        if owns_session:
            await session.commit()
        else:
            await session.flush()
        raise

    if owns_session:
        await session.commit()
    else:
        await session.flush()
    return final_state


async def resume_agent(
    session: AsyncSession,
    *,
    ticket_id: int,
    resume_payload: dict,
    owns_session: bool = True,
) -> AgentState:
    """Resumes a graph paused at escalate_node's interrupt() - the console's
    "return to AI" action. Same thread_id as the original run
    (f"ticket:{ticket_id}"), so LangGraph loads the checkpointed state and
    continues inside escalate_node from the interrupt() call, not from
    scratch. Runs against a fresh session by default (console requests are
    not the worker's session), same commit-vs-flush rule as run_agent.
    """
    graph = await get_graph()
    config = {"configurable": {"thread_id": f"ticket:{ticket_id}", "session": session}}

    try:
        final_state = await graph.ainvoke(Command(resume=resume_payload), config=config)
    except Exception:
        if owns_session:
            await session.commit()
        else:
            await session.flush()
        raise

    if owns_session:
        await session.commit()
    else:
        await session.flush()
    return final_state
