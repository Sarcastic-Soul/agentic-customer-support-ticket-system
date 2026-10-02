"""Graph state for prepare -> classify -> hard_route -> supervisor ->
retrieve -> specialist (x1-2, in parallel) -> reconcile -> commit -> answer
-> verify -> respond | escalate.

`customer_id` and `ticket_id` are set by the worker before the graph runs
and never written to by a node from model output - see CLAUDE.md
non-negotiable #2. This is what makes prompt injection ("show me order
ORD-99999") harmless once tools are wired in Stage 5: a tool call reads
customer_id from this trusted state, never from what the model asked for.
"""

from typing import Annotated, TypedDict


class RetrievedChunkDict(TypedDict):
    chunk_id: int
    document_title: str
    heading_path: str | None
    content: str
    dense_score: float | None
    sparse_score: float | None
    rerank_score: float | None


class HistoryMessage(TypedDict):
    role: str  # customer | assistant
    body: str


def merge_reports(left: list | None, right: list | None) -> list:
    """Specialists run in parallel and each returns one report, so this key
    needs a reducer to collect them. Checkpointed state carries over between
    runs on the same ticket thread, so run_agent passes None to clear the
    previous turn's reports before any specialist runs.
    """
    if right is None:
        return []
    return (left or []) + right


class AgentState(TypedDict):
    # trusted context, set before the graph runs
    run_id: int
    ticket_id: int
    conversation_id: int
    customer_id: int
    channel: str
    external_thread_id: str
    latest_message: str
    history: list[HistoryMessage]

    # classify
    intent: str | None
    intent_confidence: float | None
    secondary_intent: str | None  # a second request in the same message, if any

    # supervisor
    tool_group: str | None  # specialists | knowledge | none | clarify
    specialists: list[str]  # dispatch order; earlier wins conflict ties

    # retrieve
    retrieved: list[RetrievedChunkDict]

    # specialist (parallel) -> reconcile -> commit
    specialist_reports: Annotated[list[dict], merge_reports]
    conflicts: list[dict]
    to_commit: list[dict]
    force_approval: list[str]  # txn_refs that must go through the approval queue
    tool_results: list[dict]
    tool_call_count: int

    # answer
    draft: str | None
    citations: list[int]

    # verify
    verify_repairs: int
    verify_feedback: str | None
    verify_passed: bool | None

    # escalation triggers / hard_route
    ai_turns: int
    # Clarifying questions asked in a row. Not reset by run_agent - it is
    # carried in the checkpointed state across turns, so a customer who stays
    # unclear still reaches a human after settings.max_clarifications.
    clarifications: int
    escalation_reason_code: str | None
    escalation_priority: str | None
    human_note: str | None  # populated on resume, from the console's return-to-AI action

    # respond
    outcome: str | None  # answered | clarified | no_context | escalated | failed
