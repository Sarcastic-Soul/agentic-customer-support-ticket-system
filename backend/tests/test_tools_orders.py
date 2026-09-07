from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Customer, Order, OrderItem, Ticket, ToolCall
from app.tools.context import ToolContext
from app.tools.orders import (
    check_cancellation_eligibility,
    get_order,
    initiate_return,
    request_cancellation,
)
from app.tools.registry import execute_tool, get_tool_spec


async def _make_customer(session, key: str) -> Customer:
    customer = Customer(full_name=f"Test {key}", email=f"{key}@example.com")
    session.add(customer)
    await session.flush()
    return customer


async def _make_ticket(session, customer: Customer) -> Ticket:
    ticket = Ticket(reference=f"T-TEST-{customer.id}", customer_id=customer.id, channel="web")
    session.add(ticket)
    await session.flush()
    return ticket


async def _make_order(session, customer: Customer, **kwargs) -> Order:
    defaults = {
        "order_number": f"ORD-TEST-{customer.id}",
        "customer_id": customer.id,
        "status": "placed",
        "total_amount": "999.00",
        "placed_at": datetime.now(UTC),
        "shipping_address": {},
    }
    defaults.update(kwargs)
    order = Order(**defaults)
    session.add(order)
    await session.flush()
    return order


async def test_get_order_returns_full_detail(session):
    customer = await _make_customer(session, "own")
    order = await _make_order(session, customer, status="delivered")
    session.add(
        OrderItem(order_id=order.id, sku="SKU-1", name="Widget", qty=1, unit_price="999.00")
    )
    await session.flush()

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await get_order(ctx, order.order_number)

    assert result["order_number"] == order.order_number
    assert result["status"] == "delivered"
    assert result["items"][0]["sku"] == "SKU-1"


async def test_get_order_scoped_to_customer_returns_nothing_for_others_order(session):
    owner = await _make_customer(session, "owner")
    stranger = await _make_customer(session, "stranger")
    order = await _make_order(session, owner)

    ctx = ToolContext(session=session, customer_id=stranger.id, ticket_id=0, run_id=0)
    result = await get_order(ctx, order.order_number)

    assert result == {
        "error": "order_not_found",
        "hint": "ask the customer to confirm the order number",
    }


async def test_request_cancellation_succeeds_within_window(session):
    customer = await _make_customer(session, "cancel-ok")
    order = await _make_order(
        session, customer, status="placed",
        cancellable_until=datetime.now(UTC) + timedelta(hours=2),
    )

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    eligibility = await check_cancellation_eligibility(ctx, order.order_number)
    assert eligibility["eligible"] is True

    result = await request_cancellation(ctx, order.order_number, reason="changed my mind")
    assert result == {"cancelled": True, "order_number": order.order_number}

    await session.refresh(order)
    assert order.status == "cancelled"


async def test_request_cancellation_denied_once_shipped(session):
    customer = await _make_customer(session, "cancel-shipped")
    order = await _make_order(
        session, customer, status="shipped",
        cancellable_until=datetime.now(UTC) + timedelta(hours=2),
    )

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await request_cancellation(ctx, order.order_number, reason="changed my mind")

    assert result["denied"] is True
    assert "shipped" in result["reason"]
    await session.refresh(order)
    assert order.status == "shipped"  # unchanged


async def test_initiate_return_denied_for_non_returnable_item(session):
    customer = await _make_customer(session, "return-denied")
    order = await _make_order(
        session, customer, status="delivered",
        return_window_ends=(datetime.now(UTC) + timedelta(days=3)).date(),
    )
    session.add(
        OrderItem(
            order_id=order.id, sku="SKU-NR", name="Final Sale Item",
            qty=1, unit_price="500.00", returnable=False,
        )
    )
    await session.flush()

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0)
    result = await initiate_return(ctx, order.order_number, "SKU-NR", reason="wrong size")

    assert result["denied"] is True
    assert "non-returnable" in result["reason"]


async def test_execute_tool_records_tool_call_row(session):
    customer = await _make_customer(session, "tool-call-log")
    order = await _make_order(session, customer, status="delivered")
    ticket = await _make_ticket(session, customer)

    ctx = ToolContext(session=session, customer_id=customer.id, ticket_id=ticket.id, run_id=0)
    spec = get_tool_spec("get_order")
    await execute_tool(spec, ctx, {"order_number": order.order_number})

    logged = (
        await session.execute(select(ToolCall).where(ToolCall.ticket_id == ticket.id))
    ).scalar_one()
    assert logged.tool_name == "get_order"
    assert logged.authorized is True
    assert logged.result["order_number"] == order.order_number
