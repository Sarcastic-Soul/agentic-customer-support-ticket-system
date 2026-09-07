"""The interrupt()/Command(resume=...) path is Stage 6's core mechanic -
these tests exercise it against the real graph and a real (checkpointed)
Postgres-backed thread, not a mock. Runs on LLM_PROVIDER=stub (see
tests/test_worker.py for why that's the happy-path default, not a trap).
"""

from sqlalchemy import select

from app.agent.run import resume_agent, run_agent
from app.ingress.pipeline import ingest_message
from app.models import Escalation, Message, Ticket


async def _make_ticket(session, text: str, *, external_message_id: str):
    message = await ingest_message(
        session,
        channel="web",
        external_thread_id=external_message_id,  # unique per test, doubles as thread id seed
        sender_external_id=external_message_id,
        text=text,
        external_message_id=external_message_id,
        raw_payload={},
    )
    await session.flush()
    ticket = (
        await session.execute(
            select(Ticket).where(Ticket.conversation_id == message.conversation_id)
        )
    ).scalar_one()
    return message, ticket


async def test_hard_trigger_escalates_and_pauses(session, monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")

    message, ticket = await _make_ticket(
        session, "I want to talk to a human please", external_message_id="esc-hard-1"
    )

    final_state = await run_agent(
        session,
        ticket_id=ticket.id,
        conversation_id=message.conversation_id,
        customer_id=message.conversation.customer_id,
        channel="web",
        external_thread_id=message.conversation.external_thread_id,
        message_id=message.id,
        latest_message=message.body,
        owns_session=False,
    )

    # paused at interrupt() - escalate_node's post-interrupt code hasn't run,
    # so outcome is whatever it was before (None), which is itself evidence
    # the run is paused, not finished.
    assert final_state.get("outcome") is None
    assert "__interrupt__" in final_state

    await session.refresh(ticket)
    assert ticket.status == "escalated"

    escalation = (
        await session.execute(select(Escalation).where(Escalation.ticket_id == ticket.id))
    ).scalar_one()
    assert escalation.reason_code == "customer_requested_human"
    assert escalation.status == "queued"
    assert escalation.handoff_packet["ticket_reference"] == ticket.reference
    assert escalation.handoff_packet["summary"]

    ack = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id, Message.direction == "outbound"
            )
        )
    ).scalar_one()
    assert ticket.reference in ack.body


async def test_return_to_ai_resumes_and_completes(session, monkeypatch):
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")

    message, ticket = await _make_ticket(
        session, "I want to talk to a human please", external_message_id="esc-resume-1"
    )

    await run_agent(
        session,
        ticket_id=ticket.id,
        conversation_id=message.conversation_id,
        customer_id=message.conversation.customer_id,
        channel="web",
        external_thread_id=message.conversation.external_thread_id,
        message_id=message.id,
        latest_message=message.body,
        owns_session=False,
    )
    await session.flush()

    escalation = (
        await session.execute(select(Escalation).where(Escalation.ticket_id == ticket.id))
    ).scalar_one()

    # mirrors what the console's /return-to-ai endpoint does before resuming
    ticket.status = "ai_working"
    escalation.status = "returned_to_ai"
    escalation.human_note = "Verified manually, go ahead and reassure the customer."
    await session.flush()

    final_state = await resume_agent(
        session,
        ticket_id=ticket.id,
        resume_payload={"action": "return_to_ai", "note": escalation.human_note},
        owns_session=False,
    )

    assert "__interrupt__" not in final_state
    assert final_state["outcome"] == "answered"
    assert final_state["draft"]

    await session.refresh(ticket)
    assert ticket.status == "ai_working"  # respond_node ran again, ticket already ai_working

    replies = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id, Message.direction == "outbound"
            )
        )
    ).scalars().all()
    assert len(replies) == 2  # the escalation ack, then the post-resume reply
