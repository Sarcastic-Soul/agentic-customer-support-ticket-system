import re

from langchain_core.runnables import RunnableConfig

from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.llm.registry import get_llm
from app.llm.roles import LLMRole

NO_CONTEXT_REPLY = (
    "I don't have enough information to answer that confidently, so I'm "
    "passing this to a specialist who can help - they'll follow up shortly."
)

CITATION_RE = re.compile(r"\[(\d+)\]")


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    return "\n".join(f"{m['role']}: {m['body']}" for m in history)


def _format_context(retrieved: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] ({chunk['document_title']}"
        f"{' > ' + chunk['heading_path'] if chunk['heading_path'] else ''})\n"
        f"{chunk['content']}"
        for i, chunk in enumerate(retrieved)
    )


async def answer_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]

    # Stage 4 has no tool layer yet (Stage 5) and no escalation queue yet
    # (Stage 6) - without retrieved knowledge there is nothing grounded to
    # answer from, so the honest move is the fallback reply, not a guess.
    if not state["retrieved"]:
        await record_step(
            session, run_id=state["run_id"], node="answer",
            output={"skipped": True, "reason": "no retrieved context"},
        )
        return {"draft": NO_CONTEXT_REPLY, "citations": [], "outcome": "no_context"}

    prompt = load_prompt(
        "answer",
        intent=state["intent"],
        context=_format_context(state["retrieved"]),
        history=_format_history(state["history"]),
        message=state["latest_message"],
    )

    client = get_llm(LLMRole.reason)
    outcome = await client.ainvoke(prompt)
    draft = outcome.text or NO_CONTEXT_REPLY

    cited_positions = {int(n) for n in CITATION_RE.findall(draft)}
    citations = [
        state["retrieved"][pos - 1]["chunk_id"]
        for pos in sorted(cited_positions)
        if 1 <= pos <= len(state["retrieved"])
    ]

    await record_step(
        session, run_id=state["run_id"], node="answer",
        model=f"{outcome.provider}:{outcome.model}",
        prompt=prompt,
        output={"draft": draft, "citations": citations},
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
        latency_ms=outcome.latency_ms,
    )

    return {"draft": draft, "citations": citations, "outcome": "answered"}
