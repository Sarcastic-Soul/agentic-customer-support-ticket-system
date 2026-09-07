"""Email adapter (IMAP/SMTP). Same InboundMessage/OutboundMessage contract as
every other channel - app/workers/email_poll.py is the thin transport that
calls parse(); this module also owns send(), which (unlike the other
adapters) needs a short DB lookup to reply correctly - see send()'s
docstring.
"""

import asyncio
import email as email_lib
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage as OutgoingEmailMessage

from sqlalchemy import select

from app.channels.base import (
    Channel,
    DeliveryReceipt,
    InboundMessage,
    OutboundMessage,
    ResponseStyle,
)
from app.channels.email_parsing import (
    extract_plain_text,
    sender_email,
    strip_quoted_and_signature,
    thread_root_id,
)
from app.config import settings
from app.db.session import async_session_factory
from app.logging import get_logger
from app.models import Conversation, CustomerIdentity, Message, Ticket

logger = get_logger(__name__)


class EmailAdapter:
    channel = Channel.email

    async def parse(self, raw: bytes) -> InboundMessage:
        msg = email_lib.message_from_bytes(raw, policy=email_lib.policy.default)
        body = strip_quoted_and_signature(extract_plain_text(msg))
        message_id = (msg.get("Message-ID") or "").strip("<>")

        return InboundMessage(
            channel=self.channel,
            external_thread_id=thread_root_id(msg),
            external_message_id=message_id,
            sender_external_id=sender_email(msg),
            subject=msg.get("Subject"),
            text=body,
            received_at=datetime.now(UTC),
            raw={"headers": dict(msg.items())},
        )

    async def send(self, reply: OutboundMessage) -> DeliveryReceipt:
        """reply.external_thread_id is the thread's *root Message-ID*
        (that's the conversation-grouping key for email - see
        InboundMessage.external_thread_id / thread_root_id()), not the
        customer's address. Unlike Web/WhatsApp, where the thread id and the
        "where do I send this" id are the same value, email needs a real
        lookup for both: the recipient address (from the customer's email
        CustomerIdentity - Customer.email may be unset for a customer who
        has only ever contacted by email so far) and the reply headers
        (last inbound Message-ID, ticket subject). Found live: an earlier
        version used external_thread_id as the To: address directly, which
        happened to look email-shaped in manual testing (a simulator test
        used a Message-ID formatted like an address) but would have mailed
        the wrong "address" - a Message-ID string - in real use. See
        docs/PROGRESS.md Stage 8.
        """
        to_address, in_reply_to, subject = await self._reply_context(reply.external_thread_id)
        if to_address is None:
            logger.warning(
                "email_send_no_recipient_address", thread_id=reply.external_thread_id
            )
            return DeliveryReceipt(ok=False, detail="no email address on file for this thread")

        msg = OutgoingEmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.support_email
        msg["To"] = to_address
        if in_reply_to:
            msg["In-Reply-To"] = f"<{in_reply_to}>"
            msg["References"] = f"<{in_reply_to}>"
        msg.set_content(reply.text)

        try:
            await asyncio.to_thread(self._send_sync, msg)
        except Exception as exc:  # noqa: BLE001 - reported back as a structured receipt
            logger.warning("email_send_failed", to=to_address, error=str(exc))
            return DeliveryReceipt(ok=False, detail=str(exc))

        return DeliveryReceipt(ok=True, detail=(msg.get("Message-ID") or "").strip("<>"))

    def _send_sync(self, msg: OutgoingEmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.support_email, settings.support_email_app_password)
            server.send_message(msg)

    async def _reply_context(
        self, external_thread_id: str
    ) -> tuple[str | None, str | None, str]:
        """Returns (recipient_address, in_reply_to_message_id, subject)."""
        async with async_session_factory() as session:
            conversation = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.channel == "email",
                        Conversation.external_thread_id == external_thread_id,
                    )
                )
            ).scalar_one_or_none()
            if conversation is None:
                return None, None, "Support ticket update"

            identity = (
                await session.execute(
                    select(CustomerIdentity).where(
                        CustomerIdentity.customer_id == conversation.customer_id,
                        CustomerIdentity.channel == "email",
                    )
                )
            ).scalar_one_or_none()
            to_address = identity.external_id if identity else None

            last_inbound = (
                await session.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.direction == "inbound",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            in_reply_to = last_inbound.external_message_id if last_inbound else None

            ticket = (
                await session.execute(
                    select(Ticket).where(Ticket.conversation_id == conversation.id)
                )
            ).scalar_one_or_none()
            subject = "Support ticket update"
            if ticket and ticket.subject:
                subject = (
                    ticket.subject
                    if ticket.subject.lower().startswith("re:")
                    else f"Re: {ticket.subject}"
                )
            return to_address, in_reply_to, subject

    def style(self) -> ResponseStyle:
        return ResponseStyle(max_length=4000, markdown=False, latency_budget_ms=60_000)
