"""arq job functions. handle_message is the one job in Stage 2: it stands in
for the orchestrator until Stage 4 replaces the echo with real reasoning -
the point of this stage is proving the whole loop (webhook/WS -> ingress ->
queue -> worker -> reply) works before any LLM is involved.
"""

from contextlib import AbstractAsyncContextManager, nullcontext

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.channels.base import OutboundMessage
from app.channels.registry import get_adapter
from app.core.tickets import transition_ticket
from app.db.session import async_session_factory
from app.logging import get_logger
from app.models import Message, Ticket

logger = get_logger(__name__)


async def handle_message(
    ctx: dict, message_id: int, *, session: AsyncSession | None = None
) -> None:
    """ctx is arq's per-job context, unused here. `session` is injectable so
    tests can run this against the shared test transaction instead of a real
    connection - arq itself never passes it, so production always opens its
    own session and does the real commit.

    An injected session only gets flush()-ed, never commit()-ed: the test
    fixture binds it to a connection in savepoint mode for rollback-based
    isolation, and calling commit() on that setup trips a SQLAlchemy
    async/greenlet edge case (MissingGreenlet inside the follow-up autobegin).
    flush() is sufficient - the caller's own session already sees the change.
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

        reply_text = f"echo: {message.body}"

        reply = Message(
            conversation=conversation,
            role="assistant",
            body=reply_text,
            channel=message.channel,
            direction="outbound",
        )
        session.add(reply)

        if ticket is not None:
            if ticket.status == "new":
                await transition_ticket(session, ticket, "ai_working", actor_type="ai")
            ticket.ai_turns += 1

        if owns_session:
            await session.commit()
        else:
            await session.flush()

        adapter = get_adapter(message.channel)
        await adapter.send(
            OutboundMessage(
                channel=adapter.channel,
                external_thread_id=conversation.external_thread_id,
                text=reply_text,
            )
        )
        logger.info(
            "handle_message_done",
            message_id=message_id,
            ticket_id=ticket.id if ticket else None,
        )
