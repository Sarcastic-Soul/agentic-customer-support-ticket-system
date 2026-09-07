import pytest

from app.core.tickets import ALLOWED_TRANSITIONS, InvalidTransition, transition_ticket
from app.models import Customer, Ticket

ALL_STATUSES = set(ALLOWED_TRANSITIONS.keys())


async def _make_ticket(session, status: str) -> Ticket:
    customer = Customer(full_name="Test Customer", email=f"{status}@example.com")
    session.add(customer)
    await session.flush()

    ticket = Ticket(
        reference=f"T-TEST-{status}",
        customer_id=customer.id,
        channel="web",
        status=status,
    )
    session.add(ticket)
    await session.flush()
    return ticket


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [(f, t) for f, allowed in ALLOWED_TRANSITIONS.items() for t in allowed],
)
async def test_legal_transition_succeeds(session, from_status, to_status):
    ticket = await _make_ticket(session, from_status)

    await transition_ticket(session, ticket, to_status, actor_type="system")

    assert ticket.status == to_status


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (f, t)
        for f, allowed in ALLOWED_TRANSITIONS.items()
        for t in ALL_STATUSES - allowed - {f}
    ],
)
async def test_illegal_transition_raises(session, from_status, to_status):
    ticket = await _make_ticket(session, from_status)

    with pytest.raises(InvalidTransition):
        await transition_ticket(session, ticket, to_status, actor_type="system")

    # status must be unchanged after a rejected transition
    assert ticket.status == from_status


async def test_transition_records_ticket_event(session):
    ticket = await _make_ticket(session, "new")

    await transition_ticket(
        session, ticket, "ai_working", actor_type="ai", payload={"intent": "order_status"}
    )
    await session.flush()

    await session.refresh(ticket, attribute_names=["events"])
    events = ticket.events
    assert len(events) == 1
    assert events[0].from_status == "new"
    assert events[0].to_status == "ai_working"
    assert events[0].actor_type == "ai"
    assert events[0].payload == {"intent": "order_status"}


async def test_closed_is_terminal(session):
    ticket = await _make_ticket(session, "closed")

    assert ALLOWED_TRANSITIONS["closed"] == set()
    with pytest.raises(InvalidTransition):
        await transition_ticket(session, ticket, "ai_working", actor_type="system")
