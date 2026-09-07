from sqlalchemy import select

from app.ingress.pipeline import ingest_message
from app.models import Message, Ticket
from app.workers.tasks import handle_message


async def test_handle_message_echoes_and_advances_ticket(session):
    message = await ingest_message(
        session,
        channel="web",
        external_thread_id="worker-test-session",
        sender_external_id="worker-test-session",
        text="hello there",
        external_message_id="worker-test-msg-1",
        raw_payload={},
    )
    await session.flush()

    ticket = (
        await session.execute(
            select(Ticket).where(Ticket.conversation_id == message.conversation_id)
        )
    ).scalar_one()
    assert ticket.status == "new"

    await handle_message({}, message.id, session=session)
    await session.flush()

    await session.refresh(ticket)
    assert ticket.status == "ai_working"
    assert ticket.ai_turns == 1

    reply = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id,
                Message.direction == "outbound",
            )
        )
    ).scalar_one()
    assert reply.body == "echo: hello there"
    assert reply.role == "assistant"
