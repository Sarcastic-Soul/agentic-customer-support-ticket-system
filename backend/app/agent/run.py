"""The entrypoint the worker calls: creates the agent_runs row, builds
initial state, invokes the graph, and returns the final state. Owns the
commit-vs-flush decision so individual nodes don't have to know whether
they're running in production or against a test's injected session - see
app/agent/nodes/respond.py and app/workers/tasks.py for why that matters.
"""

import asyncio
from contextlib import asynccontextmanager

from langgraph.types import Command
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_graph
from app.agent.progress import web_progress_publisher
from app.agent.state import AgentState
from app.config import settings
from app.models import AgentRun
from app.observability import flush_traces, trace_config


@asynccontextmanager
async def _graph_config(
    *,
    thread_id: str,
    session: AsyncSession,
    ticket_id: int,
    run_id: int | None,
    channel: str | None,
    external_thread_id: str | None,
    publish_progress: bool,
):
    """The graph config for one run: thread + session as always, plus a
    progress publisher for web chat (app/agent/progress.py) and Langfuse
    callbacks when tracing is on (app/observability.py)."""
    config: dict = {
        "configurable": {"thread_id": thread_id, "session": session},
        **trace_config(ticket_id=ticket_id, run_id=run_id, channel=channel),
    }
    redis: Redis | None = None
    if publish_progress and channel == "web" and external_thread_id:
        redis = Redis.from_url(settings.redis_url)
        config["configurable"]["progress"] = web_progress_publisher(redis, external_thread_id)
    try:
        yield config
    finally:
        if redis is not None:
            await redis.aclose()
        # Langfuse's flush blocks on the export - keep it off the event loop
        await asyncio.to_thread(flush_traces)


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
    publish_progress: bool = False,
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
        "secondary_intent": None,
        "tool_group": None,
        "specialists": [],
        "retrieved": [],
        "specialist_reports": None,  # None clears last turn's reports (see merge_reports)
        "conflicts": [],
        "to_commit": [],
        "force_approval": [],
        "tool_results": [],
        "tool_call_count": 0,
        "draft": None,
        "citations": [],
        "verify_repairs": 0,
        "verify_feedback": None,
        "verify_passed": None,
        "ai_turns": 0,
        # "clarifications" is left out on purpose: it carries over from the
        # ticket thread's checkpoint so repeated unclear turns still add up.
        "escalation_reason_code": None,
        "escalation_priority": None,
        "human_note": None,
        "outcome": None,
    }

    graph = await get_graph()

    try:
        async with _graph_config(
            thread_id=run.thread_id,
            session=session,
            ticket_id=ticket_id,
            run_id=run.id,
            channel=channel,
            external_thread_id=external_thread_id,
            publish_progress=publish_progress,
        ) as config:
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
    publish_progress: bool = False,
) -> AgentState:
    """Resumes a graph paused at escalate_node's interrupt() - the console's
    "return to AI" action. Same thread_id as the original run
    (f"ticket:{ticket_id}"), so LangGraph loads the checkpointed state and
    continues inside escalate_node from the interrupt() call, not from
    scratch. Runs against a fresh session by default (console requests are
    not the worker's session), same commit-vs-flush rule as run_agent.
    """
    graph = await get_graph()
    thread_id = f"ticket:{ticket_id}"
    # The paused state knows which channel the customer is on
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    paused = snapshot.values if snapshot else {}

    try:
        async with _graph_config(
            thread_id=thread_id,
            session=session,
            ticket_id=ticket_id,
            run_id=paused.get("run_id"),
            channel=paused.get("channel"),
            external_thread_id=paused.get("external_thread_id"),
            publish_progress=publish_progress,
        ) as config:
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
