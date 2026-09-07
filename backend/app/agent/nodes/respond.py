from datetime import UTC, datetime
from decimal import Decimal

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.agent.state import AgentState
from app.channels.base import Channel, OutboundMessage
from app.channels.registry import get_adapter
from app.core.tickets import transition_ticket
from app.llm.pricing import estimate_cost_usd
from app.models import AgentRun, AgentStep, Message, Ticket


async def respond_node(state: AgentState, config: RunnableConfig) -> dict:
    """Persists the reply, advances the ticket, finalizes the agent_runs row,
    and sends the reply through the channel adapter. The last node in the
    graph - everything after this is I/O, not reasoning.
    """
    session = config["configurable"]["session"]

    reply = Message(
        conversation_id=state["conversation_id"],
        role="assistant",
        body=state["draft"],
        channel=state["channel"],
        direction="outbound",
    )
    session.add(reply)

    ticket = await session.get(Ticket, state["ticket_id"])
    if ticket is not None:
        if ticket.status == "new":
            await transition_ticket(session, ticket, "ai_working", actor_type="ai")
        ticket.ai_turns += 1
        ticket.intent = state["intent"]
        if ticket.first_response_at is None:
            ticket.first_response_at = datetime.now(UTC)

    run = await session.get(AgentRun, state["run_id"])
    if run is not None:
        run.outcome = state["outcome"]
        run.intent = state["intent"]
        run.confidence = state["intent_confidence"]
        run.finished_at = datetime.now(UTC)

        steps = (
            await session.execute(select(AgentStep).where(AgentStep.run_id == state["run_id"]))
        ).scalars().all()
        run.total_tokens_in = sum(s.tokens_in or 0 for s in steps)
        run.total_tokens_out = sum(s.tokens_out or 0 for s in steps)
        run.est_cost_usd = sum(
            (
                estimate_cost_usd(s.model.split(":", 1)[1], s.tokens_in or 0, s.tokens_out or 0)
                for s in steps
                if s.model
            ),
            Decimal(0),
        )
        run.latency_ms = sum(s.latency_ms or 0 for s in steps)

    # Commit is the caller's call (app/agent/run.py), not this node's - same
    # reasoning as app/workers/tasks.py: a session injected by the test
    # fixture (savepoint-joined, for rollback-based isolation) trips a
    # SQLAlchemy async/greenlet edge case on commit(). flush() here is
    # enough for the adapter.send() below, which doesn't read from the DB.
    await session.flush()

    adapter = get_adapter(Channel(state["channel"]))
    receipt = await adapter.send(
        OutboundMessage(
            channel=adapter.channel,
            external_thread_id=state["external_thread_id"],
            text=state["draft"],
        )
    )
    reply.delivery_status = "sent" if receipt.ok else "failed"
    if receipt.ok and receipt.detail:
        reply.external_message_id = receipt.detail
    await session.flush()

    return {}
