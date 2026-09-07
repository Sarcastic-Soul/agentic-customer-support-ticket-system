from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models import Order, OrderItem, Shipment
from app.policy.authorize import Decision, authorize_cancel_order, authorize_return_item
from app.tools.context import ToolContext
from app.tools.registry import register_tool


async def get_order_scoped(ctx: ToolContext, order_number: str) -> Order | None:
    """Every order lookup goes through this - scoped to ctx.customer_id, not
    whatever the model asked for. A request for another customer's order
    number returns nothing, not an error, exactly as if it didn't exist.
    """
    result = await ctx.session.execute(
        select(Order).where(
            Order.order_number == order_number, Order.customer_id == ctx.customer_id
        )
    )
    return result.scalar_one_or_none()


class ListRecentOrdersArgs(BaseModel):
    limit: int = Field(default=5, description="Max number of orders to return")


class OrderNumberArgs(BaseModel):
    order_number: str = Field(description="Order number, e.g. 'ORD-10432'")


class CancelOrderArgs(BaseModel):
    order_number: str
    reason: str = Field(description="Why the customer wants to cancel")


class ReturnItemArgs(BaseModel):
    order_number: str
    sku: str = Field(description="SKU of the item on the order")


class InitiateReturnArgs(ReturnItemArgs):
    reason: str


@register_tool(
    "list_recent_orders", "List the customer's most recent orders.", ListRecentOrdersArgs
)
async def list_recent_orders(ctx: ToolContext, limit: int = 5) -> dict:
    result = await ctx.session.execute(
        select(Order)
        .where(Order.customer_id == ctx.customer_id)
        .order_by(Order.placed_at.desc())
        .limit(limit)
    )
    orders = result.scalars().all()
    return {
        "orders": [
            {
                "order_number": o.order_number,
                "status": o.status,
                "total_amount": str(o.total_amount),
                "placed_at": o.placed_at.isoformat(),
            }
            for o in orders
        ]
    }


@register_tool(
    "get_order",
    "Get full detail for one of the customer's own orders by order number.",
    OrderNumberArgs,
)
async def get_order(ctx: ToolContext, order_number: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found", "hint": "ask the customer to confirm the order number"}

    items = (
        await ctx.session.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    ).scalars().all()

    return {
        "order_number": order.order_number,
        "status": order.status,
        "total_amount": str(order.total_amount),
        "currency": order.currency,
        "placed_at": order.placed_at.isoformat(),
        "promised_delivery": (
            order.promised_delivery.isoformat() if order.promised_delivery else None
        ),
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "items": [
            {"sku": i.sku, "name": i.name, "qty": i.qty, "returnable": i.returnable} for i in items
        ],
    }


@register_tool(
    "track_shipment",
    "Get live shipment/tracking status for one of the customer's own orders.",
    OrderNumberArgs,
)
async def track_shipment(ctx: ToolContext, order_number: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}

    shipment = (
        await ctx.session.execute(select(Shipment).where(Shipment.order_id == order.id))
    ).scalar_one_or_none()
    if shipment is None:
        return {"error": "not_yet_shipped", "order_status": order.status}

    return {
        "carrier": shipment.carrier,
        "tracking_no": shipment.tracking_no,
        "status": shipment.status,
        "eta": shipment.eta.isoformat() if shipment.eta else None,
        "last_location": shipment.last_location,
    }


@register_tool(
    "check_cancellation_eligibility",
    "Check whether one of the customer's own orders can still be cancelled.",
    OrderNumberArgs,
)
async def check_cancellation_eligibility(ctx: ToolContext, order_number: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    decision = authorize_cancel_order(order)
    return {"eligible": decision.decision == Decision.ALLOW, "reason": decision.reason}


@register_tool(
    "request_cancellation",
    "Cancel one of the customer's own orders, if eligible.",
    CancelOrderArgs,
    write=True,
)
async def request_cancellation(ctx: ToolContext, order_number: str, reason: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}

    decision = authorize_cancel_order(order)
    if decision.decision != Decision.ALLOW:
        return {"denied": True, "reason": decision.reason}

    order.status = "cancelled"
    await ctx.session.flush()
    return {"cancelled": True, "order_number": order.order_number}


@register_tool(
    "check_return_eligibility",
    "Check whether a specific item on one of the customer's own orders can be returned.",
    ReturnItemArgs,
)
async def check_return_eligibility(ctx: ToolContext, order_number: str, sku: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    item = (
        await ctx.session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.sku == sku)
        )
    ).scalar_one_or_none()
    if item is None:
        return {"error": "item_not_found_on_order"}

    decision = authorize_return_item(order, item)
    return {"eligible": decision.decision == Decision.ALLOW, "reason": decision.reason}


@register_tool(
    "initiate_return",
    "Start a return for a specific item on one of the customer's own orders, if eligible.",
    InitiateReturnArgs,
    write=True,
)
async def initiate_return(ctx: ToolContext, order_number: str, sku: str, reason: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    item = (
        await ctx.session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.sku == sku)
        )
    ).scalar_one_or_none()
    if item is None:
        return {"error": "item_not_found_on_order"}

    decision = authorize_return_item(order, item)
    if decision.decision != Decision.ALLOW:
        return {"denied": True, "reason": decision.reason}

    # Whole-order status, not per-item - a real system would track return
    # state per line item. Fine for a prototype; see docs/PROGRESS.md.
    order.status = "returned"
    await ctx.session.flush()
    return {"initiated": True, "order_number": order.order_number, "sku": sku}
