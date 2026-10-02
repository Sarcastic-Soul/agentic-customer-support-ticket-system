"""Cross-encoder reranking over the fused hybrid-search candidates.

RRF only knows *rank positions* from two retrievers that each looked at the
query on its own terms. A cross-encoder reads the query and each chunk
together, which is much better at telling "the cancellation policy" from "a
chunk that happens to mention cancelling". flashrank runs a small ONNX model
(ms-marco-TinyBERT-L-2-v2, ~4MB) on the CPU in a few milliseconds per chunk -
no GPU, no API key, no quota. See docs/decisions/0008-upgrades.md.

The model is loaded once per process. If it can't load (no network on first
run to fetch the weights, say), reranking is switched off for the process and
retrieval falls back to RRF order - a worse ranking beats a failed request.
"""

import os
from functools import lru_cache

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

_disabled = False


@lru_cache(maxsize=1)
def _ranker():
    from flashrank import Ranker

    # flashrank's default cache is /tmp, which a reboot wipes
    return Ranker(
        model_name=settings.reranker_model, cache_dir=os.path.expanduser("~/.cache/flashrank")
    )


def rerank(
    query: str, passages: list[tuple[int, str]], top_k: int
) -> list[tuple[int, float]] | None:
    """`passages` are (chunk_id, text). Returns the top_k as (chunk_id,
    score), best first, or None if reranking is unavailable - the caller
    keeps its own order then.
    """
    global _disabled
    if (
        not settings.reranker_enabled
        or settings.eval_ablation == "no_rerank"
        or _disabled
        or not passages
    ):
        return None
    try:
        from flashrank import RerankRequest

        results = _ranker().rerank(
            RerankRequest(query=query, passages=[{"id": cid, "text": t} for cid, t in passages])
        )
    except Exception:
        logger.exception("reranker_unavailable_falling_back_to_rrf")
        _disabled = True
        return None
    return [(int(r["id"]), float(r["score"])) for r in results[:top_k]]
