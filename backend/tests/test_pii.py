"""Stage 12 PII check: a card-like or OTP-like string in a customer message
never appears in a recorded prompt. docs/decisions/0003-prototype-scope.md
calls this non-negotiable ("PII redaction with messages.body_redacted...
so what the model saw is on the record") - regex-grade, not ML-grade.
"""

from sqlalchemy import select

from app.core.pii import redact_pii
from app.ingress.pipeline import ingest_message
from app.models import AgentStep, Ticket


def test_redact_pii_masks_card_number():
    text = "please charge my card 4111 1111 1111 1111 for the difference"
    redacted = redact_pii(text)
    assert "4111" not in redacted
    assert "[REDACTED_CARD]" in redacted


def test_redact_pii_masks_card_number_no_spaces():
    redacted = redact_pii("card number is 4111111111111111 thanks")
    assert "4111111111111111" not in redacted
    assert "[REDACTED_CARD]" in redacted


def test_redact_pii_masks_otp_near_keyword():
    redacted = redact_pii("my OTP is 583920, please use it to verify")
    assert "583920" not in redacted
    assert "[REDACTED_CODE]" in redacted


def test_redact_pii_masks_verification_code_phrasing():
    redacted = redact_pii("verification code: 4821 was just sent to me")
    assert "4821" not in redacted
    assert "[REDACTED_CODE]" in redacted


def test_redact_pii_does_not_touch_order_numbers():
    # The exact false-positive this regex must avoid - order numbers are
    # something the agent genuinely needs to read out of the message to
    # call get_order/track_shipment correctly.
    redacted = redact_pii("where is my order ORD-10432, placed last week")
    assert "ORD-10432" in redacted


def test_redact_pii_does_not_touch_bare_amounts():
    redacted = redact_pii("I was charged 4200 for this order, that seems wrong")
    assert "4200" in redacted


def test_redact_pii_passes_through_clean_text():
    text = "hi, when will my refund arrive"
    assert redact_pii(text) == text


def test_redact_pii_handles_empty_and_none():
    assert redact_pii("") == ""
    assert redact_pii(None) is None


async def test_ingest_message_stores_redacted_body(session):
    message = await ingest_message(
        session,
        channel="web",
        external_thread_id="pii-test-session",
        sender_external_id="pii-test-session",
        text="my card is 4111 1111 1111 1111, please refund it there",
        external_message_id="pii-test-1",
        raw_payload={},
    )
    await session.flush()

    assert message.body_redacted is not None
    assert "4111" not in message.body_redacted
    # the raw body is preserved for audit - only the redacted copy is what
    # prompt-building reads
    assert "4111" in message.body


async def test_card_number_never_reaches_a_recorded_prompt(session, monkeypatch):
    """End to end: a customer message containing a card number, run through
    the real graph (stub LLM, so no network call, but the real
    prepare/answer/verify prompt-building code paths), must never surface
    that card number in any agent_steps.prompt row.
    """
    monkeypatch.setattr("app.llm.registry.settings.llm_provider", "stub")

    from app.agent.run import run_agent

    message = await ingest_message(
        session,
        channel="web",
        external_thread_id="pii-test-session-2",
        sender_external_id="pii-test-session-2",
        text="hi, my card number is 4111 1111 1111 1111, can you check my order status",
        external_message_id="pii-test-2",
        raw_payload={},
    )
    await session.flush()

    ticket = (
        await session.execute(
            select(Ticket).where(Ticket.conversation_id == message.conversation_id)
        )
    ).scalar_one()
    await run_agent(
        session,
        ticket_id=ticket.id,
        conversation_id=message.conversation_id,
        customer_id=message.conversation.customer_id,
        channel="web",
        external_thread_id=message.conversation.external_thread_id,
        message_id=message.id,
        latest_message=message.body_redacted or message.body,
        owns_session=False,
    )
    await session.flush()

    steps = (
        await session.execute(
            select(AgentStep).where(AgentStep.prompt.is_not(None))
        )
    ).scalars().all()
    assert steps, "expected at least one recorded prompt"
    for step in steps:
        assert "4111 1111 1111 1111" not in step.prompt
        assert "4111111111111111" not in step.prompt

    # and the second, follow-up turn's history (built from the first
    # message) must also come through redacted, not just the first turn's
    # own latest_message
    follow_up = await ingest_message(
        session,
        channel="web",
        external_thread_id="pii-test-session-2",
        sender_external_id="pii-test-session-2",
        text="did you get that",
        external_message_id="pii-test-2b",
        raw_payload={},
    )
    await session.flush()
    await run_agent(
        session,
        ticket_id=ticket.id,
        conversation_id=follow_up.conversation_id,
        customer_id=follow_up.conversation.customer_id,
        channel="web",
        external_thread_id=follow_up.conversation.external_thread_id,
        message_id=follow_up.id,
        latest_message=follow_up.body_redacted or follow_up.body,
        owns_session=False,
    )
    await session.flush()

    steps = (
        await session.execute(
            select(AgentStep).where(AgentStep.prompt.is_not(None))
        )
    ).scalars().all()
    for step in steps:
        assert "4111 1111 1111 1111" not in step.prompt
