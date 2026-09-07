"""Action authorization, enforced in code inside the tool wrapper - never in
a prompt. The model can request a refund; it cannot approve one above the
ceiling. See CLAUDE.md non-negotiable #3.

Thresholds come from Settings (app/config.py), not a separate constants
file - one source of truth for tunable numbers, matching how the rest of
the app reads config.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.models import Order, OrderItem


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
