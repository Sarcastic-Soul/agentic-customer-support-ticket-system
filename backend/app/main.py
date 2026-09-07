from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from sqlalchemy import text

from app.api.dev import router as dev_router
from app.config import settings
from app.db.session import engine
from app.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", env=settings.env)
    yield
    await engine.dispose()
    logger.info("shutdown")


app = FastAPI(title="AI Customer Support", lifespan=lifespan)
app.include_router(dev_router)


@app.get("/health")
async def health() -> dict:
    checks = {"db": False, "redis": False}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception as exc:
        logger.warning("health_check_db_failed", error=str(exc))

    try:
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        checks["redis"] = True
    except Exception as exc:
        logger.warning("health_check_redis_failed", error=str(exc))

    ok = all(checks.values())
    return {"status": "ok" if ok else "degraded", "checks": checks}
