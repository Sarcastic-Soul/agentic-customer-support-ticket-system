from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from sqlalchemy import text

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.console import router as console_router
from app.api.dev import router as dev_router
from app.api.kb import router as kb_router
from app.config import settings
from app.db.session import engine
from app.ingress.voice import router as voice_router
from app.ingress.web import router as web_ws_router
from app.ingress.whatsapp import router as whatsapp_router
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
app.include_router(web_ws_router)
app.include_router(whatsapp_router)
app.include_router(voice_router)
app.include_router(kb_router)
app.include_router(console_router)
app.include_router(auth_router)
app.include_router(admin_router)


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
