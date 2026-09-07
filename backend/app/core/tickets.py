"""Ticket status transitions, validated in code.

The LLM may request a transition via a tool call; it never writes tickets.status
directly. This module is the single place that decides whether a transition is
legal, so the model cannot invent a status the rest of the system doesn't know
how to handle.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticket, TicketEvent

# new -> ai_working -> ai_resolved -> closed
#                   -> awaiting_customer -> ai_working
#                   -> escalated -> human_working -> human_resolved -> closed
#                                                  -> ai_working  (returned to AI)
# any -> closed (timeout / customer abandon)
# any (closed excepted) -> reopened -> ai_working
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"ai_working", "escalated", "closed"},
    "ai_working": {"ai_resolved", "awaiting_customer", "escalated", "closed"},
    "awaiting_customer": {"ai_working", "escalated", "closed"},
    "ai_resolved": {"closed", "reopened"},
    "escalated": {"human_working", "closed"},
    "human_working": {"human_resolved", "ai_working", "closed"},
    "human_resolved": {"closed", "reopened"},
    "reopened": {"ai_working", "escalated", "closed"},
    "closed": set(),
}


class InvalidTransition(ValueError):
    def __init__(self, from_status: str, to_status: str):
        super().__init__(f"cannot transition ticket from {from_status!r} to {to_status!r}")
        self.from_status = from_status
        self.to_status = to_status


async def transition_ticket(
    session: AsyncSession,
    ticket: Ticket,
    to_status: str,
    *,
    actor_type: str,
    actor_id: str | None = None,
    payload: dict | None = None,
) -> Ticket:
    """Validate and apply a status transition, recording the audit event.

    Raises InvalidTransition rather than silently writing an illegal status.
    Does not commit - caller controls the transaction boundary.
    """
    from_status = ticket.status
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransition(from_status, to_status)

    ticket.status = to_status
    ticket.updated_at = datetime.now(UTC)
    if to_status == "ai_resolved" and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(UTC)
    if to_status == "human_resolved" and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(UTC)

    session.add(
        TicketEvent(
            ticket_id=ticket.id,
            event_type="status_changed",
            actor_type=actor_type,
            actor_id=actor_id,
            from_status=from_status,
            to_status=to_status,
            payload=payload or {},
        )
    )
    return ticket
