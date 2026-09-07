from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.llm.registry import get_llm
from app.llm.roles import LLMRole

INTENTS = [
    "order_status", "order_cancel", "order_return", "order_modify",
    "delivery_issue", "damaged_or_missing_item",
    "refund_status", "refund_request", "payment_failed", "invoice_request", "billing_dispute",
    "product_question", "policy_question", "account_issue",
    "complaint", "feedback", "chitchat", "spam", "unknown",
]


class Classification(BaseModel):
    intent: str
    confidence: float
    requires_account_access: bool


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    return "\n".join(f"{m['role']}: {m['body']}" for m in history)


async def classify_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]

    prompt = load_prompt(
        "classify",
        history=_format_history(state["history"]),
        message=state["latest_message"],
    )

    client = get_llm(LLMRole.classify)
    outcome = await client.ainvoke(prompt, structured=Classification)
    result = outcome.structured

    intent = result.intent if result and result.intent in INTENTS else "unknown"
    confidence = result.confidence if result else 0.0

    await record_step(
        session,
        run_id=state["run_id"],
        node="classify",
        model=f"{outcome.provider}:{outcome.model}",
        prompt=prompt,
        output={"intent": intent, "confidence": confidence} if result else None,
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
        latency_ms=outcome.latency_ms,
    )

    return {"intent": intent, "intent_confidence": confidence}
