"""Action authorization, enforced in code inside the tool wrapper - never in
a prompt. The model can request a refund; it cannot approve one above the
ceiling. See CLAUDE.md non-negotiable #3.

Thresholds come from Settings (app/config.py), not a separate constants
file - one source of truth for tunable numbers, matching how the rest of
the app reads config.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.models import Order, OrderItem, Shipment


class Decision(Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN = "require_human"
    DENY = "deny"


@dataclass(frozen=True)
class AuthResult:
    decision: Decision
    reason: str


def authorize_cancel_order(order: "Order") -> AuthResult:
    if order.status not in ("placed", "confirmed"):
        return AuthResult(
            Decision.DENY,
            f"order status is {order.status!r} - already shipped or beyond, "
            "cancellation is no longer possible through support",
        )
    now = datetime.now(UTC)
    if order.cancellable_until is None or now > order.cancellable_until:
        return AuthResult(Decision.DENY, "the 24-hour cancellation window has passed")
    return AuthResult(Decision.ALLOW, "within the cancellation window and not yet shipped")


def authorize_return_item(order: "Order", item: "OrderItem") -> AuthResult:
    if not item.returnable:
        return AuthResult(Decision.DENY, "this item is marked non-returnable")
    if order.return_window_ends is None or datetime.now(UTC).date() > order.return_window_ends:
        return AuthResult(Decision.DENY, "the return window for this order has closed")
    return AuthResult(Decision.ALLOW, "within the return window and the item is returnable")


def authorize_refund(amount: Decimal, has_matching_failed_or_duplicate_txn: bool) -> AuthResult:
    ceiling = Decimal(str(settings.auto_refund_ceiling))
    if amount > ceiling:
        return AuthResult(
            Decision.REQUIRE_HUMAN,
            f"refund amount {amount} exceeds the auto-approval ceiling of {ceiling}",
        )
    if not has_matching_failed_or_duplicate_txn:
        return AuthResult(
            Decision.REQUIRE_HUMAN,
            "no matching failed or duplicate transaction found for this order - "
            "goodwill refunds always require human approval",
        )
    return AuthResult(
        Decision.ALLOW,
        f"amount within the {ceiling} auto-approval ceiling and a matching "
        "failed/duplicate transaction exists",
    )


def authorize_carrier_investigation(order: "Order", shipment: "Shipment | None") -> AuthResult:
    """A lost-parcel investigation is the AI's way of handling "tracking says
    delivered but I never got it" or "stuck for days" without a human - but
    only once the waiting period in the knowledge base has passed. Timing is
    read from the order and shipment rows, never judged by the model.
    """
    if shipment is None:
        return AuthResult(Decision.DENY, "the order has not shipped yet")
    now = datetime.now(UTC)
    if shipment.status == "delivered" or order.status == "delivered":
        if order.delivered_at is None:
            return AuthResult(Decision.DENY, "no delivery time recorded for this order")
        wait = timedelta(hours=settings.investigation_wait_hours)
        if now - order.delivered_at < wait:
            return AuthResult(
                Decision.DENY,
                f"it has been under {settings.investigation_wait_hours} hours since the "
                "delivery scan - parcels are often with a neighbour or building security",
            )
        return AuthResult(Decision.ALLOW, "marked delivered over 24 hours ago and not received")
    if shipment.status in ("shipped", "in_transit", "out_for_delivery", "packed"):
        if order.promised_delivery is None:
            return AuthResult(Decision.DENY, "no promised delivery date to measure a delay against")
        late_by = (now.date() - order.promised_delivery).days
        if late_by <= settings.investigation_stuck_days:
            return AuthResult(
                Decision.DENY,
                f"only {max(late_by, 0)} day(s) past the promised date - delays up to "
                f"{settings.investigation_stuck_days} days are normal",
            )
        return AuthResult(Decision.ALLOW, f"{late_by} days past the promised delivery date")
    return AuthResult(
        Decision.DENY, f"shipment status is {shipment.status!r}, nothing to investigate"
    )
