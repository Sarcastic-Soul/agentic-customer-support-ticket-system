"""Runs against LLM_PROVIDER=stub (real keys live in .env, but this test
must stay free/fast/deterministic - see tests/test_llm_registry.py). With a
stub classifier, intent always synthesizes to something outside the known
INTENTS list, which classify_node normalizes to "unknown" - not a
knowledge-shaped intent, so retrieve is skipped and answer falls back to the
honest "passing this to a specialist" reply. That's a fully deterministic
path worth asserting on its own; the real classify/retrieve/answer behavior
against live Gemini/Groq was verified manually - see docs/PROGRESS.md Stage 4.
"""

from sqlalchemy import select

from app.ingress.pipeline import ingest_message
from app.models import Message, Ticket
from app.workers.tasks import handle_message


async def test_handle_message_runs_agent_and_advances_ticket(session, monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")

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
    assert ticket.intent == "unknown"

    reply = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id,
                Message.direction == "outbound",
            )
        )
    ).scalar_one()
    assert reply.role == "assistant"
    assert "specialist" in reply.body


async def test_handle_message_nonexistent_message_is_a_noop(session, monkeypatch):
    # Must not crash if the job outlives the message it references (e.g. a
    # retry after data was cleaned up) - log and return rather than raising
    # into arq.
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")
    await handle_message({}, 999_999_999, session=session)
