"""WhatsApp adapter (Twilio). Same InboundMessage/OutboundMessage contract as
every other channel - the ingress webhook is a thin transport, this module
is where "what a WhatsApp message looks like" lives, matching app/channels/web.py.
"""

from datetime import UTC, datetime

import httpx
from twilio.rest import Client

from app.channels.base import (
    Channel,
    DeliveryReceipt,
    InboundMessage,
    OutboundMessage,
    ResponseStyle,
)
from app.config import settings
from app.logging import get_logger
from app.voice.stt import TranscriptionError, transcribe

logger = get_logger(__name__)

# Twilio returns a specific error when a free-form message is sent outside
# the 24-hour customer service window (see docs/02-tech-stack.md and
# docs/09-risks.md R14) - only template messages work there, which this
# prototype doesn't implement. Recognizing it lets us log something useful
# instead of a generic send failure.
OUTSIDE_WINDOW_ERROR_CODE = 63016


def _strip_whatsapp_prefix(value: str) -> str:
    return value.removeprefix("whatsapp:")


class WhatsAppAdapter:
    channel = Channel.whatsapp

    def __init__(self, client: Client | None = None):
        self._client = client or Client(settings.twilio_account_sid, settings.twilio_auth_token)

    async def parse(self, payload: dict) -> InboundMessage:
        """payload is the form-decoded Twilio webhook body - see
        app/ingress/whatsapp.py for where signature verification and
        form-parsing happen before this is called.
        """
        from_number = _strip_whatsapp_prefix(payload["From"])
        attachments = [
            {
                "url": payload[key],
                "content_type": payload.get(key.replace("Url", "ContentType")),
            }
            for key in payload
            if key.startswith("MediaUrl")
        ]

        text = payload.get("Body", "")
        if not text and attachments:
            # A pure voice note has no Body - Stage 10's "accept WhatsApp
            # audio -> normal pipeline, unchanged" means transcribing it
            # here, inside parse(), same as every other channel's text
            # extraction (docs/01-architecture.md).
            text = await self._transcribe_voice_note(attachments[0])

        return InboundMessage(
            channel=self.channel,
            external_thread_id=from_number,
            external_message_id=payload["MessageSid"],
            sender_external_id=from_number,
            text=text,
            attachments=attachments,
            received_at=datetime.now(UTC),
            raw=payload,
        )

    async def _transcribe_voice_note(self, attachment: dict) -> str:
        content_type = attachment.get("content_type") or ""
        if not content_type.startswith("audio/"):
            return ""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    attachment["url"],
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                )
                response.raise_for_status()
            return await transcribe(response.content, content_type)
        except (httpx.HTTPError, TranscriptionError) as exc:
            logger.warning("whatsapp_voice_transcription_failed", error=str(exc))
            return "(voice note received - could not be transcribed)"

    async def send(self, reply: OutboundMessage) -> DeliveryReceipt:
        try:
            message = self._client.messages.create(
                from_=settings.twilio_whatsapp_from,
                to=f"whatsapp:{reply.external_thread_id}",
                body=reply.text,
            )
        except Exception as exc:  # noqa: BLE001 - reported back as a structured receipt
            code = getattr(exc, "code", None)
            if code == OUTSIDE_WINDOW_ERROR_CODE:
                logger.warning(
                    "whatsapp_outside_service_window",
                    to=reply.external_thread_id,
                    detail="customer's 24h service window has closed - template "
                    "messages are not implemented in this prototype",
                )
            else:
                logger.warning("whatsapp_send_failed", to=reply.external_thread_id, error=str(exc))
            return DeliveryReceipt(ok=False, detail=str(exc))

        return DeliveryReceipt(ok=True, detail=message.sid)

    def style(self) -> ResponseStyle:
        # WhatsApp doesn't hard-cap message length, but short replies suit
        # the medium and keep well clear of the ~4096 char message limit.
        return ResponseStyle(max_length=1000, markdown=False, latency_budget_ms=10_000)
