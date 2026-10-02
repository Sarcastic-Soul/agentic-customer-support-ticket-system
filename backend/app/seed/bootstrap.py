"""First-boot setup for the Docker stack (the `setup` service in
docker-compose.yml): seed and ingest only when the database has no customers
yet. Restarting the stack keeps whatever data is already there; `make seed`
(or `docker compose run --rm setup python -m app.seed.run`) still forces a
full reset.

Usage: python -m app.seed.bootstrap
"""

import asyncio

from sqlalchemy import func, select

from app.db.session import async_session_factory
from app.logging import configure_logging, get_logger
from app.models import Customer
from app.rag.ingest import main as ingest
from app.seed.run import seed

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()
    async with async_session_factory() as session:
        customers = (await session.execute(select(func.count()).select_from(Customer))).scalar()
    if customers:
        logger.info("bootstrap_skipped", customers=customers)
        return
    await seed()
    await ingest()


if __name__ == "__main__":
    asyncio.run(main())
