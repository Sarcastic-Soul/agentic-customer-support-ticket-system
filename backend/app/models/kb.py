from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.config import settings
from app.db.session import Base


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    source: Mapped[str]  # faq | policy | macro | manual
    category: Mapped[str | None]  # shipping | refunds | payments | account | product
    body: Mapped[str] = mapped_column(Text)  # markdown
    version: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("human_agents.id"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    chunks: Mapped[list["KBChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index(
            "kb_chunks_vec_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("kb_chunks_tsv_idx", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    heading_path: Mapped[str | None]  # 'Refunds > Timelines'
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )

    document: Mapped[KBDocument] = relationship(back_populates="chunks")


__all__ = ["KBDocument", "KBChunk"]
