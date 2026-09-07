from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class AgentRun(Base):
    """One row per inbound message. The highest-value-per-line table in the
    codebase - powers the "why did the AI do that" screen and half the eval
    metrics, via its child agent_steps / tool_calls.
    """

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    thread_id: Mapped[str]  # LangGraph checkpoint thread id
    trigger: Mapped[str]  # inbound_message | resume | retry
    outcome: Mapped[str | None]  # answered | escalated | failed | no_op
    intent: Mapped[str | None]
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    total_tokens_in: Mapped[int] = mapped_column(default=0)
    total_tokens_out: Mapped[int] = mapped_column(default=0)
    est_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]

    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    node: Mapped[str]  # classify | retrieve | act | verify | ...
    model: Mapped[str | None]
    prompt: Mapped[str | None] = mapped_column(Text)  # redacted
    output: Mapped[dict | None] = mapped_column(JSONB)
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    run: Mapped[AgentRun] = relationship(back_populates="steps")
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="step")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("agent_steps.id", ondelete="CASCADE"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    tool_name: Mapped[str]
    arguments: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    authorized: Mapped[bool]
    deny_reason: Mapped[str | None]
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    step: Mapped[AgentStep | None] = relationship(back_populates="tool_calls")


__all__ = ["AgentRun", "AgentStep", "ToolCall"]
