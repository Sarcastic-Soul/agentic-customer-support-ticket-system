"""The conflict rule table - pure functions, no DB or model needed. This is
where two specialists that disagree get settled; see app/policy/conflicts.py.
"""

from decimal import Decimal

from app.policy.conflicts import reconcile

CEILING = Decimal("1000")


def _report(agent, *, results=(), proposals=()):
    return {
        "agent": agent,
        "tool_results": list(results),
        "proposals": [{**p, "agent": agent, "id": f"{agent}:{i}"} for i, p in enumerate(proposals)],
        "note": None,
        "tool_calls": len(results) + len(proposals),
        "budget": 3,
    }


def _read(tool, order_number, status):
    return {"tool": tool, "args": {"order_number": order_number},
            "result": {"order_number": order_number, "status": status}}


def _cancel(order_number):
    return {"tool": "request_cancellation", "args": {"order_number": order_number},
            "result": {"proposed": True, "order_number": order_number}}


def _return(order_number, sku="SKU-1"):
    return {"tool": "initiate_return", "args": {"order_number": order_number, "sku": sku},
            "result": {"proposed": True, "order_number": order_number}}


def _refund(txn_ref, order_number, amount="500"):
    return {"tool": "request_refund",
            "args": {"txn_ref": txn_ref, "amount": amount, "reason": "x"},
            "result": {"proposed": True, "order_number": order_number}}


def _investigate(order_number):
    return {"tool": "open_carrier_investigation", "args": {"order_number": order_number},
            "result": {"proposed": True, "order_number": order_number}}


def _skipped(res):
    return [r for r in res.tool_results if r["result"].get("skipped")]


def test_no_conflict_commits_everything():
    res = reconcile(
        [_report("orders", proposals=[_cancel("ORD-1")]),
         _report("payments", proposals=[_refund("TXN-9", "ORD-2")])],
        refund_ceiling=CEILING,
    )
    assert res.conflicts == []
    assert [p["tool"] for p in res.commit] == ["request_cancellation", "request_refund"]
    assert res.escalate is None


def test_cancel_wins_over_refund_on_same_order():
    res = reconcile(
        [_report("orders", proposals=[_cancel("ORD-1")]),
         _report("payments", proposals=[_refund("TXN-1", "ORD-1")])],
        refund_ceiling=CEILING,
    )
    assert [p["tool"] for p in res.commit] == ["request_cancellation"]
    assert res.conflicts[0]["rule"] == "cancel_covers_refund"
    assert res.conflicts[0]["agents"] == ["orders", "payments"]
    assert _skipped(res)[0]["tool"] == "request_refund"
    assert res.escalate is None


def test_investigation_wins_over_refund_and_return():
    res = reconcile(
        [_report("logistics", proposals=[_investigate("ORD-1"), _return("ORD-1")]),
         _report("payments", proposals=[_refund("TXN-1", "ORD-1")])],
        refund_ceiling=CEILING,
    )
    assert [p["tool"] for p in res.commit] == ["open_carrier_investigation"]
    assert {c["rule"] for c in res.conflicts} == {
        "investigation_before_refund", "investigation_before_return",
    }


def test_return_wins_over_refund():
    res = reconcile(
        [_report("orders", proposals=[_return("ORD-1")]),
         _report("payments", proposals=[_refund("TXN-1", "ORD-1")])],
        refund_ceiling=CEILING,
    )
    assert [p["tool"] for p in res.commit] == ["initiate_return"]
    assert res.conflicts[0]["rule"] == "return_covers_refund"


def test_duplicate_proposal_is_kept_once():
    res = reconcile(
        [_report("orders", proposals=[_return("ORD-1")]),
         _report("logistics", proposals=[_return("ORD-1")])],
        refund_ceiling=CEILING,
    )
    assert len(res.commit) == 1
    assert res.commit[0]["agent"] == "orders"  # earlier report wins the tie
    assert res.conflicts[0]["kind"] == "duplicate"


def test_carrier_is_truth_when_order_and_tracking_disagree():
    res = reconcile(
        [_report("orders", results=[_read("get_order", "ORD-1", "delivered")],
                 proposals=[_return("ORD-1")]),
         _report("logistics", results=[_read("track_shipment", "ORD-1", "in_transit")])],
        refund_ceiling=CEILING,
    )
    conflict = res.conflicts[0]
    assert conflict["kind"] == "fact"
    assert conflict["rule"] == "carrier_is_truth_for_parcel"
    assert conflict["resolution"] == "rule"
    # writes planned on the wrong story are held, not escalated
    assert res.commit == []
    assert res.escalate is None
    note = next(r for r in res.tool_results if r["tool"] == "reconcile")
    assert note["result"]["carrier_status"] == "in_transit"


def test_matching_statuses_are_not_a_conflict():
    res = reconcile(
        [_report("orders", results=[_read("get_order", "ORD-1", "shipped")]),
         _report("logistics", results=[_read("track_shipment", "ORD-1", "in_transit")])],
        refund_ceiling=CEILING,
    )
    assert res.conflicts == []


def test_refunds_that_pass_ceiling_together_go_to_approval_queue():
    res = reconcile(
        [_report("payments", proposals=[_refund("TXN-1", "ORD-1", "600"),
                                        _refund("TXN-2", "ORD-2", "600")])],
        refund_ceiling=CEILING,
    )
    assert len(res.commit) == 2
    assert res.force_approval == {"TXN-1", "TXN-2"}
    assert res.conflicts[0]["rule"] == "combined_refund_over_ceiling"


def test_refunds_under_ceiling_together_are_not_forced():
    res = reconcile(
        [_report("payments", proposals=[_refund("TXN-1", "ORD-1", "300"),
                                        _refund("TXN-2", "ORD-2", "300")])],
        refund_ceiling=CEILING,
    )
    assert res.force_approval == set()


def test_reads_from_every_agent_are_kept_in_tool_results():
    res = reconcile(
        [_report("orders", results=[_read("get_order", "ORD-1", "shipped")]),
         _report("logistics", results=[_read("track_shipment", "ORD-1", "shipped")])],
        refund_ceiling=CEILING,
    )
    assert [r["agent"] for r in res.tool_results] == ["orders", "logistics"]
