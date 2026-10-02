import time

from langchain_core.runnables import RunnableConfig

from app.agent.progress import emit_progress
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.config import settings
from app.rag.search import hybrid_search


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    """The knowledge lane. Runs for every tool_group except "none"
    (chitchat/feedback/spam/unknown) - messages handled by specialists get
    policy context alongside their tools (a refund request benefits from
    the approval-limits policy, not just the transaction lookup), not only
    pure knowledge questions. See app/agent/nodes/supervisor.py for how
    tool_group is set. Steps are tagged agent="knowledge" in the trace.
    """
    session = config["configurable"]["session"]

    if state["tool_group"] == "none":
        await record_step(
            session, run_id=state["run_id"], node="retrieve", agent="knowledge",
            output={"skipped": True, "reason": "tool_group is 'none'"},
        )
        return {"retrieved": []}

    if settings.eval_ablation == "no_rag":
        # Stage 11 ablation: parametric memory only - answer_node still runs,
        # it just never sees any retrieved context.
        await record_step(
            session, run_id=state["run_id"], node="retrieve", agent="knowledge",
            output={"skipped": True, "reason": "eval_ablation=no_rag"},
        )
        return {"retrieved": []}

    await emit_progress(config, "retrieve", "Searching our help articles", agent="knowledge")
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
            "rerank_score": r.rerank_score,
        }
        for r in results
    ]

    await record_step(
        session, run_id=state["run_id"], node="retrieve", agent="knowledge",
        output={
            "count": len(retrieved), "chunk_ids": [r["chunk_id"] for r in retrieved],
            "reranked": any(r["rerank_score"] is not None for r in retrieved),
        },
        latency_ms=latency_ms,
    )
    return {"retrieved": retrieved}
