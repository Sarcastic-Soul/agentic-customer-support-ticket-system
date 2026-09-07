"""Conversation threading: find or open the conversation an inbound message
belongs to, and the ticket that backs it.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Conversation, Customer, Ticket

IDLE_WINDOW = timedelta(hours=settings.conversation_idle_hours)


async def get_or_open_conversation(
    session: AsyncSession, *, customer: Customer, channel: str, external_thread_id: str
) -> tuple[Conversation, bool]:
    """Return (conversation, created). A new conversation starts after the
    idle window or if the thread has never been seen.
    """
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.channel == channel,
            Conversation.external_thread_id == external_thread_id,
            Conversation.status != "closed",
        )
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    if conversation is not None:
        now = datetime.now(UTC)
        stale = now - conversation.last_message_at > IDLE_WINDOW
        if not stale:
            return conversation, False
        conversation.status = "closed"
        conversation.closed_at = now

    conversation = Conversation(
        customer_id=customer.id, channel=channel, external_thread_id=external_thread_id
    )
    session.add(conversation)
    await session.flush()
    return conversation, True


def _next_ticket_reference(ticket_id: int) -> str:
    return f"T-{1000 + ticket_id}"


async def get_or_open_ticket(
    session: AsyncSession, *, conversation: Conversation, channel: str
) -> tuple[Ticket, bool]:
    """One open ticket per conversation. Closed tickets don't get reused -
    a new message on a closed thread's conversation opens a fresh ticket.

    Queries explicitly rather than reading conversation.ticket: once a
    Conversation has been flushed, its unset relationship attributes are
    "not loaded" and touching them triggers an async lazy-load, which fails
    outside a greenlet context. An explicit select sidesteps that entirely.
    """
    result = await session.execute(
        select(Ticket)
        .where(Ticket.conversation_id == conversation.id)
        .order_by(Ticket.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None and existing.status != "closed":
        return existing, False

    ticket = Ticket(
        reference="PENDING",
        customer_id=conversation.customer_id,
        conversation_id=conversation.id,
        channel=channel,
    )
    session.add(ticket)
    await session.flush()
    ticket.reference = _next_ticket_reference(ticket.id)
    return ticket, True
