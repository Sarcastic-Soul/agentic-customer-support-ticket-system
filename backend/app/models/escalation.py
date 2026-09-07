from datetime import datetime

from sqlalchemy import ARRAY, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class HumanAgent(Base):
    __tablename__ = "human_agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(default="agent")  # agent | supervisor | admin
    # e.g. {'refunds','orders','billing'} - filters the queue view, no routing algorithm
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_available: Mapped[bool] = mapped_column(default=True)


class Escalation(Base):
    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_status_priority_created", "status", "priority", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    reason_code: Mapped[str]
    reason_detail: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str]
    # summary, timeline, entities, attempts, draft
    handoff_packet: Mapped[dict] = mapped_column(JSONB)
    required_skill: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="queued")  # queued|claimed|resolved|returned_to_ai
    claimed_by: Mapped[int | None] = mapped_column(ForeignKey("human_agents.id"))
    claimed_at: Mapped[datetime | None]
    resolved_at: Mapped[datetime | None]
    human_note: Mapped[str | None] = mapped_column(Text)  # fed back into agent state on resume
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


__all__ = ["HumanAgent", "Escalation"]
