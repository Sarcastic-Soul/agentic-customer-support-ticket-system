from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    phone: Mapped[str | None] = mapped_column(unique=True)
    tier: Mapped[str] = mapped_column(default="standard")  # standard | plus | priority
    locale: Mapped[str] = mapped_column(default="en-IN")
    verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    identities: Mapped[list["CustomerIdentity"]] = relationship(back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer")


class CustomerIdentity(Base):
    """Maps a channel-specific external id (phone, email, session) to a customer.

    A phone number or email address is not a customer id - this table is the
    resolution step every inbound message goes through first.
    """

    __tablename__ = "customer_identities"
    __table_args__ = (UniqueConstraint("channel", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    channel: Mapped[str]  # web | whatsapp | email | voice
    external_id: Mapped[str]
    verified_at: Mapped[datetime | None]

    customer: Mapped[Customer] = relationship(back_populates="identities")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_channel_thread_status", "channel", "external_thread_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    channel: Mapped[str]
    external_thread_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="open")  # open | idle | closed
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]

    customer: Mapped[Customer] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")
    ticket: Mapped["Ticket | None"] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("channel", "external_message_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str]  # customer | assistant | human_agent | system
    author_agent_id: Mapped[int | None] = mapped_column(ForeignKey("human_agents.id"))
    body: Mapped[str] = mapped_column(Text)
    body_redacted: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str]
    direction: Mapped[str]  # inbound | outbound
    external_message_id: Mapped[str | None]
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
    delivery_status: Mapped[str | None]  # queued | sent | delivered | failed
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class RawEvent(Base):
    """Raw provider payload, persisted before anything else touches the message.

    With a queue in front of the orchestrator, this is what guarantees a crash
    between "webhook received" and "job ran" never loses a customer message.
    """

    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    signature_ok: Mapped[bool | None]
    processed: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status_priority_created", "status", "priority", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(unique=True)  # 'T-1041'
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    channel: Mapped[str]
    subject: Mapped[str | None]
    intent: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="new")
    priority: Mapped[str] = mapped_column(default="P3")  # P1..P4
    sentiment: Mapped[str | None]
    ai_turns: Mapped[int] = mapped_column(default=0)
    resolution: Mapped[str | None]  # ai_resolved | human_resolved | abandoned
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    csat: Mapped[int | None]
    first_response_at: Mapped[datetime | None]
    resolved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    customer: Mapped[Customer] = relationship(back_populates="tickets")
    conversation: Mapped[Conversation | None] = relationship(back_populates="ticket")
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")


class TicketEvent(Base):
    """Append-only audit trail. Every transition, every actor."""

    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    # created|status_changed|assigned|escalated|tool_executed|reply_sent|note_added|resolved
    event_type: Mapped[str]
    actor_type: Mapped[str]  # system | ai | human | customer
    actor_id: Mapped[str | None]
    from_status: Mapped[str | None]
    to_status: Mapped[str | None]
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="events")


__all__ = [
    "Customer",
    "CustomerIdentity",
    "Conversation",
    "Message",
    "RawEvent",
    "Ticket",
    "TicketEvent",
]
