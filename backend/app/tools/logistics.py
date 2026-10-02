from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Shipment
from app.policy.authorize import Decision, authorize_carrier_investigation
from app.tools.context import ToolContext
from app.tools.orders import OrderNumberArgs, get_order_scoped
from app.tools.registry import register_tool

INVESTIGATION_EVENT = "investigation_opened"


class InvestigationArgs(OrderNumberArgs):
    reason: str


@register_tool(
    "open_carrier_investigation",
    "Open a lost-parcel investigation with the carrier for one of the customer's "
    "own orders - for a parcel marked delivered but not received, or one stuck "
    "well past its promised date. Denied if the waiting period hasn't passed yet.",
    InvestigationArgs,
    write=True,
)
async def open_carrier_investigation(ctx: ToolContext, order_number: str, reason: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    shipment = (
        await ctx.session.execute(select(Shipment).where(Shipment.order_id == order.id))
    ).scalar_one_or_none()

    events = list(shipment.events or []) if shipment else []
    already = next((e for e in events if e.get("type") == INVESTIGATION_EVENT), None)
    if already is not None:
        return {
            "already_open": True, "order_number": order_number,
            "opened_at": already.get("at"),
            "note": "the carrier replies within 5 business days of opening",
        }

    decision = authorize_carrier_investigation(order, shipment)
    if decision.decision != Decision.ALLOW:
        return {"denied": True, "order_number": order_number, "reason": decision.reason}

    if ctx.propose_only:
        return {
            "proposed": True, "order_number": order_number,
            "would": "open a carrier investigation",
        }

    now = datetime.now(UTC).isoformat()
    # scan history is JSONB - reassign, don't mutate in place, or SQLAlchemy
    # won't see the change
    shipment.events = [*events, {"type": INVESTIGATION_EVENT, "at": now, "reason": reason}]
    await ctx.session.flush()
    return {
        "opened": True, "order_number": order_number, "carrier": shipment.carrier,
        "tracking_no": shipment.tracking_no,
        "next_step": (
            "the carrier replies within 5 business days; then a replacement or full refund"
        ),
    }
