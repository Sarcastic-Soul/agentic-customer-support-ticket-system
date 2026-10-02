"""Joins the specialists' reports and settles any disagreement between them
in code - see app/policy/conflicts.py for the rule table. Records one step
with every conflict found, which the ticket trace and /admin/metrics/agents
read back.
"""

from decimal import Decimal

from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.agent.steps import record_step
from app.config import settings
from app.policy.conflicts import describe, reconcile


async def reconcile_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]
    order = {name: i for i, name in enumerate(state.get("specialists") or [])}
    reports = sorted(
        state.get("specialist_reports") or [], key=lambda r: order.get(r["agent"], 99)
    )
    if not reports:
        return {"tool_results": [], "conflicts": [], "to_commit": [], "force_approval": []}

    res = reconcile(reports, refund_ceiling=Decimal(str(settings.auto_refund_ceiling)))

    await record_step(
        session, run_id=state["run_id"], node="reconcile",
        output={
            "agents": [r["agent"] for r in reports],
            "notes": {r["agent"]: r["note"] for r in reports},
            "proposals": [describe(p) for r in reports for p in r["proposals"]],
            "commit": [describe(p) for p in res.commit],
            "conflicts": res.conflicts,
            "escalate": res.escalate[0] if res.escalate else None,
        },
    )

    update: dict = {
        "tool_results": res.tool_results,
        "tool_call_count": sum(r["tool_calls"] for r in reports),
        "conflicts": res.conflicts,
        "to_commit": res.commit,
        "force_approval": sorted(t for t in res.force_approval if t),
    }
    if res.escalate:
        update["escalation_reason_code"], update["escalation_priority"] = res.escalate
    return update


def route_after_reconcile(state: AgentState) -> str:
    return "escalate" if state.get("escalation_reason_code") else "commit"
