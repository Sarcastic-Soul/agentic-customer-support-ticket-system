"""Picks which specialists work this message. Deterministic - a table
lookup on classify's intents, no LLM call - so which agent owns a request
is always explainable and never a judgement call a model can get wrong.
"""

from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from app.agent.specialists import GENERALIST, KNOWLEDGE_INTENTS, pick_specialists, tool_budget
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.config import settings


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]

    specialists = pick_specialists(state["intent"], state.get("secondary_intent"))
    if specialists and settings.eval_ablation == "single_agent":
        specialists = [GENERALIST]

    if specialists:
        tool_group = "specialists"
    elif state["intent"] in KNOWLEDGE_INTENTS:
        tool_group = "knowledge"
    else:  # chitchat, feedback, spam, unknown
        tool_group = "none"

    await record_step(
        session, run_id=state["run_id"], node="supervisor",
        output={
            "intent": state["intent"],
            "secondary_intent": state.get("secondary_intent"),
            "specialists": specialists,
            "tool_budget": tool_budget(len(specialists)),
            "tool_group": tool_group,
        },
    )
    return {"specialists": specialists, "tool_group": tool_group}


def dispatch(state: AgentState) -> list[Send] | str:
    """Fans out to one specialist branch per dispatched agent - LangGraph
    runs Send branches of one step concurrently, and reconcile waits for
    all of them. Each branch gets its own share of MAX_TOOL_CALLS.
    """
    specialists = state.get("specialists") or []
    if not specialists:
        return "reconcile"
    budgets = tool_budget(len(specialists))
    return [
        Send("specialist", {**state, "agent": name, "budget": budget})
        for name, budget in zip(specialists, budgets, strict=True)
    ]
