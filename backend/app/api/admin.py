"""Admin dashboard API: ticket list/detail with the full reasoning trace,
aggregate metrics, and KB management. Every route requires a valid
human_agents JWT (app/core/auth.py); KB writes additionally require the
admin role.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_agent, require_admin
from app.db.session import get_session
from app.models import (
    AgentRun,
    AgentStep,
    Escalation,
    HumanAgent,
    KBDocument,
    Message,
    Ticket,
    TicketEvent,
    ToolCall,
)
from app.rag.ingest import ingest_document

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_agent)]
)


# ---------- tickets ----------


class TicketSummary(BaseModel):
    id: int
    reference: str
    channel: str
    intent: str | None
    status: str
    priority: str
    sentiment: str | None
    created_at: datetime
    resolved_at: datetime | None


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    total: int


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    status_: str | None = Query(None, alias="status"),
    channel: str | None = None,
    intent: str | None = None,
    priority: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> TicketListResponse:
    query = select(Ticket)
    if status_:
        query = query.where(Ticket.status == status_)
    if channel:
        query = query.where(Ticket.channel == channel)
    if intent:
        query = query.where(Ticket.intent == intent)
    if priority:
        query = query.where(Ticket.priority == priority)

    total = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return TicketListResponse(
        items=[
            TicketSummary(
                id=t.id, reference=t.reference, channel=t.channel, intent=t.intent,
                status=t.status, priority=t.priority, sentiment=t.sentiment,
                created_at=t.created_at, resolved_at=t.resolved_at,
            )
            for t in rows
        ],
        total=total,
    )


class TicketMessage(BaseModel):
    id: int
    role: str
    body: str
    direction: str
    delivery_status: str | None
    created_at: datetime


class TicketEventOut(BaseModel):
    event_type: str
    actor_type: str
    from_status: str | None
    to_status: str | None
    created_at: datetime


class TicketDetail(TicketSummary):
    ai_turns: int
    resolution: str | None
    resolution_summary: str | None
    first_response_at: datetime | None
    messages: list[TicketMessage]
    events: list[TicketEventOut]


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(ticket_id: int, session: AsyncSession = Depends(get_session)) -> TicketDetail:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "ticket not found")

    messages = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    events = (
        await session.execute(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.created_at)
        )
    ).scalars().all()

    return TicketDetail(
        id=ticket.id, reference=ticket.reference, channel=ticket.channel, intent=ticket.intent,
        status=ticket.status, priority=ticket.priority, sentiment=ticket.sentiment,
        created_at=ticket.created_at, resolved_at=ticket.resolved_at,
        ai_turns=ticket.ai_turns, resolution=ticket.resolution,
        resolution_summary=ticket.resolution_summary, first_response_at=ticket.first_response_at,
        messages=[
            TicketMessage(
                id=m.id, role=m.role, body=m.body, direction=m.direction,
                delivery_status=m.delivery_status, created_at=m.created_at,
            )
            for m in messages
        ],
        events=[
            TicketEventOut(
                event_type=e.event_type, actor_type=e.actor_type,
                from_status=e.from_status, to_status=e.to_status, created_at=e.created_at,
            )
            for e in events
        ],
    )


class ToolCallOut(BaseModel):
    tool_name: str
    arguments: dict
    result: dict | None
    authorized: bool
    deny_reason: str | None
    latency_ms: int | None


class AgentStepOut(BaseModel):
    ordinal: int
    node: str
    model: str | None
    output: dict | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    error: str | None
    tool_calls: list[ToolCallOut]


class AgentRunOut(BaseModel):
    id: int
    trigger: str
    outcome: str | None
    intent: str | None
    confidence: float | None
    total_tokens_in: int
    total_tokens_out: int
    est_cost_usd: Decimal
    latency_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[AgentStepOut]


@router.get("/tickets/{ticket_id}/runs", response_model=list[AgentRunOut])
async def get_ticket_runs(
    ticket_id: int, session: AsyncSession = Depends(get_session)
) -> list[AgentRunOut]:
    """The "why did the AI do that" view - every node, prompt outcome, tool
    call and token count for every run against this ticket.
    """
    runs = (
        await session.execute(
            select(AgentRun).where(AgentRun.ticket_id == ticket_id).order_by(AgentRun.started_at)
        )
    ).scalars().all()

    out: list[AgentRunOut] = []
    for run in runs:
        steps = (
            await session.execute(
                select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.ordinal)
            )
        ).scalars().all()
        step_outs = []
        for step in steps:
            tool_calls = (
                await session.execute(select(ToolCall).where(ToolCall.step_id == step.id))
            ).scalars().all()
            step_outs.append(
                AgentStepOut(
                    ordinal=step.ordinal, node=step.node, model=step.model, output=step.output,
                    tokens_in=step.tokens_in, tokens_out=step.tokens_out,
                    latency_ms=step.latency_ms, error=step.error,
                    tool_calls=[
                        ToolCallOut(
                            tool_name=tc.tool_name, arguments=tc.arguments, result=tc.result,
                            authorized=tc.authorized, deny_reason=tc.deny_reason,
                            latency_ms=tc.latency_ms,
                        )
                        for tc in tool_calls
                    ],
                )
            )
        out.append(
            AgentRunOut(
                id=run.id, trigger=run.trigger, outcome=run.outcome, intent=run.intent,
                confidence=float(run.confidence) if run.confidence is not None else None,
                total_tokens_in=run.total_tokens_in, total_tokens_out=run.total_tokens_out,
                est_cost_usd=run.est_cost_usd, latency_ms=run.latency_ms,
                started_at=run.started_at, finished_at=run.finished_at, steps=step_outs,
            )
        )
    return out


# ---------- metrics ----------

_CLOSED_STATUSES = ("closed",)
_ESCALATED_STATUSES = ("escalated", "human_working")


def _was_escalated(ticket: Ticket) -> bool:
    return ticket.status in _ESCALATED_STATUSES or ticket.resolution == "human_resolved"


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


async def _tickets_since(session: AsyncSession, since: datetime, *, require_intent: bool = False):
    query = select(Ticket).where(Ticket.created_at >= since)
    if require_intent:
        query = query.where(Ticket.intent.is_not(None))
    return (await session.execute(query)).scalars().all()


@router.get("/metrics/overview")
async def metrics_overview(
    range_days: int = Query(7, alias="range"), session: AsyncSession = Depends(get_session)
) -> dict:
    since = datetime.now(UTC) - timedelta(days=range_days)
    tickets = await _tickets_since(session, since)

    total = len(tickets)
    open_count = sum(1 for t in tickets if t.status not in _CLOSED_STATUSES)
    ai_resolved = sum(1 for t in tickets if t.resolution == "ai_resolved")
    human_resolved = sum(1 for t in tickets if t.resolution == "human_resolved")
    resolved_total = ai_resolved + human_resolved
    escalated = sum(1 for t in tickets if _was_escalated(t))

    response_times = [
        (t.first_response_at - t.created_at).total_seconds()
        for t in tickets
        if t.first_response_at is not None
    ]
    resolution_times = [
        (t.resolved_at - t.created_at).total_seconds() for t in tickets if t.resolved_at is not None
    ]

    total_cost = (
        await session.execute(
            select(func.sum(AgentRun.est_cost_usd))
            .join(Ticket, Ticket.id == AgentRun.ticket_id)
            .where(Ticket.created_at >= since)
        )
    ).scalar_one()

    return {
        "total_tickets": total,
        "open_tickets": open_count,
        "closed_tickets": total - open_count,
        "ai_resolution_rate": round(ai_resolved / resolved_total, 3) if resolved_total else None,
        "escalation_rate": round(escalated / total, 3) if total else None,
        "avg_first_response_seconds": _avg(response_times),
        "avg_resolution_seconds": _avg(resolution_times),
        "total_est_cost_usd": float(total_cost or 0),
    }


@router.get("/metrics/channels")
async def metrics_channels(
    range_days: int = Query(7, alias="range"), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=range_days)
    tickets = await _tickets_since(session, since)

    by_channel: dict[str, list[Ticket]] = {}
    for t in tickets:
        by_channel.setdefault(t.channel, []).append(t)

    return [
        {
            "channel": channel,
            "count": len(rows),
            "ai_resolved": sum(1 for t in rows if t.resolution == "ai_resolved"),
            "escalated": sum(1 for t in rows if _was_escalated(t)),
        }
        for channel, rows in sorted(by_channel.items())
    ]


@router.get("/metrics/intents")
async def metrics_intents(
    range_days: int = Query(7, alias="range"), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=range_days)
    tickets = await _tickets_since(session, since, require_intent=True)

    by_intent: dict[str, list[Ticket]] = {}
    for t in tickets:
        by_intent.setdefault(t.intent, []).append(t)

    return [
        {
            "intent": intent,
            "count": len(rows),
            "escalation_rate": round(sum(1 for t in rows if _was_escalated(t)) / len(rows), 3),
        }
        for intent, rows in sorted(by_intent.items(), key=lambda kv: -len(kv[1]))
    ]


@router.get("/metrics/escalations")
async def metrics_escalations(
    range_days: int = Query(7, alias="range"), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=range_days)
    escalations = (
        await session.execute(select(Escalation).where(Escalation.created_at >= since))
    ).scalars().all()

    by_reason: dict[str, int] = {}
    for e in escalations:
        by_reason[e.reason_code] = by_reason.get(e.reason_code, 0) + 1

    return [
        {"reason_code": k, "count": v}
        for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1])
    ]


# ---------- knowledge base ----------


class KBDocumentSummary(BaseModel):
    id: int
    title: str
    category: str | None
    source: str
    version: int
    is_active: bool
    updated_at: datetime


class KBDocumentDetail(KBDocumentSummary):
    body: str


class KBDocumentCreate(BaseModel):
    title: str
    body: str
    source: str = "manual"
    category: str | None = None


class KBDocumentUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    is_active: bool | None = None


@router.get("/kb/documents", response_model=list[KBDocumentSummary])
async def list_kb_documents(
    session: AsyncSession = Depends(get_session),
) -> list[KBDocumentSummary]:
    docs = (await session.execute(select(KBDocument).order_by(KBDocument.title))).scalars().all()
    return [
        KBDocumentSummary(
            id=d.id, title=d.title, category=d.category, source=d.source,
            version=d.version, is_active=d.is_active, updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/kb/documents/{doc_id}", response_model=KBDocumentDetail)
async def get_kb_document(
    doc_id: int, session: AsyncSession = Depends(get_session)
) -> KBDocumentDetail:
    doc = await session.get(KBDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return KBDocumentDetail(
        id=doc.id, title=doc.title, category=doc.category, source=doc.source,
        version=doc.version, is_active=doc.is_active, updated_at=doc.updated_at, body=doc.body,
    )


@router.post("/kb/documents", response_model=KBDocumentDetail)
async def create_kb_document(
    body: KBDocumentCreate,
    agent: HumanAgent = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> KBDocumentDetail:
    doc = KBDocument(
        title=body.title, body=body.body, source=body.source, category=body.category,
        updated_by=agent.id,
    )
    session.add(doc)
    await session.flush()
    await ingest_document(session, doc)
    await session.commit()
    await session.refresh(doc)
    return KBDocumentDetail(
        id=doc.id, title=doc.title, category=doc.category, source=doc.source,
        version=doc.version, is_active=doc.is_active, updated_at=doc.updated_at, body=doc.body,
    )


@router.put("/kb/documents/{doc_id}", response_model=KBDocumentDetail)
async def update_kb_document(
    doc_id: int,
    body: KBDocumentUpdate,
    agent: HumanAgent = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> KBDocumentDetail:
    """Bumps version and re-embeds (app.rag.ingest.ingest_document deletes
    and rebuilds this document's kb_chunks) whenever the body actually
    changes - editing a KB article and having the agent's retrieval reflect
    it immediately is the whole point of this endpoint.
    """
    doc = await session.get(KBDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")

    body_changed = body.body is not None and body.body != doc.body
    if body.title is not None:
        doc.title = body.title
    if body.body is not None:
        doc.body = body.body
    if body.category is not None:
        doc.category = body.category
    if body.is_active is not None:
        doc.is_active = body.is_active
    doc.updated_by = agent.id

    if body_changed:
        doc.version += 1
        await ingest_document(session, doc)

    await session.commit()
    await session.refresh(doc)
    return KBDocumentDetail(
        id=doc.id, title=doc.title, category=doc.category, source=doc.source,
        version=doc.version, is_active=doc.is_active, updated_at=doc.updated_at, body=doc.body,
    )
