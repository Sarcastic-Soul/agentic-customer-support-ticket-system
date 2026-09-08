"""arq job functions. handle_message runs the real agent graph (Stage 4) -
it used to just echo the message back (Stage 2), which proved the queue/
worker/adapter loop worked before any LLM was involved. That echo path is
gone now; classify/retrieve/answer/respond do the actual work.
"""

from contextlib import AbstractAsyncContextManager, nullcontext
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.run import run_agent
from app.channels.base import Channel, OutboundMessage
from app.channels.registry import get_adapter
from app.core.tickets import ALLOWED_TRANSITIONS, transition_ticket
from app.db.session import async_session_factory
from app.logging import get_logger
from app.models import Conversation, Escalation, Message, Ticket

logger = get_logger(__name__)

SYSTEM_ERROR_REASON = "system_error"


async def _escalate_on_failure(
    session: AsyncSession,
    *,
    ticket: Ticket,
    conversation: Conversation,
    message: Message,
    error: str,
) -> None:
    """Stage 12's "never silence" requirement: if the graph raises for any
    reason (every LLM provider down, a tool blowing up unexpectedly, a bug),
    the customer still gets an honest message and a human still gets
    paged - deliberately deterministic, no LLM call of its own, so it works
    even in exactly the scenario that triggered it (both providers dead).

    Idempotency guard mirrors escalate_node's: arq may retry a failed job,
    and a second identical failure must not create a second escalation or
    send the apology twice.
    """
    if "escalated" not in ALLOWED_TRANSITIONS.get(ticket.status, set()):
        return

    existing = (
        await session.execute(
            select(Escalation).where(
                Escalation.ticket_id == ticket.id,
                Escalation.reason_code == SYSTEM_ERROR_REASON,
                Escalation.status != "resolved",
            )
        )
    ).scalars().first()
    if existing is not None:
        return

    await transition_ticket(
        session, ticket, "escalated",
        actor_type="system", payload={"reason_code": SYSTEM_ERROR_REASON},
    )

    detail = "The AI encountered an internal error and could not respond automatically."
    session.add(
        Escalation(
            ticket_id=ticket.id,
            reason_code=SYSTEM_ERROR_REASON,
            reason_detail=detail,
            priority="P2",
            required_skill=None,
            handoff_packet={
                "ticket_reference": ticket.reference,
                "escalation_reason": SYSTEM_ERROR_REASON,
                "reason_detail": detail,
                "priority": "P2",
                "required_skill": None,
                "summary": message.body,
                "timeline": [
                    {"who": "customer", "what": message.body},
                    {"who": "system", "what": f"Error: {error}"},
                ],
                "entities": {},
                "suggested_reply": None,
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )
    )

    ack_text = (
        f"I'm having trouble processing your message right now. I've flagged "
        f"this for a specialist, reference {ticket.reference}. They'll follow up shortly."
    )
    ack_message = Message(
        conversation_id=conversation.id, role="assistant", body=ack_text,
        channel=message.channel, direction="outbound",
    )
    session.add(ack_message)
    await session.flush()

    adapter = get_adapter(Channel(message.channel))
    receipt = await adapter.send(
        OutboundMessage(
            channel=adapter.channel,
            external_thread_id=conversation.external_thread_id,
            text=ack_text,
        )
    )
    ack_message.delivery_status = "sent" if receipt.ok else "failed"
    if receipt.ok and receipt.detail:
        ack_message.external_message_id = receipt.detail
    await session.flush()


async def handle_message(
    ctx: dict, message_id: int, *, session: AsyncSession | None = None
) -> None:
    """ctx is arq's per-job context, unused here. `session` is injectable so
    tests can run this against the shared test transaction instead of a real
    connection - arq itself never passes it, so production always opens its
    own session and does the real commit. See app/agent/run.py's
    `owns_session` for why this matters (MissingGreenlet on commit() against
    a test's savepoint-joined session).
    """
    owns_session = session is None
    session_ctx: AbstractAsyncContextManager[AsyncSession] = (
        async_session_factory() if owns_session else nullcontext(session)
    )
    async with session_ctx as session:
        result = await session.execute(
            select(Message)
            .options(selectinload(Message.conversation))
            .where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            logger.warning("handle_message_missing", message_id=message_id)
            return

        conversation = message.conversation

        ticket_result = await session.execute(
            select(Ticket)
            .where(Ticket.conversation_id == conversation.id)
            .order_by(Ticket.created_at.desc())
            .limit(1)
        )
        ticket = ticket_result.scalar_one_or_none()
        if ticket is None:
            logger.warning("handle_message_no_ticket", message_id=message_id)
            return

        if ticket.status in ("escalated", "human_working"):
            # A human owns this ticket - the message is already persisted
            # (the console shows it live), but the graph's checkpoint for
            # this thread is either mid-run or paused at an interrupt.
            # Invoking it again here with a fresh input isn't the resume
            # protocol (Command(resume=...) is, via app.agent.run.resume_agent
            # from the console) and would be undefined behaviour on an
            # interrupted thread. The AI stays quiet until the human acts.
            logger.info(
                "handle_message_skipped_human_owned",
                message_id=message_id, ticket_id=ticket.id, status=ticket.status,
            )
            return

        try:
            final_state = await run_agent(
                session,
                ticket_id=ticket.id,
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                channel=message.channel,
                external_thread_id=conversation.external_thread_id,
                message_id=message.id,
                latest_message=message.body_redacted or message.body,
                owns_session=owns_session,
            )
        except Exception as exc:  # noqa: BLE001 - the customer must hear *something*, whatever broke
            logger.exception("handle_message_failed", message_id=message_id, ticket_id=ticket.id)
            # run_agent already committed/flushed its own "outcome=failed"
            # AgentRun row before re-raising - this session is clean to reuse.
            await _escalate_on_failure(
                session, ticket=ticket, conversation=conversation, message=message, error=str(exc)
            )
            if owns_session:
                await session.commit()
            else:
                await session.flush()
            return

        # final_state["outcome"] is set by answer_node ("answered") before
        # verify_node ever runs, and is never updated if verify then routes
        # to escalate_node instead of respond_node - the graph pauses at
        # interrupt() with that stale value still in state. The ticket's own
        # (freshly committed) status is what actually happened.
        await session.refresh(ticket)
        actual_outcome = (
            "escalated" if ticket.status in ("escalated", "human_working")
            else final_state["outcome"]
        )
        logger.info(
            "handle_message_done",
            message_id=message_id,
            ticket_id=ticket.id,
            intent=final_state["intent"],
            outcome=actual_outcome,
        )
