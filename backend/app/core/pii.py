"""PII redaction: regex-grade, not ML-grade, but a real path - see
docs/decisions/0003-prototype-scope.md ("PII redaction with
messages.body_redacted... so what the model saw is on the record").

Card numbers are redacted unconditionally (13-19 consecutive digits, the
shape of every real card scheme - low false-positive risk in normal
support chat). OTP/verification codes are only redacted near an explicit
keyword ("otp", "verification code", "pin", ...) - a bare rule like "any
4-8 digit number" would also eat order numbers (ORD-10432) and refund
amounts (4200), which the agent genuinely needs to reason about and which
are not the kind of secret this check exists to catch.
"""

import re

_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?<=\d)")

_OTP_RE = re.compile(
    r"\b(?:otp|one[- ]time (?:pass(?:code|word)?|code)|verification code|"
    r"passcode|pin|security code)\b[^\d]{0,15}(\d{4,8})",
    re.IGNORECASE,
)

CARD_PLACEHOLDER = "[REDACTED_CARD]"
CODE_PLACEHOLDER = "[REDACTED_CODE]"


def redact_pii(text: str | None) -> str | None:
    if not text:
        return text
    text = _CARD_RE.sub(CARD_PLACEHOLDER, text)
    text = _OTP_RE.sub(lambda m: m.group(0).replace(m.group(1), CODE_PLACEHOLDER), text)
    return text
