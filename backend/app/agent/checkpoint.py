"""LangGraph's Postgres checkpointer: a separate psycopg 3 pool against the
same database the app's asyncpg engine already uses (see
CLAUDE.md "two Postgres pools, one database" and
docs/decisions/0003-prototype-scope.md). This is what makes escalation's
pause-and-resume (Stage 6) possible - the graph's state is durable, not
in-memory.

IMPORTANT: this module must be imported (directly or transitively) before any
other module imports langgraph, so `app.config`'s load_dotenv() has already
put LANGGRAPH_STRICT_MSGPACK into the process environment - langgraph reads
it via a plain os.getenv() at import time, not through our Settings object.
That is why `from app.config import settings` is the first import below.
"""

from app.config import settings  # noqa: F401 - import order matters, see docstring

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402
from psycopg_pool import AsyncConnectionPool  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Lazily creates the pool and saver on first use, and runs .setup() once
    (idempotent - creates the checkpoint tables if they don't exist yet).
    """
    global _pool, _saver
    if _saver is not None:
        return _saver

    _pool = AsyncConnectionPool(
        conninfo=settings.checkpoint_database_url,
        max_size=settings.checkpoint_pool_size,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await _pool.open()
    _saver = AsyncPostgresSaver(_pool)
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool = None
    _saver = None
