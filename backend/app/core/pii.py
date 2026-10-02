"""PII redaction into messages.body_redacted - what the model sees.

Two layers:

1. **Regex rules, always on.** Card numbers are redacted unconditionally
   (13-19 consecutive digits, the shape of every real card scheme - low
   false-positive risk in normal support chat). OTP/verification codes only
   near an explicit keyword ("otp", "verification code", "pin", ...) - a bare
   rule like "any 4-8 digit number" would also eat order numbers (ORD-10432)
   and refund amounts (4200), which the agent needs to reason about.

2. **Presidio** (settings.pii_engine == "presidio"): spaCy NER plus
   Presidio's pattern recognizers, for what regex can't see - people's
   names, email addresses, phone numbers, Aadhaar/PAN numbers, IBANs, IPs.
   Locations are deliberately NOT redacted: "do you ship to Singapore?"
   needs the place name to be answered. Anything overlapping an order or
   transaction reference is kept, since tools need those verbatim.

The customer's identity never comes from the message body (it comes from
trusted channel state - CLAUDE.md non-negotiable #2), so redacting a name or
an email in the text costs the agent nothing. If Presidio or the spaCy model
can't load, redaction falls back to the regex layer and logs it once - a
missing model must not stop messages being ingested.
"""

import re
from functools import lru_cache

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?<=\d)")

_OTP_RE = re.compile(
    r"\b(?:otp|one[- ]time (?:pass(?:code|word)?|code)|verification code|"
    r"passcode|pin|security code)\b[^\d]{0,15}(\d{4,8})",
    re.IGNORECASE,
)

# References the tools need exactly as written - never redact inside these.
_KEEP_RE = re.compile(r"\b(?:ORD|TXN|T|TKT)-[A-Z0-9-]+\b", re.IGNORECASE)

CARD_PLACEHOLDER = "[REDACTED_CARD]"
CODE_PLACEHOLDER = "[REDACTED_CODE]"

# Presidio entity -> placeholder. Only these are redacted.
_ENTITY_PLACEHOLDERS = {
    "PERSON": "[REDACTED_NAME]",
    "EMAIL_ADDRESS": "[REDACTED_EMAIL]",
    "PHONE_NUMBER": "[REDACTED_PHONE]",
    "CREDIT_CARD": CARD_PLACEHOLDER,
    "IBAN_CODE": "[REDACTED_ID]",
    "IN_AADHAAR": "[REDACTED_ID]",
    "IN_PAN": "[REDACTED_ID]",
    "IP_ADDRESS": "[REDACTED_ID]",
}
# PAN with its "PAN" keyword nearby scores 0.45; spaCy entities score 0.85
_SCORE_MIN = 0.4

_presidio_failed = False


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import InAadhaarRecognizer, InPanRecognizer

    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": settings.pii_spacy_model}],
        }
    ).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    # Country-specific recognizers aren't in Presidio's default registry
    analyzer.registry.add_recognizer(InAadhaarRecognizer())
    analyzer.registry.add_recognizer(InPanRecognizer())
    return analyzer


def _presidio_redact(text: str) -> str:
    global _presidio_failed
    if settings.pii_engine != "presidio" or _presidio_failed:
        return text
    try:
        results = _analyzer().analyze(
            text=text,
            language="en",
            entities=list(_ENTITY_PLACEHOLDERS),
            score_threshold=_SCORE_MIN,
        )
    except Exception:
        logger.exception("presidio_unavailable_falling_back_to_regex")
        _presidio_failed = True
        return text

    keep = [m.span() for m in _KEEP_RE.finditer(text)]
    placeholders = set(_ENTITY_PLACEHOLDERS.values()) | {CODE_PLACEHOLDER}

    spans: list[tuple[int, int, str]] = []
    for r in sorted(results, key=lambda r: (r.start, -(r.end - r.start))):
        if any(r.start < k_end and k_start < r.end for k_start, k_end in keep):
            continue
        if text[r.start:r.end] in placeholders or "REDACTED" in text[r.start:r.end]:
            continue  # already redacted by the regex layer
        if spans and r.start < spans[-1][1]:
            continue  # overlaps a longer span already taken
        spans.append((r.start, r.end, _ENTITY_PLACEHOLDERS[r.entity_type]))

    for start, end, placeholder in reversed(spans):
        text = text[:start] + placeholder + text[end:]
    return text


def redact_pii(text: str | None) -> str | None:
    if not text:
        return text
    text = _CARD_RE.sub(CARD_PLACEHOLDER, text)
    text = _OTP_RE.sub(lambda m: m.group(0).replace(m.group(1), CODE_PLACEHOLDER), text)
    return _presidio_redact(text)
