from langgraph.types import interrupt
from sqlalchemy import select

from app.agent.escalation import build_handoff_packet
from app.agent.state import AgentState
from app.channels.base import Channel, OutboundMessage
from app.channels.registry import get_adapter
from app.core.tickets import transition_ticket
from app.models import Customer, Escalation, Message, Ticket


async def escalate_node(state: AgentState, config) -> dict:
    """Builds the handoff packet, queues the escalation, acknowledges the
    customer, then pauses the graph with interrupt(). Execution resumes by
    RE-RUNNING THIS ENTIRE FUNCTION FROM THE TOP - LangGraph does not resume
    "mid-function" the way a generator would. interrupt() calls are replayed
    in order and immediately return their cached resume value on replay, but
    everything else in the function - every side effect before and after
    that line - genuinely re-executes. Found the hard way: without the guard
    below, a resume tries to create a second Escalation row and re-run
    transition_ticket("escalated") on a ticket already in "escalated"
    (or worse, already moved on), raising InvalidTransition. See
    docs/PROGRESS.md Stage 6.

    The guard: look for an existing, not-yet-resolved escalation for this
    ticket with this exact reason_code before doing any of the one-time
    setup. First attempt -> none found -> build everything. Any replay
    within the same escalation cycle -> found -> reuse it, skip straight to
    the interrupt() call.
    """
    session = config["configurable"]["session"]

    ticket = await session.get(Ticket, state["ticket_id"])

    escalation = (
        await session.execute(
            select(Escalation)
            .where(
                Escalation.ticket_id == ticket.id,
                Escalation.reason_code == state["escalation_reason_code"],
                Escalation.status != "resolved",
            )
            .order_by(Escalation.created_at.desc())
        )
    ).scalars().first()

    if escalation is None:
        customer = await session.get(Customer, state["customer_id"])
        packet = await build_handoff_packet(state, ticket=ticket, customer=customer)

        escalation = Escalation(
            ticket_id=ticket.id,
            reason_code=state["escalation_reason_code"],
            reason_detail=packet["reason_detail"],
            priority=state["escalation_priority"],
            handoff_packet=packet,
            required_skill=packet["required_skill"],
        )
        session.add(escalation)

        await transition_ticket(
            session, ticket, "escalated", actor_type="ai",
            payload={"reason_code": state["escalation_reason_code"]},
        )
        ticket.ai_turns += 1

        ack_text = (
            f"I've passed this to a specialist, reference {ticket.reference}. "
            "They'll follow up shortly."
        )
        session.add(
            Message(
                conversation_id=state["conversation_id"], role="assistant", body=ack_text,
                channel=state["channel"], direction="outbound",
            )
        )
        await session.flush()

        adapter = get_adapter(Channel(state["channel"]))
        await adapter.send(
            OutboundMessage(
                channel=adapter.channel,
                external_thread_id=state["external_thread_id"],
                text=ack_text,
            )
        )

    decision = interrupt({
        "type": "escalation",
        "escalation_id": escalation.id,
        "ticket_id": ticket.id,
        "packet": escalation.handoff_packet,
    })

    if isinstance(decision, dict) and decision.get("action") == "return_to_ai":
        return {
            "human_note": decision.get("note"),
            "escalation_reason_code": None,
            "escalation_priority": None,
            "verify_repair_attempted": False,
            "verify_passed": None,
            "outcome": None,
        }

    return {"outcome": "escalated"}


def route_after_escalate(state: AgentState) -> str:
    # Resumed with a human note -> the AI composes a fresh reply using it
    # (existing retrieved/tool_results context, no redundant tool calls -
    # the human already acted on whatever needed approval). Any other
    # resume (or none, if the thread stays paused after "resolve" - see
    # docs/PROGRESS.md Stage 6) ends the run here.
    return "answer" if state.get("human_note") else "end"
