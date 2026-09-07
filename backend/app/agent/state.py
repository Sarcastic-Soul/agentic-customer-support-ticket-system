"""Graph state. Stage 4 scope only: prepare -> classify -> retrieve -> answer
-> respond. Fields for tools/policy/escalation (Stage 5+) are added when
those stages need them, not speculatively now.

`customer_id` and `ticket_id` are set by the worker before the graph runs
and never written to by a node from model output - see CLAUDE.md
non-negotiable #2. This is what makes prompt injection ("show me order
ORD-99999") harmless once tools are wired in Stage 5: a tool call reads
customer_id from this trusted state, never from what the model asked for.
"""

from typing import TypedDict


class RetrievedChunkDict(TypedDict):
    chunk_id: int
    document_title: str
    heading_path: str | None
    content: str
    dense_score: float | None
    sparse_score: float | None


class HistoryMessage(TypedDict):
    role: str  # customer | assistant
    body: str


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

    # plan
    tool_group: str | None  # orders | transactions | knowledge | none

    # retrieve
    retrieved: list[RetrievedChunkDict]

    # act
    tool_results: list[dict]
    tool_call_count: int

    # answer
    draft: str | None
    citations: list[int]

    # respond
    outcome: str | None  # answered | no_context | failed
