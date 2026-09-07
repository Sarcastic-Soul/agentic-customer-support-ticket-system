from datetime import UTC, datetime
from decimal import Decimal

from app.models import Customer, Order, Transaction
from app.tools.context import ToolContext
from app.tools.transactions import get_refund_status, request_refund


async def _make_customer(session, key: str) -> Customer:
    customer = Customer(full_name=f"Test {key}", email=f"{key}@example.com")
    session.add(customer)
    await session.flush()
    return customer


async def _make_order(session, customer: Customer, key: str) -> Order:
    order = Order(
        order_number=f"ORD-TEST-{key}",
        customer_id=customer.id,
        status="delivered",
        total_amount="5000.00",
        placed_at=datetime.now(UTC),
        shipping_address={},
    )
    session.add(order)
    await session.flush()
    return order


async def _make_txn(session, order: Order, customer: Customer, **kwargs) -> Transaction:
    defaults = {
        "txn_ref": f"TXN-TEST-{order.id}-{kwargs.get('suffix', 1)}",
        "order_id": order.id,
        "customer_id": customer.id,
        "type": "payment",
        "method": "card",
        "amount": "5000.00",
        "status": "captured",
        "created_at": datetime.now(UTC),
    }
    kwargs.pop("suffix", None)
    defaults.update(kwargs)
    txn = Transaction(**defaults)
    session.add(txn)
    await session.flush()
    return txn


async def test_refund_denied_above_ceiling_even_with_matching_fault(session):
    customer = await _make_customer(session, "refund-ceiling")
    order = await _make_order(session, customer, "ceiling")
    txn = await _make_txn(session, order, customer, suffix=1)
    # a duplicate captured payment on the same order - a genuine fault
    await _make_txn(session, order, customer, suffix=2)

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("5000.00"), reason="duplicate charge")

    assert result["denied"] is True
    assert result["requires_human"] is True
    assert "exceeds" in result["reason"]


async def test_refund_allowed_within_ceiling_with_duplicate_charge(session):
    customer = await _make_customer(session, "refund-dup")
    order = await _make_order(session, customer, "dup")
    order.total_amount = "500.00"
    txn = await _make_txn(session, order, customer, suffix=1, amount="500.00")
    await _make_txn(session, order, customer, suffix=2, amount="500.00")  # duplicate

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")

    assert result["requested"] is True
    assert result["status"] == "requested"


async def test_refund_requires_human_without_any_fault(session):
    customer = await _make_customer(session, "refund-goodwill")
    order = await _make_order(session, customer, "goodwill")
    txn = await _make_txn(session, order, customer, suffix=1, amount="300.00")

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("300.00"), reason="just don't want it")

    assert result["denied"] is True
    assert result["requires_human"] is True
    assert "matching" in result["reason"]


async def test_refund_scoped_to_customer_returns_nothing_for_others_transaction(session):
    owner = await _make_customer(session, "txn-owner")
    stranger = await _make_customer(session, "txn-stranger")
    order = await _make_order(session, owner, "scoped")
    txn = await _make_txn(session, order, owner, suffix=1)

    ctx = ToolContext(session=session, customer_id=stranger.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("100.00"), reason="not mine")

    assert result == {"error": "transaction_not_found"}


async def test_get_refund_status_reports_no_refund_when_none_exists(session):
    customer = await _make_customer(session, "refund-status")
    order = await _make_order(session, customer, "status")
    txn = await _make_txn(session, order, customer, suffix=1)

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await get_refund_status(ctx, txn.txn_ref)

    assert result == {"error": "no_refund_on_this_transaction"}
