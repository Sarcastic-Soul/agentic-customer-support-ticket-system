from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.config import settings
from app.policy.triggers import check_hard_triggers


async def hard_route_node(state: AgentState, config: RunnableConfig) -> dict:
    """Deterministic + early judgemental checks, before any tool call is
    spent. Sets escalation_reason_code/priority if a trigger fires;
    route_after_hard_route (the graph's conditional edge) reads it and skips
    straight to escalate, saving the plan/retrieve/act round trip entirely
    for the cases that were never going to be auto-resolved anyway.
    """
    hard = check_hard_triggers(state["latest_message"])
    if hard is not None:
        reason_code, priority = hard
        return {"escalation_reason_code": reason_code, "escalation_priority": priority}

    if state["ai_turns"] >= settings.max_ai_turns:
        return {"escalation_reason_code": "turn_budget_exceeded", "escalation_priority": "P3"}

    if (
        state["intent_confidence"] is not None
        and state["intent_confidence"] < settings.intent_confidence_min
    ):
        return {"escalation_reason_code": "low_intent_confidence", "escalation_priority": "P3"}

    return {}


def route_after_hard_route(state: AgentState) -> str:
    return "escalate" if state.get("escalation_reason_code") else "plan"
