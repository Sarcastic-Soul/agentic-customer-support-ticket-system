import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.agent.graph as agent_graph
import app.channels.registry as channel_registry
from app.agent.checkpoint import close_checkpointer
from app.db.session import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    """pytest-asyncio gives each test its own event loop, but connection
    pools (and the asyncio.Lock/Future objects inside them) are bound to
    whichever loop created them. Tear every process-level cache down after
    every test - not just ones using the `session` fixture, e.g.
    test_health.py connects directly - so the next test opens fresh
    connections on its own loop instead of reusing ones tied to a closed
    loop:
      - app.db.session.engine (asyncpg, via SQLAlchemy)
      - app.agent.checkpoint's psycopg pool (AsyncPostgresSaver) - its
        internal asyncio.Lock is what actually breaks cross-loop; the
        RuntimeError only surfaces on the *second* test that touches the
        graph, which is what made this one take two escalation tests to find
      - app.agent.graph's cached CompiledStateGraph - it holds a reference to
        whichever checkpointer it was compiled with, so closing the
        checkpointer above is not enough on its own; the cached graph must
        be dropped too or get_graph() hands back a graph pointing at a pool
        that no longer exists
      - app.channels.registry's cached adapters (WebAdapter holds a Redis
        client)
    """
    yield
    await engine.dispose()
    await close_checkpointer()
    agent_graph._graph = None
    channel_registry._ADAPTERS.clear()


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
