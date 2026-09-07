from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(unique=True)  # 'ORD-10432'
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    # placed|confirmed|packed|shipped|in_transit|out_for_delivery|delivered|cancelled|returned
    status: Mapped[str]
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(default="INR")
    placed_at: Mapped[datetime]
    promised_delivery: Mapped[date | None]
    delivered_at: Mapped[datetime | None]
    cancellable_until: Mapped[datetime | None]  # policy input, NOT an LLM judgement
    return_window_ends: Mapped[date | None]  # policy input, NOT an LLM judgement
    shipping_address: Mapped[dict] = mapped_column(JSONB)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="order")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    sku: Mapped[str]
    name: Mapped[str]
    qty: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    returnable: Mapped[bool] = mapped_column(default=True)

    order: Mapped[Order] = relationship(back_populates="items")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    carrier: Mapped[str]
    tracking_no: Mapped[str]
    status: Mapped[str]
    last_scan_at: Mapped[datetime | None]
    last_location: Mapped[str | None]
    eta: Mapped[date | None]
    events: Mapped[list] = mapped_column(JSONB, default=list)  # scan history

    order: Mapped[Order] = relationship(back_populates="shipments")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_ref: Mapped[str] = mapped_column(unique=True)  # 'TXN-88213'
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    type: Mapped[str]  # payment | refund | chargeback | adjustment
    method: Mapped[str]  # card | upi | netbanking | wallet | cod
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(default="INR")
    status: Mapped[str]  # pending|authorized|captured|failed|refund_initiated|refunded|reversed
    gateway_ref: Mapped[str | None]
    failure_code: Mapped[str | None]
    created_at: Mapped[datetime]
    settled_at: Mapped[datetime | None]

    order: Mapped[Order | None] = relationship(back_populates="transactions")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="transaction")


class Refund(Base):
    """Separate from transactions: a refund has an approval lifecycle a payment
    does not, and that lifecycle - AI requests, policy denies, human approves,
    processed - is the most demo-critical write path in the system.
    """

    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str]  # requested | approved | rejected | processing | completed
    requested_by_type: Mapped[str]  # ai | human
    requested_by_id: Mapped[str | None]
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("human_agents.id"))
    expected_credit_by: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    transaction: Mapped[Transaction] = relationship(back_populates="refunds")


__all__ = ["Order", "OrderItem", "Shipment", "Transaction", "Refund"]
