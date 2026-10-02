"""Supervisor routing: which specialists work a message and how the tool
budget is split between them. Pure functions, no DB or model.
"""

from app.agent.specialists import (
    GENERALIST,
    SPECIALISTS,
    all_tools,
    pick_specialists,
    prompt_for,
    tool_budget,
    tools_for,
)
from app.config import settings


def test_single_intent_picks_one_specialist():
    assert pick_specialists("refund_request", None) == ["payments"]
    assert pick_specialists("order_status", None) == ["logistics"]
    assert pick_specialists("order_cancel", None) == ["orders"]


def test_compound_message_picks_both_primary_first():
    assert pick_specialists("delivery_issue", "refund_request") == ["logistics", "payments"]
    assert pick_specialists("refund_request", "delivery_issue") == ["payments", "logistics"]


def test_same_owner_twice_is_one_specialist():
    assert pick_specialists("refund_status", "payment_failed") == ["payments"]


def test_knowledge_and_chitchat_intents_pick_nobody():
    assert pick_specialists("policy_question", None) == []
    assert pick_specialists("unknown", None) == []


def test_tool_budget_never_exceeds_max_tool_calls():
    for n in range(0, 4):
        assert sum(tool_budget(n)) == (settings.max_tool_calls if n else 0)
    assert tool_budget(2)[0] >= tool_budget(2)[1]


def test_money_tools_only_with_payments():
    assert "request_refund" in tools_for("payments")
    assert "request_refund" not in tools_for("orders")
    assert "request_refund" not in tools_for("logistics")
    assert "request_cancellation" not in tools_for("payments")


def test_generalist_has_every_tool_and_the_act_prompt():
    assert set(tools_for(GENERALIST)) == set(all_tools())
    assert prompt_for(GENERALIST) == "act"
    for name in SPECIALISTS:
        assert prompt_for(name) == f"specialist_{name}"
