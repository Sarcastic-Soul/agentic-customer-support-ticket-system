"""Identity resolution: mapping a channel-specific external id to a customer.

A phone number or email address is not a customer id. Every inbound message
goes through this before anything else touches it.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, CustomerIdentity


async def resolve_customer(
    session: AsyncSession, *, channel: str, external_id: str
) -> tuple[Customer, bool]:
    """Return (customer, created). Creates an unverified customer on first
    contact from a new (channel, external_id) pair rather than rejecting it -
    a prototype default; account-specific tools still require verification.
    """
    result = await session.execute(
        select(CustomerIdentity).where(
            CustomerIdentity.channel == channel, CustomerIdentity.external_id == external_id
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        customer = await session.get(Customer, identity.customer_id)
        assert customer is not None
        return customer, False

    customer = Customer(verified=False)
    session.add(customer)
    await session.flush()

    session.add(CustomerIdentity(customer_id=customer.id, channel=channel, external_id=external_id))
    return customer, True
