import time

from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.agent.steps import record_step
from app.config import settings
from app.rag.search import hybrid_search


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    """Runs for every tool_group except "none" (chitchat/feedback/spam/
    unknown) - order and transaction intents get policy context alongside
    their tools (e.g. a refund request benefits from the approval-limits
    policy, not just the transaction lookup), not only pure knowledge
    questions. See app/agent/nodes/plan.py for how tool_group is set.
    """
    session = config["configurable"]["session"]

    if state["tool_group"] == "none":
        await record_step(
            session, run_id=state["run_id"], node="retrieve",
            output={"skipped": True, "reason": "tool_group is 'none'"},
        )
        return {"retrieved": []}

    if settings.eval_ablation == "no_rag":
        # Stage 11 ablation: parametric memory only - answer_node still runs,
        # it just never sees any retrieved context.
        await record_step(
            session, run_id=state["run_id"], node="retrieve",
            output={"skipped": True, "reason": "eval_ablation=no_rag"},
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
