"""KB debug endpoint: shows dense, sparse and fused results side by side with
scores. Not customer-facing - this is for tuning retrieval and for the demo
screen that explains why the agent answered (or refused to answer) the way
it did.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.models import KBChunk, KBDocument
from app.rag.embed import embed_query
from app.rag.search import dense_hits, hybrid_search, sparse_hits

router = APIRouter(prefix="/api/kb", tags=["kb"])


class SearchRequest(BaseModel):
    query: str


class ScoredChunk(BaseModel):
    chunk_id: int
    document_title: str
    heading_path: str | None
    content: str
    score: float


class SearchResponse(BaseModel):
    dense: list[ScoredChunk]
    sparse: list[ScoredChunk]
    fused: list[ScoredChunk]
    gated_empty: bool  # True if the real hybrid_search() would return nothing


@router.post("/search", response_model=SearchResponse)
async def debug_search(
    body: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    query_vec = embed_query(body.query)
    dense = await dense_hits(session, query_vec, settings.retrieval_top_k_dense)
    sparse = await sparse_hits(session, body.query, settings.retrieval_top_k_sparse)
    fused = await hybrid_search(session, body.query)

    all_ids = {cid for cid, _ in dense} | {cid for cid, _ in sparse} | {c.chunk_id for c in fused}
    rows: dict[int, tuple[KBChunk, str]] = {}
    if all_ids:
        result = await session.execute(
            select(KBChunk, KBDocument.title)
            .join(KBDocument, KBDocument.id == KBChunk.document_id)
            .where(KBChunk.id.in_(all_ids))
        )
        rows = {row[0].id: row for row in result.all()}

    def to_scored(chunk_id: int, score: float) -> ScoredChunk | None:
        row = rows.get(chunk_id)
        if row is None:
            return None
        chunk, title = row
        return ScoredChunk(
            chunk_id=chunk.id,
            document_title=title,
            heading_path=chunk.heading_path,
            content=chunk.content,
            score=score,
        )

    return SearchResponse(
        dense=[scored for cid, s in dense if (scored := to_scored(cid, s))],
        sparse=[scored for cid, s in sparse if (scored := to_scored(cid, s))],
        fused=[
            ScoredChunk(
                chunk_id=c.chunk_id,
                document_title=c.document_title,
                heading_path=c.heading_path,
                content=c.content,
                score=c.fused_score,
            )
            for c in fused
        ],
        gated_empty=len(fused) == 0,
    )
