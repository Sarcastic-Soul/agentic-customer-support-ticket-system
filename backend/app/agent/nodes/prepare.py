from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.agent.state import AgentState
from app.models import Message

HISTORY_LIMIT = 10


async def prepare_node(state: AgentState, config: RunnableConfig) -> dict:
    """Loads recent conversation history. Identity (ticket_id, customer_id,
    conversation_id) is already set by the caller before the graph runs -
    this node never touches it, only reads context.
    """
    session = config["configurable"]["session"]

    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == state["conversation_id"])
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT + 1)
    )
    messages = list(reversed(result.scalars().all()))
    # the most recent message is the one triggering this run (already in
    # `latest_message`) - exclude it from history so it isn't duplicated.
    prior = messages[:-1] if messages else []

    history = [
        {"role": m.role, "body": m.body}
        for m in prior
        if m.role in ("customer", "assistant")
    ]
    return {"history": history}
