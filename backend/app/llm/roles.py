from enum import StrEnum


class LLMRole(StrEnum):
    classify = "classify"
    reason = "reason"
    verify = "verify"
    summarize = "summarize"
    judge = "judge"
