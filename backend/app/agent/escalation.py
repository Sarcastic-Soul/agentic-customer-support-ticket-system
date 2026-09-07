"""Builds the handoff packet - the thing that turns "the AI gave up" into
"the AI did the first 80% of the work". See docs/05-escalation-policy.md.
`summary` and `suggested_reply` are LLM-generated; everything else here is
assembled deterministically from state, never authored by the model - the
timeline and entities must be facts a human can trust without re-verifying.
"""

from datetime import UTC, datetime

from app.agent.nodes.answer import format_history
from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.llm.registry import get_llm
from app.llm.roles import LLMRole
from app.models import Customer, Ticket

REASON_DETAIL = {
    "customer_requested_human": "The customer explicitly asked to speak with a person.",
    "abusive_or_distress": (
        "The message contains language suggesting distress or abuse - handle with care."
    ),
    "legal_or_regulatory": (
        "The message references legal action, chargebacks, or a regulatory complaint."
    ),
    "turn_budget_exceeded": "The AI has not resolved this after several turns.",
    "low_intent_confidence": (
        "The AI was not confident enough in classifying what the customer needs."
    ),
    "policy_limit_exceeded": (
        "A requested action was denied by policy and requires human approval."
    ),
    "knowledge_gap": "The knowledge base and available tools don't cover this question.",
    "ungrounded_answer": "The AI's draft reply failed a groundedness check twice.",
}

REQUIRED_SKILL = {
    "policy_limit_exceeded": "refunds",
    "knowledge_gap": None,
    "ungrounded_answer": None,
}


async def build_handoff_packet(
    state: AgentState, *, ticket: Ticket, customer: Customer
) -> dict:
    reason_code = state["escalation_reason_code"]
    reason_detail = REASON_DETAIL.get(reason_code, reason_code)

    summary_prompt = load_prompt(
        "summarize_escalation",
        reason_code=reason_code,
        reason_detail=reason_detail,
        history=format_history(state["history"]),
        message=state["latest_message"],
        tool_results="\n".join(
            f"{r['tool']}({r['args']}) -> {r['result']}" for r in state["tool_results"]
        )
        or "(none)",
    )
    client = get_llm(LLMRole.summarize)
    summary_outcome = await client.ainvoke(summary_prompt)
    summary = summary_outcome.text or state["latest_message"]

    timeline = [{"who": "customer", "what": state["latest_message"]}]
    for r in state["tool_results"]:
        timeline.append({"who": "ai", "what": f"Called {r['tool']}({r['args']}) -> {r['result']}"})
    if state.get("draft"):
        timeline.append({"who": "ai", "what": f"Drafted (not sent): {state['draft']}"})
    timeline.append({"who": "system", "what": f"Escalated: {reason_detail}"})

    entities: dict[str, str] = {}
    for r in state["tool_results"]:
        for key in ("order_number", "txn_ref"):
            if key in r["args"]:
                entities[key] = r["args"][key]
        if "amount" in r["args"]:
            entities["amount"] = str(r["args"]["amount"])

    return {
        "ticket_reference": ticket.reference,
        "escalation_reason": reason_code,
        "reason_detail": reason_detail,
        "priority": state["escalation_priority"],
        "required_skill": REQUIRED_SKILL.get(reason_code),
        "customer": {
            "id": customer.id,
            "name": customer.full_name,
            "tier": customer.tier,
            "verified": customer.verified,
        },
        "summary": summary,
        "timeline": timeline,
        "entities": entities,
        "suggested_reply": state.get("draft"),
        "ai_confidence": state.get("intent_confidence"),
        "intent": state.get("intent"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
