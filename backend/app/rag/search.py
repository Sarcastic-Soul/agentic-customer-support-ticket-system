"""Hybrid retrieval: dense (pgvector cosine) + sparse (Postgres full-text),
fused with Reciprocal Rank Fusion. Dense finds paraphrases; sparse finds
order numbers, SKUs and error codes, which dense embeddings are reliably bad
at. The gate on the *best* score returning nothing rather than a bad guess is
the single most important line in this module - see docs/03/04/09.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import KBChunk, KBDocument
from app.rag.embed import embed_query

RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    document_title: str
    heading_path: str | None
    content: str
    dense_score: float | None  # cosine similarity, 0..1 (higher is better)
    sparse_score: float | None  # ts_rank, unbounded (higher is better)
    fused_score: float


async def dense_hits(
    session: AsyncSession, query_vec: list[float], k: int
) -> list[tuple[int, float]]:
    distance = KBChunk.embedding.cosine_distance(query_vec)
    result = await session.execute(
        select(KBChunk.id, distance.label("distance")).order_by(distance).limit(k)
    )
    # cosine_distance = 1 - cosine_similarity
    return [(chunk_id, 1 - dist) for chunk_id, dist in result.all()]


async def sparse_hits(session: AsyncSession, query: str, k: int) -> list[tuple[int, float]]:
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(KBChunk.tsv, tsquery)
    result = await session.execute(
        select(KBChunk.id, rank.label("rank"))
        .where(KBChunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(k)
    )
    return [(chunk_id, r) for chunk_id, r in result.all()]


def _rrf_fuse(
    dense: list[tuple[int, float]], sparse: list[tuple[int, float]]
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for rank, (chunk_id, _) in enumerate(dense, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank)
    for rank, (chunk_id, _) in enumerate(sparse, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank)
    return scores


async def hybrid_search(
    session: AsyncSession,
    query: str,
    *,
    k: int | None = None,
) -> list[RetrievedChunk]:
    """Returns [] if the best dense match is below RETRIEVAL_SCORE_MIN and
    nothing matched the sparse (keyword) search either - the system must not
    answer from parametric memory when the knowledge base doesn't cover it.
    """
    final_k = k or settings.retrieval_final_k
    query_vec = embed_query(query)

    dense = await dense_hits(session, query_vec, settings.retrieval_top_k_dense)
    # Stage 11 "dense-only retrieval" ablation: no tsvector search at all.
    sparse = (
        []
        if settings.eval_ablation == "dense_only"
        else await sparse_hits(session, query, settings.retrieval_top_k_sparse)
    )

    best_dense = dense[0][1] if dense else 0.0
    if best_dense < settings.retrieval_score_min and not sparse:
        return []

    fused_scores = _rrf_fuse(dense, sparse)
    dense_by_id = dict(dense)
    sparse_by_id = dict(sparse)

    top_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)[:final_k]
    if not top_ids:
        return []

    result = await session.execute(
        select(KBChunk, KBDocument.title)
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBChunk.id.in_(top_ids))
    )
    chunks_by_id = {row[0].id: row for row in result.all()}

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            heading_path=chunk.heading_path,
            content=chunk.content,
            dense_score=dense_by_id.get(chunk_id),
            sparse_score=sparse_by_id.get(chunk_id),
            fused_score=fused_scores[chunk_id],
        )
        for chunk_id in top_ids
        for chunk, title in [chunks_by_id[chunk_id]]
    ]
