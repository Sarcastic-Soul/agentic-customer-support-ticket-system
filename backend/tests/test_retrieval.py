"""~20 hand-written retrieval queries against the seeded KB, per Stage 3's
definition of done: recall@5 around 0.85, and out-of-scope queries return
nothing rather than a low-relevance chunk. Requires the KB to be ingested
(`python -m app.rag.ingest`) - run against the seeded dev database, same as
the rest of the test suite (see docs/decisions/0003-prototype-scope.md).
"""

import pytest

from app.rag.search import hybrid_search

# (query, expected document title substring)
ON_TOPIC_QUERIES = [
    ("how long does a refund take", "Refund timelines"),
    ("when will my refund arrive", "Refund timelines"),
    ("I was charged twice for the same order", "Refund timelines"),
    ("can you automatically approve my refund", "Refund approval limits"),
    ("is there a limit on refunds without human approval", "Refund approval limits"),
    ("can I cancel my order", "Order cancellation policy"),
    ("how long do I have to cancel an order", "Order cancellation policy"),
    ("can I cancel after it has shipped", "Order cancellation policy"),
    ("what is the return window", "Return window"),
    ("can I return jeans I bought", "Return window"),
    ("are all items returnable", "Return window"),
    ("my order hasn't arrived yet", "Delayed delivery"),
    ("my order is late, what should I do", "Delayed delivery"),
    ("why did my payment fail", "Payment failure reasons"),
    ("why was my card declined", "Payment failure reasons"),
    ("do I need to pay again after a failed payment", "Payment failure reasons"),
    ("does warranty cover physical damage", "Warranty coverage"),
    ("how long is the warranty", "Warranty coverage"),
    ("can I change my delivery address after ordering", "Changing a delivery address"),
    ("can support update my shipping address", "Changing a delivery address"),
]

OFF_TOPIC_QUERIES = [
    "what is the meaning of life",
    "recommend me a good movie",
    "how do I bake a chocolate cake",
    "tell me a joke",
    "what's the weather like today",
]


@pytest.mark.parametrize(("query", "expected_title"), ON_TOPIC_QUERIES)
async def test_on_topic_query_retrieves_expected_document(session, query, expected_title):
    results = await hybrid_search(session, query)
    assert results, f"expected results for {query!r}, got none"
    titles = [r.document_title for r in results]
    assert expected_title in titles, f"{query!r}: expected {expected_title!r} in {titles}"


async def test_recall_at_5_meets_target(session):
    hits = 0
    for query, expected_title in ON_TOPIC_QUERIES:
        results = await hybrid_search(session, query)
        if expected_title in [r.document_title for r in results]:
            hits += 1
    recall = hits / len(ON_TOPIC_QUERIES)
    assert recall >= 0.85, f"recall@5 was {recall:.2f}, expected >= 0.85"


@pytest.mark.parametrize("query", OFF_TOPIC_QUERIES)
async def test_off_topic_query_returns_nothing(session, query):
    results = await hybrid_search(session, query)
    assert results == [], f"expected no results for off-topic query {query!r}, got {results}"
