"""RAG ingestion: chunk every active kb_document and embed the chunks into
kb_chunks. Re-runnable - each document's existing chunks are replaced, so
editing a KB article and re-ingesting is just running this again.

Usage: python -m app.rag.ingest
"""

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.logging import configure_logging, get_logger
from app.models import KBChunk, KBDocument
from app.rag.chunk import chunk_markdown
from app.rag.embed import embed_texts

logger = get_logger(__name__)


async def ingest_document(session: AsyncSession, document: KBDocument) -> int:
    await session.execute(delete(KBChunk).where(KBChunk.document_id == document.id))

    chunks = chunk_markdown(document.body)
    if not chunks:
        return 0

    embeddings = embed_texts([c.content for c in chunks])
    for ordinal, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        session.add(
            KBChunk(
                document_id=document.id,
                ordinal=ordinal,
                heading_path=chunk.heading_path,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding=embedding,
            )
        )
    return len(chunks)


async def ingest_all(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(select(KBDocument).where(KBDocument.is_active))
    documents = result.scalars().all()

    total_chunks = 0
    for document in documents:
        total_chunks += await ingest_document(session, document)

    await session.commit()
    return {"documents": len(documents), "chunks": total_chunks}


async def main() -> None:
    configure_logging()
    async with async_session_factory() as session:
        stats = await ingest_all(session)
    logger.info("rag_ingest_complete", **stats)


if __name__ == "__main__":
    asyncio.run(main())
