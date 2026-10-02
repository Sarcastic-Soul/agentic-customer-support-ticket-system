"""The specialist agents: which intents each one owns, which tools it may
call, and which prompt it runs with. One table, read by the supervisor (to
pick who works a message) and by the specialist node (to run one of them).

Specialists split the work by *domain* (money, the order record, the
parcel), never by channel - see docs/decisions/0006-specialist-agents.md
for why this beats per-channel agents (the first draft's design).

Knowledge questions have no specialist of their own: the retrieve node is
the knowledge lane, and its step is tagged agent="knowledge" in the trace.
"""

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class Specialist:
    name: str
    intents: frozenset[str]
    tools: tuple[str, ...]
    prompt: str


ORDERS = Specialist(
    name="orders",
    intents=frozenset({"order_cancel", "order_modify", "order_return"}),
    tools=(
        "list_recent_orders", "get_order",
        "check_cancellation_eligibility", "request_cancellation",
        "check_return_eligibility", "initiate_return",
    ),
    prompt="specialist_orders",
)

LOGISTICS = Specialist(
    name="logistics",
    intents=frozenset({"order_status", "delivery_issue", "damaged_or_missing_item"}),
    tools=(
        "list_recent_orders", "get_order", "track_shipment",
        "open_carrier_investigation", "check_return_eligibility", "initiate_return",
    ),
    prompt="specialist_logistics",
)

PAYMENTS = Specialist(
    name="payments",
    intents=frozenset({
        "refund_status", "refund_request", "payment_failed",
        "invoice_request", "billing_dispute",
    }),
    tools=(
        "list_recent_orders", "list_transactions_for_order", "get_transaction",
        "get_refund_status", "explain_payment_failure", "request_refund",
        "generate_invoice",
    ),
    prompt="specialist_payments",
)

SPECIALISTS: dict[str, Specialist] = {s.name: s for s in (ORDERS, LOGISTICS, PAYMENTS)}

# Dispatch order when two specialists work one message: the one that owns
# the primary intent goes first, and ties in conflict resolution go to the
# earlier one (see pick_specialists and app/policy/conflicts.py).
MAX_SPECIALISTS_PER_TURN = 2

KNOWLEDGE_INTENTS = frozenset({
    "product_question", "policy_question", "account_issue", "complaint",
})


def specialist_for_intent(intent: str | None) -> str | None:
    for spec in SPECIALISTS.values():
        if intent in spec.intents:
            return spec.name
    return None


def pick_specialists(intent: str | None, secondary_intent: str | None) -> list[str]:
    """Primary intent's owner first, then the secondary intent's owner if it
    is a different specialist. Never more than MAX_SPECIALISTS_PER_TURN -
    each one costs LLM calls against a free-tier rate limit.
    """
    picked: list[str] = []
    for i in (intent, secondary_intent):
        name = specialist_for_intent(i)
        if name and name not in picked:
            picked.append(name)
    return picked[:MAX_SPECIALISTS_PER_TURN]


def tool_budget(n_specialists: int) -> list[int]:
    """Splits MAX_TOOL_CALLS across the specialists working one turn, so the
    whole turn still stays inside the one limit (CLAUDE.md non-negotiable
    #7). The first specialist gets the remainder: 5 -> [5], [3, 2].
    """
    if n_specialists == 0:
        return []
    base, extra = divmod(settings.max_tool_calls, n_specialists)
    return [base + (1 if i < extra else 0) for i in range(n_specialists)]


# The "single_agent" eval ablation replaces the specialists with this one
# agent holding every tool - the pre-specialist design, kept runnable so the
# two can be compared on the same dataset.
GENERALIST = "generalist"


def all_tools() -> list[str]:
    seen: dict[str, None] = {}
    for spec in SPECIALISTS.values():
        seen.update(dict.fromkeys(spec.tools))
    return list(seen)


def tools_for(name: str) -> list[str]:
    # Stage 11 "all tools exposed" ablation: every specialist gets every
    # tool, which removes the domain restriction the split exists for.
    if name == GENERALIST or settings.eval_ablation == "all_tools":
        return all_tools()
    return list(SPECIALISTS[name].tools)


def prompt_for(name: str) -> str:
    return SPECIALISTS[name].prompt if name in SPECIALISTS else "act"
