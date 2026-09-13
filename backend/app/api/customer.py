"""Customer-facing chat login: email only, no password (prototype scope,
`docs/decisions/0003-prototype-scope.md`). Resolves/creates the same
(channel="web", external_id=email) identity the web WS and
`/dev/simulate/web` already use via `resolve_customer`, so the email a
customer logs in with and the chat session it starts share one customer
and one conversation thread.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import resolve_customer
from app.db.session import get_session
from app.models import Conversation, Customer, Message, Ticket

router = APIRouter(prefix="/api/customer", tags=["customer"])


class LoginRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("not a valid email")
        return value


class LoginResponse(BaseModel):
    customer_id: int
    email: str
    created: bool


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_session)
) -> LoginResponse:
    customer, created = await resolve_customer(session, channel="web", external_id=body.email)
    await session.commit()
    return LoginResponse(customer_id=customer.id, email=body.email, created=created)


class CustomerTicketSummary(BaseModel):
    id: int
    reference: str
    channel: str
    intent: str | None
    status: str
    created_at: datetime
    resolved_at: datetime | None


@router.get("/tickets", response_model=list[CustomerTicketSummary])
async def list_my_tickets(
    customer_id: int, session: AsyncSession = Depends(get_session)
) -> list[CustomerTicketSummary]:
    """Self-service ticket history for the browser's own logged-in customer.

    `customer_id` here comes straight from this browser's own /login
    response, not from a privileged source - there is no password, so this
    is not a security boundary against someone who already knows (or
    guesses) another customer's id, same tolerance as the rest of this
    prototype's password-less customer channels.
    """
    if await session.get(Customer, customer_id) is None:
        raise HTTPException(404, "customer not found")

    rows = (
        await session.execute(
            select(Ticket)
            .where(Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc())
        )
    ).scalars().all()
    return [
        CustomerTicketSummary(
            id=t.id, reference=t.reference, channel=t.channel, intent=t.intent,
            status=t.status, created_at=t.created_at, resolved_at=t.resolved_at,
        )
        for t in rows
    ]


class CustomerMessage(BaseModel):
    id: int
    role: str
    text: str
    created_at: datetime


@router.get("/messages", response_model=list[CustomerMessage])
async def get_current_messages(
    customer_id: int, session: AsyncSession = Depends(get_session)
) -> list[CustomerMessage]:
    """History of this customer's current (not-closed) web conversation, so
    the chat widget can restore it after a page refresh or reconnect instead
    of starting blank - the WS itself only forwards new replies going
    forward (app/ingress/web.py), it never replays history.
    """
    if await session.get(Customer, customer_id) is None:
        raise HTTPException(404, "customer not found")

    conversation = (
        await session.execute(
            select(Conversation)
            .where(
                Conversation.customer_id == customer_id,
                Conversation.channel == "web",
                Conversation.status != "closed",
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conversation is None:
        return []

    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    return [
        CustomerMessage(id=m.id, role=m.role, text=m.body, created_at=m.created_at)
        for m in rows
        if m.role in ("customer", "assistant", "human_agent")
    ]
