"""Stage 12 failure drills: each must produce an honest customer-facing
message, never silence. "No LLM key"/"every provider down" is exercised
here at the handle_message level (test_llm_registry.py already covers the
registry's own fallback-then-raise behaviour - this tests what happens to
the *customer* once that exception reaches the worker). "Tool raises" is
already handled by app/tools/registry.py's execute_tool - this is a
regression test for that existing behaviour, not a new fix. "No Redis" and
"no tunnel" are infra-level (see docs/PROGRESS.md Stage 12) and were
verified manually rather than in pytest - see the notes there.
"""

from sqlalchemy import select

from app.ingress.pipeline import ingest_message
from app.llm.registry import AllProvidersFailedError
from app.models import Customer, Escalation, Message, Ticket, ToolCall
from app.tools.context import ToolContext
from app.tools.registry import execute_tool, get_tool_spec
from app.workers.tasks import handle_message


async def _make_ticket(session, text: str, *, external_message_id: str, channel: str = "web"):
    message = await ingest_message(
        session,
        channel=channel,
        external_thread_id=external_message_id,
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


async def test_every_provider_down_still_answers_the_customer(session, monkeypatch):
    async def _boom(*args, **kwargs):
        raise AllProvidersFailedError("reason", [RuntimeError("no key configured")])

    monkeypatch.setattr("app.workers.tasks.run_agent", _boom)

    message, ticket = await _make_ticket(
        session, "where is my order", external_message_id="drill-no-llm-1"
    )

    await handle_message({}, message.id, session=session)
    await session.flush()

    await session.refresh(ticket)
    assert ticket.status == "escalated"

    reply = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id,
                Message.direction == "outbound",
            )
        )
    ).scalar_one()
    assert reply.role == "assistant"
    assert reply.body  # not silence
    assert ticket.reference in reply.body

    escalation = (
        await session.execute(
            select(Escalation).where(Escalation.ticket_id == ticket.id)
        )
    ).scalar_one()
    assert escalation.reason_code == "system_error"
    assert escalation.status == "queued"


async def test_repeated_failure_does_not_duplicate_escalation_or_message(session, monkeypatch):
    """arq may retry a failed job - a second identical failure on the same
    ticket must not page a human twice or apologize to the customer twice.
    """
    async def _boom(*args, **kwargs):
        raise RuntimeError("still broken")

    monkeypatch.setattr("app.workers.tasks.run_agent", _boom)

    message, ticket = await _make_ticket(
        session, "where is my order", external_message_id="drill-no-llm-2"
    )

    await handle_message({}, message.id, session=session)
    await session.flush()
    await handle_message({}, message.id, session=session)
    await session.flush()

    escalations = (
        await session.execute(
            select(Escalation).where(Escalation.ticket_id == ticket.id)
        )
    ).scalars().all()
    assert len(escalations) == 1

    replies = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == message.conversation_id,
                Message.direction == "outbound",
            )
        )
    ).scalars().all()
    assert len(replies) == 1


async def test_tool_raising_returns_a_structured_error_not_a_crash(session, monkeypatch):
    """Regression coverage for existing behaviour: execute_tool already
    catches any tool exception and turns it into a structured error result
    fed back to the model (app/tools/registry.py), rather than propagating
    it and crashing the graph mid-turn. Exercised directly against
    execute_tool rather than through the stub graph - StubChatModel's
    bind_tools() never actually issues a tool call (see app/llm/stub.py),
    so this specific claim isn't reachable end to end without spending real
    LLM quota on tool selection, which isn't the point of this drill.
    """
    customer = Customer(full_name="Drill Customer", email="drill@example.com")
    session.add(customer)
    await session.flush()
    ticket = Ticket(reference=f"T-DRILL-{customer.id}", customer_id=customer.id, channel="web")
    session.add(ticket)
    await session.flush()
    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=ticket.id, run_id=1)

    spec = get_tool_spec("get_order")

    async def _boom(ctx, **kwargs):
        raise RuntimeError("simulated tool crash")

    monkeypatch.setattr(spec, "func", _boom)

    result = await execute_tool(spec, ctx, {"order_number": "ORD-10000"})

    assert result["error"] == "tool_execution_failed"
    assert "simulated tool crash" in result["hint"]

    call = (
        await session.execute(select(ToolCall).where(ToolCall.ticket_id == ticket.id))
    ).scalar_one()
    assert call.error is not None
    assert call.tool_name == "get_order"
