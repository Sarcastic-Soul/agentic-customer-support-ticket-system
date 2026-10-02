"""Records one agent_steps row per node execution. This table is what the
"why did the AI do that" screen and half the eval metrics read from - every
node writes one, success or failure.
"""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStep


async def record_step(
    session: AsyncSession,
    *,
    run_id: int,
    node: str,
    agent: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    output: dict | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> AgentStep:
    result = await session.execute(
        select(func.count()).select_from(AgentStep).where(AgentStep.run_id == run_id)
    )
    ordinal = result.scalar_one()

    step = AgentStep(
        run_id=run_id,
        ordinal=ordinal,
        node=node,
        agent=agent,
        model=model,
        prompt=prompt,
        output=output,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(step)
    await session.flush()
    return step


def session_lock(session: AsyncSession) -> asyncio.Lock:
    """One AsyncSession can't run two statements at once, and parallel
    specialists share the run's session. They hold this lock around every
    database call (their LLM calls, the slow part, still overlap). Kept on
    session.info so every node touching the same session finds the same lock.
    """
    return session.info.setdefault("agent_db_lock", asyncio.Lock())
