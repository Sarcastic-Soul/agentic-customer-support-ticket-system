"""The human agent console API. Stage 6 delivered the escalation mechanics
without auth (noted loudly there, not quietly); Stage 9 adds it - every
route below requires a valid human_agents JWT (see app/core/auth.py).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.run import resume_agent
from app.channels.base import Channel, OutboundMessage
from app.channels.registry import get_adapter
from app.core.auth import get_current_agent
from app.core.tickets import transition_ticket
from app.db.session import get_session
from app.models import Conversation, Escalation, Message, Ticket

router = APIRouter(
    prefix="/api/console", tags=["console"], dependencies=[Depends(get_current_agent)]
)


class EscalationSummary(BaseModel):
    id: int
    ticket_id: int
    ticket_reference: str
    reason_code: str
    priority: str
    status: str
    required_skill: str | None
    created_at: datetime


class EscalationDetail(EscalationSummary):
    handoff_packet: dict
    claimed_by: int | None
    human_note: str | None


class TranscriptMessage(BaseModel):
    id: int
    role: str
    body: str
    direction: str
    created_at: datetime


class ClaimResponse(BaseModel):
    claimed: bool
    escalation: EscalationDetail | None = None


class ReplyRequest(BaseModel):
    text: str
    agent_name: str = "agent"  # stand-in for auth (Stage 9); who sent this reply


class ReturnToAIRequest(BaseModel):
    note: str


class ResolveRequest(BaseModel):
    summary: str


PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


async def _load_ticket(session: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "ticket not found")
    return ticket


@router.get("/queue", response_model=list[EscalationSummary])
async def get_queue(
    skill: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[EscalationSummary]:
    query = (
        select(Escalation, Ticket.reference)
        .join(Ticket, Ticket.id == Escalation.ticket_id)
        .where(Escalation.status == "queued")
    )
    if skill:
        query = query.where(Escalation.required_skill == skill)
    rows = (await session.execute(query)).all()

    rows.sort(key=lambda r: (PRIORITY_ORDER.get(r[0].priority, 9), r[0].created_at))
    return [
        EscalationSummary(
            id=e.id, ticket_id=e.ticket_id, ticket_reference=ref,
            reason_code=e.reason_code, priority=e.priority, status=e.status,
            required_skill=e.required_skill, created_at=e.created_at,
        )
        for e, ref in rows
    ]


@router.get("/escalations/{escalation_id}", response_model=EscalationDetail)
async def get_escalation(
    escalation_id: int, session: AsyncSession = Depends(get_session)
) -> EscalationDetail:
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(404, "escalation not found")
    ticket = await _load_ticket(session, escalation.ticket_id)
    return EscalationDetail(
        id=escalation.id, ticket_id=escalation.ticket_id, ticket_reference=ticket.reference,
        reason_code=escalation.reason_code, priority=escalation.priority, status=escalation.status,
        required_skill=escalation.required_skill, created_at=escalation.created_at,
        handoff_packet=escalation.handoff_packet, claimed_by=escalation.claimed_by,
        human_note=escalation.human_note,
    )


@router.get("/escalations/{escalation_id}/transcript", response_model=list[TranscriptMessage])
async def get_transcript(
    escalation_id: int, session: AsyncSession = Depends(get_session)
) -> list[TranscriptMessage]:
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(404, "escalation not found")
    ticket = await _load_ticket(session, escalation.ticket_id)

    messages = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    return [
        TranscriptMessage(
            id=m.id, role=m.role, body=m.body, direction=m.direction, created_at=m.created_at
        )
        for m in messages
    ]


@router.post("/escalations/{escalation_id}/claim", response_model=ClaimResponse)
async def claim_escalation(
    escalation_id: int, session: AsyncSession = Depends(get_session)
) -> ClaimResponse:
    """Atomic claim: FOR UPDATE SKIP LOCKED so two agents can never grab the
    same ticket, then a plain status check to reject an already-claimed one.
    """
    locked = (
        await session.execute(
            select(Escalation)
            .where(Escalation.id == escalation_id, Escalation.status == "queued")
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if locked is None:
        return ClaimResponse(claimed=False)

    locked.status = "claimed"
    locked.claimed_at = datetime.now(UTC)

    ticket = await _load_ticket(session, locked.ticket_id)
    await transition_ticket(session, ticket, "human_working", actor_type="human")
    await session.commit()

    return ClaimResponse(
        claimed=True,
        escalation=EscalationDetail(
            id=locked.id, ticket_id=locked.ticket_id, ticket_reference=ticket.reference,
            reason_code=locked.reason_code, priority=locked.priority, status=locked.status,
            required_skill=locked.required_skill, created_at=locked.created_at,
            handoff_packet=locked.handoff_packet, claimed_by=locked.claimed_by,
            human_note=locked.human_note,
        ),
    )


@router.post("/escalations/{escalation_id}/reply")
async def send_reply(
    escalation_id: int, body: ReplyRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Human reply, sent through the same channel adapter the customer used
    - the customer sees one continuous thread, not "AI" then "human" as
    different actors on different channels.
    """
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(404, "escalation not found")
    ticket = await _load_ticket(session, escalation.ticket_id)
    conversation = await session.get(Conversation, ticket.conversation_id)

    reply = Message(
        conversation_id=ticket.conversation_id, role="human_agent", body=body.text,
        channel=ticket.channel, direction="outbound",
    )
    session.add(reply)
    await session.flush()

    adapter = get_adapter(Channel(ticket.channel))
    receipt = await adapter.send(
        OutboundMessage(
            channel=adapter.channel, external_thread_id=conversation.external_thread_id,
            text=body.text,
        )
    )
    reply.delivery_status = "sent" if receipt.ok else "failed"
    if receipt.ok and receipt.detail:
        reply.external_message_id = receipt.detail
    await session.commit()
    return {"sent": True, "delivered": receipt.ok}


@router.post("/escalations/{escalation_id}/return-to-ai")
async def return_to_ai(
    escalation_id: int, body: ReturnToAIRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Resumes the paused graph with the human's note - the AI continues
    from its checkpoint, not from scratch (see app/agent/run.resume_agent).
    """
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(404, "escalation not found")
    if escalation.status not in ("claimed", "queued"):
        raise HTTPException(409, f"escalation is already {escalation.status}")

    escalation.status = "returned_to_ai"
    escalation.human_note = body.note
    ticket = await _load_ticket(session, escalation.ticket_id)
    await transition_ticket(session, ticket, "ai_working", actor_type="human")
    await session.flush()

    final_state = await resume_agent(
        session, ticket_id=ticket.id,
        resume_payload={"action": "return_to_ai", "note": body.note},
    )
    return {"resumed": True, "outcome": final_state.get("outcome")}


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: int, body: ResolveRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Marks the escalation (and ticket) resolved. Does not resume the
    paused graph - there is nothing more for the AI to do, and an
    interrupted LangGraph thread left unresumed is inert, not a leak (see
    docs/PROGRESS.md Stage 6 for the trade-off this implies for agent_runs).
    """
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(404, "escalation not found")

    escalation.status = "resolved"
    escalation.resolved_at = datetime.now(UTC)

    ticket = await _load_ticket(session, escalation.ticket_id)
    await transition_ticket(
        session, ticket, "closed", actor_type="human", payload={"summary": body.summary}
    )
    ticket.resolution = "human_resolved"
    ticket.resolution_summary = body.summary
    ticket.resolved_at = datetime.now(UTC)

    await session.commit()
    return {"resolved": True}


@router.get("/stats")
async def queue_stats(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(Escalation.priority, Escalation.reason_code).where(Escalation.status == "queued")
        )
    ).all()
    return {
        "queued": len(rows),
        "by_priority": {p: sum(1 for row in rows if row[0] == p) for p in PRIORITY_ORDER},
    }
