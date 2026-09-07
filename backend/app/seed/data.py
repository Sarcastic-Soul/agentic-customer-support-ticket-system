"""Synthetic seed data, fixed random seed for reproducible demos.

Edge cases are written first and by hand - per docs/03-data-model.md, they are
what make a demo interesting, not the volume. Everything after the edge-case
block is generated to pad out the numbers.
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

SEED = 20260908
rng = random.Random(SEED)

NOW = datetime(2026, 9, 8, tzinfo=UTC)

FIRST_NAMES = [
    "Aarav", "Vivaan", "Diya", "Ananya", "Ishaan", "Kavya", "Rohan", "Priya",
    "Aditya", "Meera", "Arjun", "Sneha", "Karan", "Pooja", "Nikhil", "Riya",
    "Sanjay", "Anjali", "Vikram", "Neha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Reddy", "Patel", "Singh",
    "Rao", "Das", "Menon", "Kapoor", "Chopra", "Mehta", "Joshi",
]

CARRIERS = ["Delhivery", "BlueDart", "Ekart", "XpressBees"]
CITIES = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Kolkata"]


@dataclass
class SeedCustomer:
    key: str
    full_name: str
    email: str
    phone: str
    tier: str = "standard"
    verified: bool = True


@dataclass
class SeedOrder:
    key: str
    customer_key: str
    status: str
    total_amount: Decimal
    placed_at: datetime
    promised_delivery: date | None = None
    delivered_at: datetime | None = None
    cancellable_until: datetime | None = None
    return_window_ends: date | None = None
    items: list[dict] = field(default_factory=list)
    shipment: dict | None = None
    note: str = ""  # what makes this order interesting - not persisted, just for readability


@dataclass
class SeedTransaction:
    key: str
    order_key: str | None
    customer_key: str
    type: str
    method: str
    amount: Decimal
    status: str
    created_at: datetime
    failure_code: str | None = None
    settled_at: datetime | None = None
    note: str = ""


@dataclass
class SeedRefund:
    transaction_key: str
    amount: Decimal
    reason: str
    status: str
    requested_by_type: str
    expected_credit_by: date | None = None


def _phone(i: int) -> str:
    return f"+9198{i:08d}"


def _name() -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def build_customers(n_extra: int = 90) -> list[SeedCustomer]:
    customers = [
        SeedCustomer("cust_priority_angry", "Rohan Sharma", "rohan.sharma@example.com", _phone(1), tier="priority"),
        SeedCustomer("cust_standard_dupe", "Meera Iyer", "meera.iyer@example.com", _phone(2)),
        SeedCustomer("cust_plus_return", "Vikram Nair", "vikram.nair@example.com", _phone(3), tier="plus"),
        SeedCustomer("cust_unverified", "Unknown Caller", None, _phone(4), verified=False),
        SeedCustomer("cust_repeat", "Ananya Gupta", "ananya.gupta@example.com", _phone(5)),
    ]
    for i in range(n_extra):
        idx = 100 + i
        customers.append(
            SeedCustomer(
                key=f"cust_{idx}",
                full_name=_name(),
                email=f"customer{idx}@example.com",
                phone=_phone(idx),
                tier=rng.choices(["standard", "plus", "priority"], weights=[70, 22, 8])[0],
            )
        )
    return customers


def build_orders() -> list[SeedOrder]:
    """~35 hand-written edge cases first, then generated padding."""
    edge_cases = [
        SeedOrder(
            "ord_delivered_missing", "cust_priority_angry", "delivered",
            Decimal("4200.00"), NOW - timedelta(days=6),
            promised_delivery=(NOW - timedelta(days=2)).date(),
            delivered_at=NOW - timedelta(days=2),
            return_window_ends=(NOW + timedelta(days=5)).date(),
            items=[{"sku": "SKU-EARBUD-01", "name": "Wireless Earbuds", "qty": 1, "unit_price": "4200.00"}],
            shipment={"carrier": "Delhivery", "status": "delivered", "eta": None},
            note="delivered but customer claims it never arrived - priority tier, angry",
        ),
        SeedOrder(
            "ord_stuck_transit", "cust_repeat", "in_transit",
            Decimal("1899.00"), NOW - timedelta(days=9),
            promised_delivery=(NOW - timedelta(days=2)).date(),
            items=[{"sku": "SKU-CABLE-03", "name": "USB-C Cable 2m", "qty": 3, "unit_price": "633.00"}],
            shipment={"carrier": "Ekart", "status": "in_transit", "eta": (NOW - timedelta(days=2)).date()},
            note="stuck past ETA - delivery_issue intent",
        ),
        SeedOrder(
            "ord_cancelled_after_ship", "cust_standard_dupe", "cancelled",
            Decimal("2499.00"), NOW - timedelta(days=4),
            items=[{"sku": "SKU-WATCH-02", "name": "Fitness Band", "qty": 1, "unit_price": "2499.00"}],
            shipment={"carrier": "BlueDart", "status": "cancelled", "eta": None},
            note="cancelled after it had already shipped - should NOT be auto-cancellable now",
        ),
        SeedOrder(
            "ord_dup_charge", "cust_priority_angry", "delivered",
            Decimal("4200.00"), NOW - timedelta(days=6),
            promised_delivery=(NOW - timedelta(days=3)).date(),
            delivered_at=NOW - timedelta(days=3),
            return_window_ends=(NOW + timedelta(days=4)).date(),
            items=[{"sku": "SKU-EARBUD-01", "name": "Wireless Earbuds", "qty": 1, "unit_price": "4200.00"}],
            shipment={"carrier": "Delhivery", "status": "delivered", "eta": None},
            note="charged twice for this order - see ord_dup_charge txns",
        ),
        SeedOrder(
            "ord_partial_return", "cust_plus_return", "delivered",
            Decimal("6300.00"), NOW - timedelta(days=10),
            promised_delivery=(NOW - timedelta(days=6)).date(),
            delivered_at=NOW - timedelta(days=6),
            return_window_ends=(NOW + timedelta(days=1)).date(),
            items=[
                {"sku": "SKU-SHIRT-M", "name": "Cotton Shirt (M)", "qty": 2, "unit_price": "1400.00"},
                {"sku": "SKU-JEANS-32", "name": "Denim Jeans (32)", "qty": 1, "unit_price": "3500.00", "returnable": False},
            ],
            shipment={"carrier": "XpressBees", "status": "delivered", "eta": None},
            note="one item returnable, one not - return window closes tomorrow",
        ),
        SeedOrder(
            "ord_cod_refund", "cust_repeat", "returned",
            Decimal("999.00"), NOW - timedelta(days=20),
            promised_delivery=(NOW - timedelta(days=16)).date(),
            delivered_at=NOW - timedelta(days=16),
            items=[{"sku": "SKU-MUG-01", "name": "Ceramic Mug Set", "qty": 1, "unit_price": "999.00"}],
            shipment={"carrier": "Delhivery", "status": "returned", "eta": None},
            note="COD order, already returned, refund via bank transfer pending",
        ),
        SeedOrder(
            "ord_out_of_window_return", "cust_standard_dupe", "delivered",
            Decimal("1599.00"), NOW - timedelta(days=60),
            promised_delivery=(NOW - timedelta(days=56)).date(),
            delivered_at=NOW - timedelta(days=56),
            return_window_ends=(NOW - timedelta(days=26)).date(),
            items=[{"sku": "SKU-LAMP-01", "name": "Desk Lamp", "qty": 1, "unit_price": "1599.00"}],
            shipment={"carrier": "BlueDart", "status": "delivered", "eta": None},
            note="return window closed a month ago - must escalate/deny, not auto-approve",
        ),
        SeedOrder(
            "ord_cancellable_now", "cust_unverified", "placed",
            Decimal("899.00"), NOW - timedelta(hours=2),
            cancellable_until=NOW + timedelta(hours=22),
            items=[{"sku": "SKU-CASE-01", "name": "Phone Case", "qty": 1, "unit_price": "899.00"}],
            note="placed 2h ago, still within the 24h cancellation window",
        ),
        SeedOrder(
            "ord_out_for_delivery", "cust_repeat", "out_for_delivery",
            Decimal("3200.00"), NOW - timedelta(days=3),
            promised_delivery=NOW.date(),
            items=[{"sku": "SKU-BLENDER-01", "name": "Blender", "qty": 1, "unit_price": "3200.00"}],
            shipment={"carrier": "Ekart", "status": "out_for_delivery", "eta": NOW.date()},
            note="arriving today - order_status happy path",
        ),
        SeedOrder(
            "ord_failed_payment_never_placed", "cust_unverified", "placed",
            Decimal("1299.00"), NOW - timedelta(hours=1),
            cancellable_until=NOW + timedelta(hours=23),
            items=[{"sku": "SKU-BOTTLE-01", "name": "Steel Bottle", "qty": 1, "unit_price": "1299.00"}],
            note="payment failed on this order - see linked failed transaction",
        ),
    ]

    # padding: ordinary orders across every status, spread over 6 months
    statuses = [
        "placed", "confirmed", "packed", "shipped", "in_transit",
        "out_for_delivery", "delivered", "delivered", "delivered", "cancelled",
    ]
    padding: list[SeedOrder] = []
    for i in range(190):
        key = f"ord_pad_{i}"
        customer_key = f"cust_{100 + (i % 90)}"
        status = rng.choice(statuses)
        placed_at = NOW - timedelta(days=rng.randint(1, 180), hours=rng.randint(0, 23))
        amount = Decimal(rng.choice([499, 899, 1299, 1899, 2499, 3499, 4999, 7999]))
        promised = (placed_at + timedelta(days=rng.randint(3, 7))).date()
        delivered_at = placed_at + timedelta(days=rng.randint(3, 6)) if status == "delivered" else None
        padding.append(
            SeedOrder(
                key, customer_key, status, amount, placed_at,
                promised_delivery=promised,
                delivered_at=delivered_at,
                return_window_ends=(delivered_at + timedelta(days=7)).date() if delivered_at else None,
                items=[{"sku": f"SKU-GEN-{i % 20:02d}", "name": "Assorted Item", "qty": 1, "unit_price": str(amount)}],
                shipment=(
                    {"carrier": rng.choice(CARRIERS), "status": status, "eta": promised}
                    if status not in ("placed", "confirmed")
                    else None
                ),
            )
        )
    return edge_cases + padding


def build_transactions(orders: list[SeedOrder]) -> tuple[list[SeedTransaction], list[SeedRefund]]:
    txns: list[SeedTransaction] = []
    refunds: list[SeedRefund] = []

    def _payment_for(order: SeedOrder, key_suffix: str = "") -> SeedTransaction:
        return SeedTransaction(
            f"txn_{order.key}{key_suffix}", order.key, order.customer_key, "payment",
            rng.choice(["card", "upi", "netbanking", "cod"]), order.total_amount,
            "captured", order.placed_at, settled_at=order.placed_at + timedelta(minutes=2),
        )

    for order in orders:
        if order.key == "ord_failed_payment_never_placed":
            txns.append(
                SeedTransaction(
                    "txn_failed_1", order.key, order.customer_key, "payment", "card",
                    order.total_amount, "failed", order.placed_at,
                    failure_code="insufficient_funds", note="failed payment - payment_failed intent",
                )
            )
            continue

        payment = _payment_for(order)
        txns.append(payment)

        if order.key == "ord_dup_charge":
            dup = SeedTransaction(
                "txn_dup_charge_2", order.key, order.customer_key, "payment",
                payment.method, order.total_amount, "captured",
                order.placed_at + timedelta(minutes=4),
                settled_at=order.placed_at + timedelta(minutes=6),
                note="duplicate charge for the same order",
            )
            txns.append(dup)

        if order.key == "ord_cod_refund":
            refund_txn = SeedTransaction(
                "txn_cod_refund", order.key, order.customer_key, "refund",
                "netbanking", order.total_amount, "refund_initiated",
                order.placed_at + timedelta(days=21),
            )
            txns.append(refund_txn)
            refunds.append(
                SeedRefund(
                    "txn_cod_refund", order.total_amount, "product returned, COD order",
                    "processing", "human", expected_credit_by=(NOW + timedelta(days=3)).date(),
                )
            )

        if order.key == "ord_partial_return":
            partial_amount = Decimal("2800.00")
            refund_txn = SeedTransaction(
                "txn_partial_return", order.key, order.customer_key, "refund",
                payment.method, partial_amount, "refund_initiated",
                NOW - timedelta(days=1),
            )
            txns.append(refund_txn)
            refunds.append(
                SeedRefund(
                    "txn_partial_return", partial_amount, "one of two items returned",
                    "requested", "ai", expected_credit_by=(NOW + timedelta(days=5)).date(),
                )
            )

    # padding: a handful of failed and refunded transactions among the generated orders
    padded = [o for o in orders if o.key.startswith("ord_pad_")]
    for order in rng.sample(padded, k=min(30, len(padded))):
        payment = _payment_for(order, "_pad")
        if rng.random() < 0.25:
            payment.status = "failed"
            payment.failure_code = rng.choice(["insufficient_funds", "card_declined", "gateway_timeout"])
        txns.append(payment)

    return txns, refunds


KB_DOCUMENTS = [
    {
        "title": "Refund timelines",
        "source": "policy",
        "category": "refunds",
        "body": (
            "# Refund timelines\n\n"
            "Refunds to the original payment method take 5-7 business days to reflect "
            "once processing starts. Refunds to a bank account (for COD orders) take "
            "7-10 business days. Processing itself starts within 24 hours of approval.\n\n"
            "## Duplicate charges\n\n"
            "If a customer was charged twice for the same order, the duplicate charge is "
            "eligible for a full refund once both transactions are confirmed captured "
            "against the same order."
        ),
    },
    {
        "title": "Refund approval limits",
        "source": "policy",
        "category": "refunds",
        "body": (
            "# Refund approval limits\n\n"
            "Refunds up to and including INR 1000 may be approved automatically when a "
            "matching failed or duplicate captured transaction exists for the same order. "
            "Refunds above INR 1000, or without a matching failed/duplicate transaction, "
            "require human approval. Goodwill refunds (no transaction fault) always "
            "require human approval regardless of amount."
        ),
    },
    {
        "title": "Order cancellation policy",
        "source": "policy",
        "category": "shipping",
        "body": (
            "# Order cancellation policy\n\n"
            "An order can be cancelled free of charge within 24 hours of being placed, "
            "and only while it is still in 'placed' or 'confirmed' status. Once an order "
            "has shipped, it can no longer be cancelled - the customer should use the "
            "return process after delivery instead."
        ),
    },
    {
        "title": "Return window",
        "source": "policy",
        "category": "refunds",
        "body": (
            "# Return window\n\n"
            "Most items can be returned within 7 days of delivery. Some items are marked "
            "non-returnable at checkout (for example innerwear, and jeans purchased in a "
            "final-sale bundle) and cannot be returned regardless of the window. Requests "
            "made after the return window has closed are not eligible for automatic "
            "approval and should be escalated for a case-by-case decision."
        ),
    },
    {
        "title": "Delayed delivery",
        "source": "faq",
        "category": "shipping",
        "body": (
            "# My order hasn't arrived by the promised date\n\n"
            "Delivery delays of 1-2 days beyond the promised date can happen due to "
            "carrier volume, especially around holidays. If a shipment shows no scan "
            "activity for more than 3 days, or is more than 5 days past its promised "
            "delivery date, treat it as a delivery issue requiring escalation rather than "
            "a routine delay."
        ),
    },
    {
        "title": "Payment failure reasons",
        "source": "faq",
        "category": "payments",
        "body": (
            "# Why did my payment fail?\n\n"
            "Common reasons: insufficient funds, the bank declined the card, or a "
            "temporary gateway timeout. In all three cases no money was deducted - a "
            "failed transaction never reaches the captured state, so nothing needs to be "
            "refunded. The customer can simply retry the payment."
        ),
    },
    {
        "title": "Warranty coverage",
        "source": "policy",
        "category": "product",
        "body": (
            "# Warranty coverage\n\n"
            "Electronics carry a 12-month manufacturer warranty against defects, "
            "excluding physical damage, water damage, and unauthorized repairs. "
            "Warranty claims are handled by the manufacturer directly; the support team "
            "can help the customer locate the manufacturer's service center but cannot "
            "process warranty repairs or replacements itself."
        ),
    },
    {
        "title": "Changing a delivery address",
        "source": "faq",
        "category": "account",
        "body": (
            "# Can I change my delivery address after placing an order?\n\n"
            "The delivery address can only be changed while the order is still in "
            "'placed' status. Once an order is packed or shipped, the address cannot be "
            "changed through support and the customer needs to coordinate directly with "
            "the courier, or wait for delivery and arrange a return."
        ),
    },
]
