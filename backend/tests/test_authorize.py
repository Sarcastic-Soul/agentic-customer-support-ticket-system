"""authorize() decision table - pure functions, no DB needed. This is the
one place a refund or cancellation is actually approved or denied; the LLM
never gets to override it.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.policy.authorize import (
    Decision,
    authorize_cancel_order,
    authorize_carrier_investigation,
    authorize_refund,
    authorize_return_item,
)


class FakeOrder:
    def __init__(self, *, status, cancellable_until=None, return_window_ends=None):
        self.status = status
        self.cancellable_until = cancellable_until
        self.return_window_ends = return_window_ends


class FakeItem:
    def __init__(self, *, returnable):
        self.returnable = returnable


def test_cancel_allowed_within_window_and_not_shipped():
    order = FakeOrder(status="placed", cancellable_until=datetime.now(UTC) + timedelta(hours=1))
    result = authorize_cancel_order(order)
    assert result.decision == Decision.ALLOW


def test_cancel_denied_after_window_passed():
    order = FakeOrder(status="placed", cancellable_until=datetime.now(UTC) - timedelta(hours=1))
    result = authorize_cancel_order(order)
    assert result.decision == Decision.DENY
    assert "window" in result.reason


def test_cancel_denied_once_shipped():
    order = FakeOrder(status="shipped", cancellable_until=datetime.now(UTC) + timedelta(hours=1))
    result = authorize_cancel_order(order)
    assert result.decision == Decision.DENY
    assert "shipped" in result.reason


def test_return_denied_for_non_returnable_item():
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    order = FakeOrder(status="delivered", return_window_ends=tomorrow)
    item = FakeItem(returnable=False)
    result = authorize_return_item(order, item)
    assert result.decision == Decision.DENY
    assert "non-returnable" in result.reason


def test_return_denied_after_window_closed():
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    order = FakeOrder(status="delivered", return_window_ends=yesterday)
    item = FakeItem(returnable=True)
    result = authorize_return_item(order, item)
    assert result.decision == Decision.DENY
    assert "window" in result.reason


def test_return_allowed_within_window_and_returnable():
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    order = FakeOrder(status="delivered", return_window_ends=tomorrow)
    item = FakeItem(returnable=True)
    result = authorize_return_item(order, item)
    assert result.decision == Decision.ALLOW


def test_refund_allowed_within_ceiling_with_matching_fault():
    result = authorize_refund(Decimal("500.00"), has_matching_failed_or_duplicate_txn=True)
    assert result.decision == Decision.ALLOW


def test_refund_requires_human_above_ceiling():
    result = authorize_refund(Decimal("5000.00"), has_matching_failed_or_duplicate_txn=True)
    assert result.decision == Decision.REQUIRE_HUMAN
    assert "exceeds" in result.reason


def test_refund_requires_human_without_matching_fault():
    result = authorize_refund(Decimal("100.00"), has_matching_failed_or_duplicate_txn=False)
    assert result.decision == Decision.REQUIRE_HUMAN
    assert "matching" in result.reason


def test_refund_at_exact_ceiling_is_allowed():
    from app.config import settings

    ceiling = Decimal(str(settings.auto_refund_ceiling))
    result = authorize_refund(ceiling, has_matching_failed_or_duplicate_txn=True)
    assert result.decision == Decision.ALLOW


class FakeParcelOrder:
    def __init__(self, *, status, delivered_at=None, promised_delivery=None):
        self.status = status
        self.delivered_at = delivered_at
        self.promised_delivery = promised_delivery


class FakeShipment:
    def __init__(self, status):
        self.status = status


def test_investigation_denied_within_24h_of_delivery_scan():
    order = FakeParcelOrder(status="delivered", delivered_at=datetime.now(UTC) - timedelta(hours=3))
    result = authorize_carrier_investigation(order, FakeShipment("delivered"))
    assert result.decision == Decision.DENY
    assert "neighbour" in result.reason


def test_investigation_allowed_after_24h_not_received():
    order = FakeParcelOrder(status="delivered", delivered_at=datetime.now(UTC) - timedelta(days=2))
    result = authorize_carrier_investigation(order, FakeShipment("delivered"))
    assert result.decision == Decision.ALLOW


def test_investigation_denied_for_normal_delay():
    promised = (datetime.now(UTC) - timedelta(days=1)).date()
    order = FakeParcelOrder(status="shipped", promised_delivery=promised)
    result = authorize_carrier_investigation(order, FakeShipment("in_transit"))
    assert result.decision == Decision.DENY


def test_investigation_allowed_when_stuck_past_promised_date():
    promised = (datetime.now(UTC) - timedelta(days=6)).date()
    order = FakeParcelOrder(status="shipped", promised_delivery=promised)
    result = authorize_carrier_investigation(order, FakeShipment("in_transit"))
    assert result.decision == Decision.ALLOW


def test_investigation_denied_before_shipping():
    order = FakeParcelOrder(status="placed")
    assert authorize_carrier_investigation(order, None).decision == Decision.DENY
