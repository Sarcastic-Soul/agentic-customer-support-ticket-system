from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    # Every timestamp in this schema is timestamptz (docs/03-data-model.md).
    # Mapping datetime here once means every `Mapped[datetime]` column gets
    # timezone=True without having to repeat DateTime(timezone=True) on each.
    type_annotation_map = {datetime: DateTime(timezone=True)}


engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
