from datetime import UTC, datetime, timedelta

from app.models import Customer, Order, Shipment
from app.tools.context import ToolContext
from app.tools.logistics import open_carrier_investigation


async def _make_parcel(session, key: str, *, delivered_hours_ago: int):
    customer = Customer(full_name=f"Test {key}", email=f"{key}@example.com")
    session.add(customer)
    await session.flush()
    delivered_at = datetime.now(UTC) - timedelta(hours=delivered_hours_ago)
    order = Order(
        order_number=f"ORD-TEST-{key}", customer_id=customer.id, status="delivered",
        total_amount="999.00", placed_at=delivered_at - timedelta(days=4),
        delivered_at=delivered_at, shipping_address={},
    )
    session.add(order)
    await session.flush()
    shipment = Shipment(
        order_id=order.id, carrier="Ekart", tracking_no=f"TRK-{key}", status="delivered",
        events=[],
    )
    session.add(shipment)
    await session.flush()
    return customer, order, shipment


def _ctx(session, customer, **kwargs):
    return ToolContext(session=session, customer_id=customer.id, ticket_id=0, run_id=0, **kwargs)


async def test_investigation_opened_after_waiting_period(session):
    customer, order, shipment = await _make_parcel(session, "inv-open", delivered_hours_ago=48)
    result = await open_carrier_investigation(_ctx(session, customer), order.order_number, "lost")

    assert result["opened"] is True
    assert any(e["type"] == "investigation_opened" for e in shipment.events)


async def test_investigation_denied_inside_waiting_period(session):
    customer, order, _ = await _make_parcel(session, "inv-early", delivered_hours_ago=3)
    result = await open_carrier_investigation(_ctx(session, customer), order.order_number, "lost")

    assert result["denied"] is True


async def test_investigation_is_opened_once(session):
    customer, order, _ = await _make_parcel(session, "inv-twice", delivered_hours_ago=48)
    ctx = _ctx(session, customer)
    await open_carrier_investigation(ctx, order.order_number, "missing")
    second = await open_carrier_investigation(ctx, order.order_number, "still missing")

    assert second["already_open"] is True


async def test_propose_only_investigation_changes_nothing(session):
    customer, order, shipment = await _make_parcel(session, "inv-propose", delivered_hours_ago=48)
    ctx = _ctx(session, customer, propose_only=True)
    result = await open_carrier_investigation(ctx, order.order_number, "missing")

    assert result["proposed"] is True
    assert shipment.events == []


async def test_investigation_scoped_to_customer(session):
    _, order, _ = await _make_parcel(session, "inv-owner", delivered_hours_ago=48)
    stranger = Customer(full_name="Test stranger", email="inv-stranger@example.com")
    session.add(stranger)
    await session.flush()

    result = await open_carrier_investigation(_ctx(session, stranger), order.order_number, "x")

    assert result == {"error": "order_not_found"}
