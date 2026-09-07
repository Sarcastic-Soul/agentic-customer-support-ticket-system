import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    """pytest-asyncio gives each test its own event loop, but the engine's
    asyncpg connections are bound to whichever loop created them. Dispose the
    pool after every test (not just ones using the `session` fixture, e.g.
    test_health.py connects directly) so the next test opens a fresh
    connection on its own loop instead of reusing one tied to a closed loop.
    """
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def session():
    """One connection per test, wrapped in a transaction that's rolled back at
    the end. Runs against the real dev database rather than a dedicated test
    database or testcontainers - a deliberate prototype simplification (see
    docs/decisions/0003-prototype-scope.md). Tests never see each other's data
    because nothing is ever committed.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
