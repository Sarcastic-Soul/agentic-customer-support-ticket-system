from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.agent.state import AgentState
from app.models import Message, Ticket

HISTORY_LIMIT = 10


async def prepare_node(state: AgentState, config: RunnableConfig) -> dict:
    """Loads recent conversation history and the ticket's current ai_turns
    count. Identity (ticket_id, customer_id, conversation_id) is already set
    by the caller before the graph runs - this node never touches it, only
    reads context.
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

    # body_redacted is only ever set on customer messages (see
    # app/ingress/pipeline.py) - assistant messages fall back to body since
    # there's nothing to redact from the AI's own output.
    history = [
        {"role": m.role, "body": m.body_redacted or m.body}
        for m in prior
        if m.role in ("customer", "assistant")
    ]

    ticket = await session.get(Ticket, state["ticket_id"])
    ai_turns = ticket.ai_turns if ticket is not None else 0

    return {"history": history, "ai_turns": ai_turns}
