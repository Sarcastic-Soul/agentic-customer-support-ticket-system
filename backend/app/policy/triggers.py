"""Deterministic escalation triggers - keyword-based, checked before any
expensive reasoning. These always win over model judgement; see
docs/05-escalation-policy.md's trigger table. A short, defensible keyword
list, not an NLP classifier - false negatives here just mean the judgemental
triggers (low confidence, ungrounded answer) catch it downstream instead.
"""

import re

HUMAN_REQUEST_RE = re.compile(
    r"\b(talk to|speak to|connect me to|transfer me to)\s+(a\s+)?"
    r"(human|person|agent|representative|supervisor|manager)\b"
    r"|\bhuman agent\b|\breal person\b",
    re.IGNORECASE,
)

ABUSE_OR_DISTRESS_RE = re.compile(
    r"\b(kill myself|suicide|self.?harm|end my life|hurt myself)\b",
    re.IGNORECASE,
)

LEGAL_RE = re.compile(
    r"\b(lawyer|legal action|sue you|sue your company|consumer court|"
    r"chargeback|police complaint|fraud complaint|legal notice)\b",
    re.IGNORECASE,
)


def check_hard_triggers(text: str) -> tuple[str, str] | None:
    """Returns (reason_code, priority) if a deterministic trigger fires,
    else None.
    """
    if ABUSE_OR_DISTRESS_RE.search(text):
        return "abusive_or_distress", "P2"
    if LEGAL_RE.search(text):
        return "legal_or_regulatory", "P2"
    if HUMAN_REQUEST_RE.search(text):
        return "customer_requested_human", "P3"
    return None
