"""What happens when two specialists disagree. Runs in code, never in a
prompt - same rule as authorize(): a model can argue, a rule table can't be
argued with.

Specialists only *propose* write actions (see ToolContext.propose_only), so
by the time this runs nothing has changed in the database yet. This module
looks at every specialist's reads and proposals together and decides:

- which proposals get committed,
- which are dropped, with a note the customer reply can use,
- whether the disagreement is one no rule settles, in which case nothing is
  committed and the ticket goes to a human with both sides in the packet.

Escalating is the last resort, not the default: every kind below has a rule
that settles it in code. Only a pair of actions the table has never seen
escalates - with today's tools that can't happen, it is a guard for new
tools added later.

Three kinds of conflict:

- **fact**: two sources the specialists read disagree about the same order
  (the order record says delivered, the carrier says in transit). Settled
  by a source-of-truth rule: the carrier's scan is what says where the
  parcel is. Writes on that order are held for this turn (they were
  planned on the other story), and the reply is told which fact to use.
- **duplicate**: two proposals for the same action on the same target
  (both logistics and orders propose a return for one item). One is kept.
- **action**: different actions on one order that can't all happen
  (cancel + refund would refund twice). Settled by the rule table below;
  anything the table doesn't cover escalates.

Pure functions on plain dicts, so the whole table is unit-testable without
a database or a model.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Order/shipment statuses that describe where the parcel really is. If
# either side is in one of these and the two differ, they are telling
# different stories about the same parcel.
_SETTLED_STATUSES = {"delivered", "cancelled", "returned"}

CANCEL = "request_cancellation"
RETURN = "initiate_return"
REFUND = "request_refund"
INVESTIGATE = "open_carrier_investigation"

# (winner, loser) -> (rule name, note for the customer reply about the
# loser). Checked in this order. The notes restate policy that is in the
# knowledge base ("Order cancellation policy", "Return window", "Parcel
# marked delivered but not received"), so verify can ground them.
_PAIR_RULES: dict[tuple[str, str], tuple[str, str]] = {
    (CANCEL, RETURN): (
        "cancel_over_return",
        "The order is being cancelled rather than returned, because it has not shipped yet.",
    ),
    (CANCEL, REFUND): (
        "cancel_covers_refund",
        "No separate refund was needed: cancelling the order refunds the full amount "
        "paid to the original payment method automatically.",
    ),
    (INVESTIGATE, REFUND): (
        "investigation_before_refund",
        "No refund yet: a carrier investigation is open, and it ends in either a free "
        "replacement or a full refund within 5 business days.",
    ),
    (INVESTIGATE, RETURN): (
        "investigation_before_return",
        "No return was started: the parcel hasn't been received, so a carrier "
        "investigation was opened instead.",
    ),
    (RETURN, REFUND): (
        "return_covers_refund",
        "No separate refund was needed now: the refund for a returned item is issued "
        "once the item is received back at the warehouse.",
    ),
}

_HELD_NOTE = (
    "Not done this turn: the order record and the carrier's tracking disagree, so "
    "nothing was changed on this order. Use what the carrier's tracking shows."
)


@dataclass
class Resolution:
    commit: list[dict] = field(default_factory=list)
    # refunds that must go to the human approval queue even though each one
    # alone would be auto-approved (see rule combined_refund_over_ceiling)
    force_approval: set[str] = field(default_factory=set)
    tool_results: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    escalate: tuple[str, str] | None = None  # (reason_code, priority)


def describe(p: dict) -> str:
    target = p["args"].get("txn_ref") or p["args"].get("order_number") or "?"
    if p["args"].get("sku"):
        target = f"{target} {p['args']['sku']}"
    return f"{p['agent']}: {p['tool']}({target})"


def _target(p: dict) -> tuple:
    a = p["args"]
    return (p["tool"], a.get("txn_ref"), a.get("order_number"), a.get("sku"))


def _order_of(p: dict) -> str | None:
    return p["args"].get("order_number") or p.get("result", {}).get("order_number")


def _amount(p: dict) -> Decimal:
    try:
        return Decimal(str(p["args"].get("amount", "0")))
    except InvalidOperation:
        return Decimal("0")


def _statuses_disagree(order_status: str, shipment_status: str) -> bool:
    if order_status == shipment_status:
        return False
    return order_status in _SETTLED_STATUSES or shipment_status in _SETTLED_STATUSES


def _skipped(p: dict, reason: str) -> dict:
    return {
        "tool": p["tool"], "args": p["args"], "agent": p["agent"],
        "result": {"skipped": True, "reason": reason},
    }


def reconcile(reports: list[dict], *, refund_ceiling: Decimal) -> Resolution:
    """`reports` are specialist reports in dispatch order, each
    {"agent", "tool_results": [...], "proposals": [...]}. Earlier reports
    win ties.
    """
    res = Resolution()
    results = [
        {**r, "agent": rep["agent"]} for rep in reports for r in rep["tool_results"]
    ]
    proposals = [p for rep in reports for p in rep["proposals"]]

    # 1. fact conflicts: the order record vs the carrier
    order_seen: dict[str, tuple[str, str]] = {}
    shipment_seen: dict[str, tuple[str, str]] = {}
    for r in results:
        status = r["result"].get("status")
        number = r["args"].get("order_number") or r["result"].get("order_number")
        if not status or not number:
            continue
        if r["tool"] == "get_order":
            order_seen[number] = (status, r["agent"])
        elif r["tool"] == "track_shipment":
            shipment_seen[number] = (status, r["agent"])

    held_orders: set[str] = set()
    for number, (o_status, o_agent) in order_seen.items():
        if number not in shipment_seen:
            continue
        s_status, s_agent = shipment_seen[number]
        if not _statuses_disagree(o_status, s_status):
            continue
        held_orders.add(number)
        touched = [p for p in proposals if _order_of(p) == number]
        res.conflicts.append({
            "kind": "fact",
            "agents": sorted({o_agent, s_agent}),
            "subject": f"order {number}",
            "detail": (
                f"The order record says '{o_status}' but the carrier says "
                f"'{s_status}'."
            ),
            "resolution": "rule",
            "rule": "carrier_is_truth_for_parcel",
            "kept": f"{s_agent}: track_shipment({number}) = {s_status}",
            "dropped": [f"{o_agent}: get_order({number}) = {o_status}"]
            + [describe(p) for p in touched],
        })
        res.tool_results.append({
            "tool": "reconcile", "agent": None, "args": {"order_number": number},
            "result": {
                "note": (
                    f"The order record says '{o_status}' but the carrier's tracking "
                    f"says '{s_status}'. The carrier's tracking is the source of "
                    "truth for where the parcel is - tell the customer what the "
                    "carrier shows, not the order record."
                ),
                "carrier_status": s_status,
            },
        })

    # 2. duplicates: same action on the same target
    live: list[dict] = []
    seen: dict[tuple, dict] = {}
    for p in proposals:
        key = _target(p)
        if key in seen:
            first = seen[key]
            res.conflicts.append({
                "kind": "duplicate",
                "agents": sorted({first["agent"], p["agent"]}),
                "subject": f"order {_order_of(p)}" if _order_of(p) else p["tool"],
                "detail": f"{first['agent']} and {p['agent']} both proposed {p['tool']}.",
                "resolution": "rule",
                "rule": "same_action_once",
                "kept": describe(first),
                "dropped": [describe(p)],
            })
            continue
        seen[key] = p
        live.append(p)

    # 3. different actions on the same order
    by_order: dict[str, list[dict]] = {}
    for p in live:
        number = _order_of(p)
        if number and number not in held_orders:
            by_order.setdefault(number, []).append(p)

    dropped_ids: set[int] = set()
    skip_notes: list[dict] = []
    for number, actions in by_order.items():
        tools = {p["tool"] for p in actions}
        for (winner, loser), (rule, note) in _PAIR_RULES.items():
            if winner not in tools:
                continue
            winning = next(p for p in actions if p["tool"] == winner)
            losers = [p for p in actions if p["tool"] == loser and id(p) not in dropped_ids]
            if not losers:
                continue
            for p in losers:
                dropped_ids.add(id(p))
                skip_notes.append(_skipped(p, note))
            res.conflicts.append({
                "kind": "action",
                "agents": sorted({winning["agent"], *(p["agent"] for p in losers)}),
                "subject": f"order {number}",
                "detail": (
                    f"{winning['agent']} proposed {winner} while "
                    f"{', '.join(sorted({p['agent'] for p in losers}))} proposed "
                    f"{loser}. Both can't happen."
                ),
                "resolution": "rule",
                "rule": rule,
                "kept": describe(winning),
                "dropped": [describe(p) for p in losers],
            })

        remaining = {p["tool"] for p in actions if id(p) not in dropped_ids}
        if len(remaining) > 1:
            # Two different writes on one order that no rule covers - don't
            # guess which one the customer meant.
            res.conflicts.append({
                "kind": "action",
                "agents": sorted({p["agent"] for p in actions}),
                "subject": f"order {number}",
                "detail": f"Proposals {sorted(remaining)} on one order and no rule covers them.",
                "resolution": "escalated",
                "rule": "no_rule",
                "kept": None,
                "dropped": [describe(p) for p in actions if id(p) not in dropped_ids],
            })
            res.escalate = res.escalate or ("agent_conflict", "P2")

    # 4. refunds that are each fine but together pass the ceiling
    refunds = [p for p in live if p["tool"] == REFUND and id(p) not in dropped_ids]
    if len(refunds) > 1:
        total = sum((_amount(p) for p in refunds), Decimal("0"))
        if total > refund_ceiling:
            res.conflicts.append({
                "kind": "action",
                "agents": sorted({p["agent"] for p in refunds}),
                "subject": "refunds this turn",
                "detail": (
                    f"{len(refunds)} refunds totalling {total} pass the {refund_ceiling} "
                    "auto-approval ceiling together, though each is under it alone. "
                    "Both still go ahead, but through the approval queue."
                ),
                "resolution": "rule",
                "rule": "combined_refund_over_ceiling",
                "kept": "all refunds, sent to the human approval queue",
                "dropped": [],
            })
            res.force_approval = {p["args"].get("txn_ref") for p in refunds}

    res.tool_results = results + res.tool_results + skip_notes

    survivors = []
    for p in live:
        if id(p) in dropped_ids:
            continue
        if _order_of(p) in held_orders:
            res.tool_results.append(_skipped(p, _HELD_NOTE))
            continue
        survivors.append(p)
    if res.escalate:
        # Nothing is committed while a human is needed - they see every
        # proposal in the handoff packet and decide.
        for p in survivors:
            res.tool_results.append(
                _skipped(p, "Held for a support specialist to review with the rest of this case.")
            )
    else:
        res.commit = survivors
    return res
