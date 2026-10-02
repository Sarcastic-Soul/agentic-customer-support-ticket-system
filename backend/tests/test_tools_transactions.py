from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import Customer, Order, Refund, Ticket, Transaction
from app.tools.context import ToolContext
from app.tools.registry import execute_tool, get_tool_spec
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
    # A Decimal, as a row loaded from Postgres would be - the object stays in
    # the session's identity map, so a str here would leak into the tool.
    defaults["amount"] = Decimal(str(defaults["amount"]))
    txn = Transaction(**defaults)
    session.add(txn)
    await session.flush()
    return txn


async def test_refund_above_ceiling_goes_to_approval_queue(session):
    # Above the ceiling the AI no longer hands the whole ticket over: the
    # refund is recorded as "requested" and waits in the console's approval
    # queue (docs/decisions/0007-fewer-handoffs.md).
    customer = await _make_customer(session, "refund-ceiling")
    order = await _make_order(session, customer, "ceiling")
    txn = await _make_txn(session, order, customer, suffix=1)
    # a duplicate captured payment on the same order - a genuine fault
    await _make_txn(session, order, customer, suffix=2)

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("5000.00"), reason="duplicate charge")

    assert result["pending_approval"] is True
    assert "exceeds" in result["reason"]
    refund = await session.get(Refund, result["refund_id"])
    assert refund.status == "requested"
    assert refund.expected_credit_by is None


async def test_refund_approved_within_ceiling_with_duplicate_charge(session):
    customer = await _make_customer(session, "refund-dup")
    order = await _make_order(session, customer, "dup")
    order.total_amount = "500.00"
    txn = await _make_txn(session, order, customer, suffix=1, amount="500.00")
    await _make_txn(session, order, customer, suffix=2, amount="500.00")  # duplicate

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")

    assert result["approved"] is True
    assert result["status"] == "approved"
    assert result["expected_credit_by"]


async def test_goodwill_refund_goes_to_approval_queue(session):
    customer = await _make_customer(session, "refund-goodwill")
    order = await _make_order(session, customer, "goodwill")
    txn = await _make_txn(session, order, customer, suffix=1, amount="300.00")

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("300.00"), reason="just don't want it")

    assert result["pending_approval"] is True
    assert "matching" in result["reason"]


async def test_force_approval_sends_an_allowed_refund_to_the_queue(session):
    # reconcile sets force_approval when several refunds together pass the
    # ceiling, even though each one alone would be auto-approved
    customer = await _make_customer(session, "refund-forced")
    order = await _make_order(session, customer, "forced")
    txn = await _make_txn(session, order, customer, suffix=1, amount="500.00")
    await _make_txn(session, order, customer, suffix=2, amount="500.00")

    ctx = ToolContext(
        session=session, customer_id=customer.id, ticket_id=0, run_id=0, force_approval=True
    )
    result = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")

    assert result["pending_approval"] is True


async def test_second_refund_on_same_payment_is_denied(session):
    customer = await _make_customer(session, "refund-twice")
    order = await _make_order(session, customer, "twice")
    txn = await _make_txn(session, order, customer, suffix=1, amount="500.00")
    await _make_txn(session, order, customer, suffix=2, amount="500.00")

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    first = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")
    second = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")

    assert first["approved"] is True
    assert second["denied"] is True
    assert second["refund_id"] == first["refund_id"]


async def test_refund_above_payment_amount_is_denied(session):
    customer = await _make_customer(session, "refund-too-much")
    order = await _make_order(session, customer, "too-much")
    txn = await _make_txn(session, order, customer, suffix=1, amount="300.00")

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_refund(ctx, txn.txn_ref, Decimal("900.00"), reason="more please")

    assert result["denied"] is True


async def test_propose_only_refund_writes_nothing(session):
    customer = await _make_customer(session, "refund-propose")
    order = await _make_order(session, customer, "propose")
    txn = await _make_txn(session, order, customer, suffix=1, amount="500.00")
    await _make_txn(session, order, customer, suffix=2, amount="500.00")

    ctx = ToolContext(
        session=session, customer_id=customer.id, ticket_id=0, run_id=0, propose_only=True
    )
    result = await request_refund(ctx, txn.txn_ref, Decimal("500.00"), reason="duplicate charge")

    assert result["proposed"] is True
    assert result["needs_approval"] is False
    rows = (await session.execute(select(Refund).where(Refund.transaction_id == txn.id))).all()
    assert rows == []


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


async def test_execute_tool_coerces_string_amount_from_llm_tool_call(session):
    # Real bug, found live: Gemini's tool-call JSON sends a Decimal-typed
    # arg as a plain string ("4200.00"), and request_refund does real
    # arithmetic on `amount` (comparing it to the policy ceiling) - without
    # coercing args through the tool's schema first, that raised
    # "'>' not supported between instances of 'str' and 'decimal.Decimal'"
    # instead of returning a denial. See docs/PROGRESS.md Stage 6.
    customer = await _make_customer(session, "refund-string-amount")
    order = await _make_order(session, customer, "string-amount")
    txn = await _make_txn(session, order, customer, suffix=1, amount="5000.00")
    await _make_txn(session, order, customer, suffix=2, amount="5000.00")  # duplicate -> a fault

    ticket = Ticket(reference=f"T-TEST-{order.id}", customer_id=customer.id, channel="web")
    session.add(ticket)
    await session.flush()

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=ticket.id, run_id=0)
    spec = get_tool_spec("request_refund")
    result = await execute_tool(
        spec, ctx, {"txn_ref": txn.txn_ref, "amount": "5000.00", "reason": "duplicate"}
    )

    assert result["pending_approval"] is True
    assert "exceeds" in result["reason"]
