import time

from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.agent.steps import record_step
from app.rag.search import hybrid_search

# Intents where a knowledge-base answer even makes sense. Everything else
# (order/refund status, chitchat) either needs a tool (Stage 5) or no
# retrieval at all - skipping retrieval for them avoids a wasted embedding
# call and, more importantly, avoids surfacing an irrelevant policy chunk.
KNOWLEDGE_INTENTS = {
    "policy_question", "product_question", "account_issue",
    "refund_status", "refund_request", "order_cancel", "order_return",
    "delivery_issue", "damaged_or_missing_item", "payment_failed",
    "billing_dispute", "invoice_request",
}


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]

    if state["intent"] not in KNOWLEDGE_INTENTS:
        await record_step(
            session, run_id=state["run_id"], node="retrieve",
            output={"skipped": True, "reason": f"intent {state['intent']} is not knowledge-shaped"},
        )
        return {"retrieved": []}

    start = time.monotonic()
    results = await hybrid_search(session, state["latest_message"])
    latency_ms = int((time.monotonic() - start) * 1000)

    retrieved = [
        {
            "chunk_id": r.chunk_id,
            "document_title": r.document_title,
            "heading_path": r.heading_path,
            "content": r.content,
            "dense_score": r.dense_score,
            "sparse_score": r.sparse_score,
        }
        for r in results
    ]

    await record_step(
        session, run_id=state["run_id"], node="retrieve",
        output={"count": len(retrieved), "chunk_ids": [r["chunk_id"] for r in retrieved]},
        latency_ms=latency_ms,
    )
    return {"retrieved": retrieved}
