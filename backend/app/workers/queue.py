"""arq job queue setup. Kept behind this thin module so swapping to another
async queue later is a matter of changing what's here, not every call site.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_pool() -> ArqRedis:
    return await create_pool(_redis_settings())


async def enqueue_handle_message(message_id: int) -> None:
    pool = await get_pool()
    try:
        await pool.enqueue_job("handle_message", message_id)
    finally:
        await pool.aclose()
