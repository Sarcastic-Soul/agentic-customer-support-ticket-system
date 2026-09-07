"""Seed the database with synthetic customers, orders, transactions and KB
documents. Fixed random seed (see app.seed.data) so demos are reproducible.

Idempotent: truncates the tables it owns first, so `make seed` can be re-run
freely. Does not touch kb_chunks/embeddings - that's the RAG ingestion step
(Stage 3), which chunks and embeds whatever is in kb_documents.

Usage: python -m app.seed.run
"""

import asyncio

from argon2 import PasswordHasher
from sqlalchemy import text

from app.db.session import async_session_factory
from app.logging import configure_logging, get_logger
from app.models import (
    Customer,
    CustomerIdentity,
    HumanAgent,
    KBDocument,
    Order,
    OrderItem,
    Refund,
    Shipment,
    Transaction,
)
from app.seed.data import KB_DOCUMENTS, build_customers, build_orders, build_transactions

configure_logging()
logger = get_logger(__name__)

HUMAN_AGENTS = [
    {
        "email": "priya.agent@example.com", "full_name": "Priya Nataraj",
        "role": "admin", "skills": ["refunds", "orders", "billing"],
    },
    {
        "email": "arjun.agent@example.com", "full_name": "Arjun Mehta",
        "role": "agent", "skills": ["orders", "shipping"],
    },
    {
        "email": "sneha.agent@example.com", "full_name": "Sneha Kapoor",
        "role": "agent", "skills": ["refunds", "billing"],
    },
    {
        "email": "vikas.agent@example.com", "full_name": "Vikas Rao",
        "role": "agent", "skills": ["orders"],
    },
]

TRUNCATE_TABLES = [
    "tool_calls", "agent_steps", "agent_runs",
    "escalations", "ticket_events", "tickets",
    "messages", "raw_events", "conversations",
    "refunds", "transactions", "order_items", "shipments", "orders",
    "customer_identities", "customers",
    "kb_chunks", "kb_documents",
    "human_agents",
]


async def _truncate_all(session) -> None:
    tables = ", ".join(TRUNCATE_TABLES)
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def seed() -> None:
    ph = PasswordHasher()

    async with async_session_factory() as session:
        await _truncate_all(session)

        for agent in HUMAN_AGENTS:
            session.add(HumanAgent(password_hash=ph.hash("dev-password"), **agent))

        for doc in KB_DOCUMENTS:
            session.add(KBDocument(**doc))

        seed_customers = build_customers()
        customer_rows: dict[str, Customer] = {}
        for sc in seed_customers:
            customer = Customer(
                full_name=sc.full_name, email=sc.email, phone=sc.phone,
                tier=sc.tier, verified=sc.verified,
            )
            session.add(customer)
            customer_rows[sc.key] = customer
        await session.flush()

        for sc in seed_customers:
            customer = customer_rows[sc.key]
            session.add(
                CustomerIdentity(customer_id=customer.id, channel="whatsapp", external_id=sc.phone)
            )
            if sc.email:
                session.add(
                    CustomerIdentity(customer_id=customer.id, channel="email", external_id=sc.email)
                )

        seed_orders = build_orders()
        order_rows: dict[str, Order] = {}
        for so in seed_orders:
            customer = customer_rows[so.customer_key]
            order = Order(
                order_number=f"ORD-{10000 + len(order_rows)}",
                customer_id=customer.id,
                status=so.status,
                total_amount=so.total_amount,
                placed_at=so.placed_at,
                promised_delivery=so.promised_delivery,
                delivered_at=so.delivered_at,
                cancellable_until=so.cancellable_until,
                return_window_ends=so.return_window_ends,
                shipping_address={
                    "line1": "123 MG Road", "city": "Bengaluru",
                    "postal_code": "560001", "country": "IN",
                },
            )
            session.add(order)
            order_rows[so.key] = order
            await session.flush()

            for item in so.items:
                session.add(
                    OrderItem(
                        order_id=order.id, sku=item["sku"], name=item["name"],
                        qty=item["qty"], unit_price=item["unit_price"],
                        returnable=item.get("returnable", True),
                    )
                )
            if so.shipment:
                session.add(
                    Shipment(
                        order_id=order.id, carrier=so.shipment["carrier"],
                        tracking_no=f"TRK{order.id:08d}", status=so.shipment["status"],
                        eta=so.shipment.get("eta"), events=[],
                    )
                )

        seed_txns, seed_refunds = build_transactions(seed_orders)
        txn_rows: dict[str, Transaction] = {}
        for st in seed_txns:
            order = order_rows.get(st.order_key) if st.order_key else None
            customer = customer_rows[st.customer_key]
            txn = Transaction(
                txn_ref=f"TXN-{80000 + len(txn_rows)}",
                order_id=order.id if order else None,
                customer_id=customer.id,
                type=st.type, method=st.method, amount=st.amount,
                status=st.status, failure_code=st.failure_code,
                created_at=st.created_at, settled_at=st.settled_at,
            )
            session.add(txn)
            txn_rows[st.key] = txn
        await session.flush()

        for sr in seed_refunds:
            txn = txn_rows[sr.transaction_key]
            session.add(
                Refund(
                    transaction_id=txn.id, amount=sr.amount, reason=sr.reason,
                    status=sr.status, requested_by_type=sr.requested_by_type,
                    expected_credit_by=sr.expected_credit_by,
                )
            )

        await session.commit()

    logger.info(
        "seed_complete",
        customers=len(seed_customers),
        orders=len(seed_orders),
        transactions=len(seed_txns),
        refunds=len(seed_refunds),
        kb_documents=len(KB_DOCUMENTS),
        human_agents=len(HUMAN_AGENTS),
    )


if __name__ == "__main__":
    asyncio.run(seed())
