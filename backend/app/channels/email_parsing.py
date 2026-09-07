"""MIME parsing and threading helpers, kept separate from the adapter so
they're testable as pure functions against real email.message.Message
objects, not through a live IMAP connection. This is the fiddly part of the
email channel per docs/09-risks.md R6 - 80% correct quoted-text stripping is
the accepted bar, not perfection.
"""

import re
from email.message import Message as EmailMessage
from email.utils import parseaddr

# Crude but effective: catches the most common quoted-reply openers across
# Gmail, Outlook and Apple Mail without needing a full quote-detection
# library. A stray signature or quote line surviving occasionally is an
# accepted rough edge, not a bug to chase - see docs/01-architecture.md's
# "what prototype tolerance means here".
_QUOTE_MARKERS = [
    re.compile(r"^On .+ wrote:\s*$", re.MULTILINE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^From:\s.+$", re.MULTILINE),
    re.compile(r"^>.*$", re.MULTILINE),  # a line of quoted text ('>' prefix)
]
_SIGNATURE_MARKER = re.compile(r"^--\s*$", re.MULTILINE)


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def extract_plain_text(msg: EmailMessage) -> str:
    """Prefers text/plain; falls back to a stripped text/html part."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return str(part.get_content()).strip()
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                return _strip_html(str(part.get_content()))
        return ""

    if msg.get_content_type() == "text/html":
        return _strip_html(str(msg.get_content()))
    return str(msg.get_content()).strip()


def strip_quoted_and_signature(body: str) -> str:
    """Cuts the body at the first quoted-reply marker or signature line,
    whichever comes first.
    """
    earliest_cut = len(body)
    for pattern in _QUOTE_MARKERS:
        match = pattern.search(body)
        if match and match.start() < earliest_cut:
            earliest_cut = match.start()
    sig_match = _SIGNATURE_MARKER.search(body)
    if sig_match and sig_match.start() < earliest_cut:
        earliest_cut = sig_match.start()
    return body[:earliest_cut].strip()


def thread_root_id(msg: EmailMessage) -> str:
    """The stable id a whole reply chain shares: the first entry in
    References (the thread's original message) if present, else
    In-Reply-To, else this message's own Message-ID for a fresh thread.
    """
    references = msg.get("References", "")
    if references:
        ids = references.split()
        if ids:
            return ids[0].strip("<>")
    in_reply_to = msg.get("In-Reply-To")
    if in_reply_to:
        return in_reply_to.strip("<>")
    return (msg.get("Message-ID") or "").strip("<>")


def is_auto_reply(msg: EmailMessage) -> bool:
    """Loop protection: never respond to a mailing list, an autoresponder,
    or another bot - without this, two auto-replying systems can bounce
    messages back and forth forever.
    """
    auto_submitted = (msg.get("Auto-Submitted") or "no").lower()
    if auto_submitted != "no":
        return True
    if msg.get("List-Id") or msg.get("List-Unsubscribe"):
        return True
    precedence = (msg.get("Precedence") or "").lower()
    return precedence in ("bulk", "junk", "list")


def sender_email(msg: EmailMessage) -> str:
    _, addr = parseaddr(msg.get("From", ""))
    return addr.lower()
