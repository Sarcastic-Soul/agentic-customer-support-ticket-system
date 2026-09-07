"""Runs against LLM_PROVIDER=stub (real keys live in .env, but this test
must stay free/fast/deterministic - see tests/test_llm_registry.py). The
stub's structured-output synthesis defaults to the "happy path" (confidence
0.95, all verdict booleans True - see app/llm/stub.py) so a plain message
runs the full classify -> plan -> retrieve -> act -> answer -> verify ->
respond path without spuriously escalating. A stub-classified intent always
lands outside the known INTENTS list and normalizes to "unknown", which
plan_node maps to tool_group "none" (chitchat) - no retrieval, no tools, a
plain conversational reply. The real classify/plan/retrieve/act/answer/verify
behaviour against live Gemini/Groq, including a genuine escalation, was
verified manually - see docs/PROGRESS.md Stage 5 and 6.
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
    assert reply.body  # stub's canned text - content itself isn't the point here


async def test_handle_message_nonexistent_message_is_a_noop(session, monkeypatch):
    # Must not crash if the job outlives the message it references (e.g. a
    # retry after data was cleaned up) - log and return rather than raising
    # into arq.
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")
    await handle_message({}, 999_999_999, session=session)
