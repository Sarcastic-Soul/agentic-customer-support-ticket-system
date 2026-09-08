"""Restricts the tool set to the intent's family before the model ever sees
a tool schema. This is the honest version of "specialised agents": same
effect (the model can't call get_order for a refund question) for a
fraction of the code, and it cuts prompt size and wrong-tool-call risk.
Ticket tools (escalate_ticket etc.) don't exist until Stage 6, so
account_issue/complaint fall back to knowledge-only for now.
"""

from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.config import settings

ORDER_TOOLS = [
    "list_recent_orders", "get_order", "track_shipment",
    "check_cancellation_eligibility", "request_cancellation",
    "check_return_eligibility", "initiate_return",
]

TRANSACTION_TOOLS = [
    "get_transaction", "list_transactions_for_order", "get_refund_status",
    "explain_payment_failure", "request_refund", "generate_invoice",
]

_ORDER_INTENTS = {
    "order_status", "order_cancel", "order_return", "order_modify",
    "delivery_issue", "damaged_or_missing_item",
}
_TRANSACTION_INTENTS = {
    "refund_status", "refund_request", "payment_failed",
    "invoice_request", "billing_dispute",
}
_KNOWLEDGE_INTENTS = {
    "product_question", "policy_question", "account_issue", "complaint",
}


def tools_for_group(tool_group: str) -> list[str]:
    # Stage 11 "all tools exposed" ablation: simulates removing plan_node's
    # restriction by handing over the full order+transaction toolset
    # whenever any tools would normally be used at all.
    if settings.eval_ablation == "all_tools" and tool_group in ("orders", "transactions"):
        return ORDER_TOOLS + TRANSACTION_TOOLS
    return {"orders": ORDER_TOOLS, "transactions": TRANSACTION_TOOLS}.get(tool_group, [])


async def plan_node(state: AgentState, config: RunnableConfig) -> dict:
    intent = state["intent"]
    if intent in _ORDER_INTENTS:
        tool_group = "orders"
    elif intent in _TRANSACTION_INTENTS:
        tool_group = "transactions"
    elif intent in _KNOWLEDGE_INTENTS:
        tool_group = "knowledge"
    else:  # chitchat, feedback, spam, unknown
        tool_group = "none"

    return {"tool_group": tool_group}
