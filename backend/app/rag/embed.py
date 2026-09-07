"""Local embeddings via fastembed - CPU, ONNX, no API key, no rate limit.
Model downloads once to a local cache on first use, then runs fully offline.
"""

from functools import lru_cache

from fastembed import TextEmbedding

from app.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vec.tolist() for vec in get_embedder().embed(texts)]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
