"""IMAP polling: an arq cron job, not a live push subscription (IMAP IDLE) -
docs/07-build-stages.md's explicit choice, matching the 30-60s cadence every
other "how fresh does this need to be" decision in this project uses.
imaplib is blocking, so the actual network I/O runs in a thread
(asyncio.to_thread) and returns raw bytes; parsing and ingestion happen back
on the event loop, using the same ingest_message pipeline every channel goes
through.
"""

import asyncio
import email as email_lib
import imaplib

from app.channels.email import EmailAdapter
from app.channels.email_parsing import is_auto_reply, sender_email
from app.config import settings
from app.db.session import async_session_factory
from app.ingress.pipeline import ingest_message
from app.logging import get_logger
from app.workers.queue import enqueue_handle_message

logger = get_logger(__name__)


def _fetch_unseen_sync() -> list[bytes]:
    """All blocking IMAP I/O lives here, so it can run in a worker thread.
    Marks each fetched message \\Seen as it goes - if ingestion later fails
    for one message, it won't be re-fetched forever (accepted: a message
    lost between "marked seen" and "ingested" is a known, rare gap, not
    unlike Stage 2's "work in flight is lost on restart" trade-off).
    """
    raws: list[bytes] = []
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
        imap.login(settings.support_email, settings.support_email_app_password)
        imap.select("INBOX")
        typ, data = imap.search(None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return raws
        for num in data[0].split():
            typ, msg_data = imap.fetch(num, "(RFC822)")
            if typ == "OK" and msg_data and isinstance(msg_data[0], tuple):
                raws.append(msg_data[0][1])
            imap.store(num, "+FLAGS", "\\Seen")
    return raws


async def poll_inbox() -> int:
    """Returns the number of messages ingested (auto-replies and
    already-seen duplicates don't count).
    """
    if not settings.email_enabled:
        return 0

    raws = await asyncio.to_thread(_fetch_unseen_sync)
    if not raws:
        return 0

    adapter = EmailAdapter()
    ingested = 0

    async with async_session_factory() as session:
        for raw in raws:
            parsed = email_lib.message_from_bytes(raw, policy=email_lib.policy.default)
            if is_auto_reply(parsed):
                logger.info("email_auto_reply_ignored", from_=sender_email(parsed))
                continue

            inbound = await adapter.parse(raw)
            message = await ingest_message(
                session,
                channel=inbound.channel,
                external_thread_id=inbound.external_thread_id,
                sender_external_id=inbound.sender_external_id,
                text=inbound.text,
                external_message_id=inbound.external_message_id,
                raw_payload=inbound.raw,
            )
            await session.commit()

            if message is not None:
                await enqueue_handle_message(message.id)
                ingested += 1

    logger.info("email_poll_complete", fetched=len(raws), ingested=ingested)
    return ingested


async def poll_inbox_job(ctx: dict) -> int:
    """arq cron entrypoint - ctx is arq's per-run context, unused here."""
    return await poll_inbox()
