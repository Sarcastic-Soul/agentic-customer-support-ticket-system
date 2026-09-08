"""Shared ingress pipeline: the steps every channel's webhook goes through
before the orchestrator ever sees a message. Channel adapters and the arq
worker (Stage 2+) call this; the dev simulator endpoint calls it directly.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.conversation import get_or_open_conversation, get_or_open_ticket
from app.core.identity import resolve_customer
from app.core.pii import redact_pii
from app.models import Message, RawEvent


async def ingest_message(
    session: AsyncSession,
    *,
    channel: str,
    external_thread_id: str,
    sender_external_id: str,
    text: str,
    external_message_id: str,
    raw_payload: dict,
) -> Message | None:
    """Persist the raw event, dedupe on (channel, external_message_id), resolve
    identity, thread the conversation, open/attach a ticket, and store the
    message. Returns None if this external_message_id was already processed -
    the caller (webhook handler) should still ack 200 in that case; retried
    webhooks are expected, not an error.

    Checks for the existing row before inserting rather than racing the
    UNIQUE (channel, external_message_id) constraint and catching the
    IntegrityError: a caught error still poisons the session's transaction
    (SQLAlchemy 2.0 async requires an explicit rollback to recover, not just
    a savepoint), which is more moving parts than a webhook retry - the
    expected case, not a rare one - deserves. The constraint stays in the
    schema as the backstop for a genuine concurrent-delivery race; that rare
    case surfacing as a 500 is acceptable prototype tolerance.
    """
    existing = await session.execute(
        select(Message.id).where(
            Message.channel == channel, Message.external_message_id == external_message_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    session.add(RawEvent(channel=channel, payload=raw_payload, signature_ok=True))

    customer, _ = await resolve_customer(session, channel=channel, external_id=sender_external_id)
    conversation, _ = await get_or_open_conversation(
        session, customer=customer, channel=channel, external_thread_id=external_thread_id
    )
    ticket, _ = await get_or_open_ticket(session, conversation=conversation, channel=channel)

    # Assign the relationship object (not just conversation_id) so callers can
    # read message.conversation without triggering an async lazy-load.
    # body_redacted is what every prompt-building path reads (prepare_node's
    # history, handle_message's latest_message) - body itself is kept
    # unredacted for audit, same as raw_events never being edited.
    message = Message(
        conversation=conversation,
        role="customer",
        body=text,
        body_redacted=redact_pii(text),
        channel=channel,
        direction="inbound",
        external_message_id=external_message_id,
    )
    session.add(message)
    await session.flush()

    conversation.last_message_at = message.created_at
    return message
