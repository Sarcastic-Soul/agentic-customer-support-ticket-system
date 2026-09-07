"""arq job functions. handle_message runs the real agent graph (Stage 4) -
it used to just echo the message back (Stage 2), which proved the queue/
worker/adapter loop worked before any LLM was involved. That echo path is
gone now; classify/retrieve/answer/respond do the actual work.
"""

from contextlib import AbstractAsyncContextManager, nullcontext

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.run import run_agent
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

        final_state = await run_agent(
            session,
            ticket_id=ticket.id,
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            channel=message.channel,
            external_thread_id=conversation.external_thread_id,
            message_id=message.id,
            latest_message=message.body,
            owns_session=owns_session,
        )

        logger.info(
            "handle_message_done",
            message_id=message_id,
            ticket_id=ticket.id,
            intent=final_state["intent"],
            outcome=final_state["outcome"],
        )
