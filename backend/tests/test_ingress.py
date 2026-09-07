from sqlalchemy import select

from app.ingress.pipeline import ingest_message
from app.models import Customer, Ticket


async def test_ingest_creates_customer_conversation_and_ticket(session):
    message = await ingest_message(
        session,
        channel="web",
        external_thread_id="session-abc",
        sender_external_id="session-abc",
        text="where is my order ORD-10432?",
        external_message_id="msg-1",
        raw_payload={"text": "where is my order ORD-10432?"},
    )
    await session.flush()

    assert message is not None
    assert message.body == "where is my order ORD-10432?"

    customer = await session.get(Customer, message.conversation.customer_id)
    assert customer is not None
    assert customer.verified is False

    result = await session.execute(
        select(Ticket).where(Ticket.conversation_id == message.conversation_id)
    )
    ticket = result.scalar_one()
    assert ticket.status == "new"
    assert ticket.reference.startswith("T-")


async def test_replayed_external_message_id_is_dropped(session):
    first = await ingest_message(
        session,
        channel="whatsapp",
        external_thread_id="+919800000001",
        sender_external_id="+919800000001",
        text="hello",
        external_message_id="wamid-1",
        raw_payload={},
    )
    await session.flush()
    assert first is not None

    replay = await ingest_message(
        session,
        channel="whatsapp",
        external_thread_id="+919800000001",
        sender_external_id="+919800000001",
        text="hello",
        external_message_id="wamid-1",
        raw_payload={},
    )

    assert replay is None


async def test_same_sender_resolves_to_same_customer(session):
    first = await ingest_message(
        session,
        channel="whatsapp",
        external_thread_id="+919800000002",
        sender_external_id="+919800000002",
        text="first message",
        external_message_id="wamid-2a",
        raw_payload={},
    )
    await session.flush()

    second = await ingest_message(
        session,
        channel="whatsapp",
        external_thread_id="+919800000002",
        sender_external_id="+919800000002",
        text="second message",
        external_message_id="wamid-2b",
        raw_payload={},
    )
    await session.flush()

    assert first.conversation.customer_id == second.conversation.customer_id
    # same open thread within the idle window -> same conversation
    assert first.conversation_id == second.conversation_id
