import json
import re

from langchain_core.runnables import RunnableConfig

from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.channels.base import Channel, ResponseStyle
from app.channels.registry import get_adapter
from app.llm.registry import get_llm
from app.llm.roles import LLMRole

NO_CONTEXT_REPLY = (
    "I don't have enough information to answer that confidently, so I'm "
    "passing this to a specialist who can help - they'll follow up shortly."
)

CITATION_RE = re.compile(r"\[(\d+)\]")


def format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    return "\n".join(f"{m['role']}: {m['body']}" for m in history)


def format_context(retrieved: list[dict]) -> str:
    if not retrieved:
        return "(none retrieved)"
    return "\n\n".join(
        f"[{i + 1}] ({chunk['document_title']}"
        f"{' > ' + chunk['heading_path'] if chunk['heading_path'] else ''})\n"
        f"{chunk['content']}"
        for i, chunk in enumerate(retrieved)
    )


def format_tool_results(tool_results: list[dict]) -> str:
    if not tool_results:
        return "(no tools were called)"
    return "\n\n".join(
        f"{r['tool']}({r['args']}) ->\n{json.dumps(r['result'], default=str)}"
        for r in tool_results
    )


def _style_guidance(style: ResponseStyle) -> str:
    """Nudges generation itself toward a channel's rendering constraints,
    rather than relying only on post-hoc truncation/stripping in
    respond_node - avoids an LLM-written reply getting chopped mid-sentence
    just because it assumed markdown or an unbounded length were fine.
    """
    if style.markdown:
        return ""
    return (
        "\nRespond in plain spoken language: short sentences, no markdown "
        "formatting (no asterisks, headers, or bullet lists), and no links "
        f"or URLs. Keep the whole reply under {style.max_length} characters.\n"
    )


def _format_extra_guidance(state: AgentState) -> str:
    """Guidance not part of the normal grounded context: a human's note on
    return-to-AI (Stage 6), or verify's feedback on a repair pass. Both are
    optional and additive - most turns have neither.
    """
    parts = []
    if state.get("human_note"):
        parts.append(
            "A human support agent reviewed this case and left a note for "
            f"you to act on: {state['human_note']}"
        )
    if state.get("verify_feedback"):
        parts.append(f"Revision needed: {state['verify_feedback']}")
    if not parts:
        return ""
    return "\n" + "\n".join(parts) + "\n"


async def answer_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["session"]

    # chitchat/feedback/spam/unknown (plan_node's tool_group == "none") need
    # no KB context or tool results - a plain conversational reply is the
    # correct behaviour, not an escalation. Only order/transaction/knowledge
    # intents that genuinely found nothing fall into the no-context gap
    # below, which verify_node turns into a real knowledge_gap escalation.
    #
    # tool_group is also None (never "none") when hard_route escalated
    # before plan ever ran (customer_requested_human, abuse, legal, low
    # confidence, turn budget) - resuming that via return-to-ai lands here
    # with no tool_group set at all. Treat it the same as "none": the human
    # note is what matters now, not a domain lookup that was never planned.
    style = get_adapter(Channel(state["channel"])).style()

    if state["tool_group"] in (None, "none"):
        prompt = load_prompt(
            "chitchat",
            style_guidance=_style_guidance(style),
            history=format_history(state["history"]),
            message=state["latest_message"],
        )
        client = get_llm(LLMRole.reason)
        outcome = await client.ainvoke(prompt)
        draft = outcome.text or NO_CONTEXT_REPLY
        await record_step(
            session, run_id=state["run_id"], node="answer",
            model=f"{outcome.provider}:{outcome.model}", prompt=prompt,
            output={"draft": draft, "citations": []},
            tokens_in=outcome.tokens_in, tokens_out=outcome.tokens_out,
            latency_ms=outcome.latency_ms,
        )
        return {"draft": draft, "citations": [], "outcome": "answered"}

    if not state["retrieved"] and not state["tool_results"]:
        await record_step(
            session, run_id=state["run_id"], node="answer",
            output={"skipped": True, "reason": "no retrieved context and no tool results"},
        )
        return {"draft": NO_CONTEXT_REPLY, "citations": [], "outcome": "no_context"}

    prompt = load_prompt(
        "answer",
        intent=state["intent"],
        context=format_context(state["retrieved"]),
        tool_results=format_tool_results(state["tool_results"]),
        extra_guidance=_format_extra_guidance(state) + _style_guidance(style),
        history=format_history(state["history"]),
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
