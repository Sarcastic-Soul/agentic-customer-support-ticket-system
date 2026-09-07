from pydantic import BaseModel

from app.agent.nodes.answer import format_context, format_tool_results
from app.agent.prompts import load_prompt
from app.agent.state import AgentState
from app.agent.steps import record_step
from app.llm.registry import get_llm
from app.llm.roles import LLMRole


class VerifyVerdict(BaseModel):
    grounded: bool
    answers_question: bool
    policy_safe: bool
    confidence: float


async def verify_node(state: AgentState, config) -> dict:
    """Groundedness/policy-safety gate before anything reaches a customer.
    One repair attempt (re-run answer with the verdict's reasoning fed
    back), then escalate rather than loop. Also where the two Stage-6
    escalation triggers that depend on Stage 4/5 output live:
    knowledge_gap (nothing to answer from) and policy_limit_exceeded (a
    write tool was denied and needs a human).
    """
    session = config["configurable"]["session"]

    if state["outcome"] == "no_context":
        return {"escalation_reason_code": "knowledge_gap", "escalation_priority": "P3"}

    if any(r["result"].get("requires_human") for r in state["tool_results"]):
        return {"escalation_reason_code": "policy_limit_exceeded", "escalation_priority": "P2"}

    prompt = load_prompt(
        "verify",
        context=format_context(state["retrieved"]),
        tool_results=format_tool_results(state["tool_results"]),
        message=state["latest_message"],
        draft=state["draft"],
    )

    client = get_llm(LLMRole.verify)
    outcome = await client.ainvoke(prompt, structured=VerifyVerdict)
    verdict = outcome.structured

    passed = bool(verdict and verdict.grounded and verdict.answers_question and verdict.policy_safe)

    await record_step(
        session, run_id=state["run_id"], node="verify",
        model=f"{outcome.provider}:{outcome.model}",
        prompt=prompt,
        output={"passed": passed, "verdict": verdict.model_dump() if verdict else None},
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
        latency_ms=outcome.latency_ms,
    )

    if passed:
        return {"verify_passed": True}

    if not state["verify_repair_attempted"]:
        feedback = (
            f"Your previous draft failed review: grounded={verdict.grounded if verdict else '?'}, "
            f"answers_question={verdict.answers_question if verdict else '?'}, "
            f"policy_safe={verdict.policy_safe if verdict else '?'}. "
            "Fix it - stay strictly within the knowledge and tool results, "
            "and make sure you actually answer what was asked."
        )
        return {
            "verify_passed": False,
            "verify_repair_attempted": True,
            "verify_feedback": feedback,
        }

    return {
        "verify_passed": False,
        "escalation_reason_code": "ungrounded_answer",
        "escalation_priority": "P3",
    }


def route_after_verify(state: AgentState) -> str:
    if state.get("escalation_reason_code"):
        return "escalate"
    if state.get("verify_passed") is False:
        return "answer"
    return "respond"
