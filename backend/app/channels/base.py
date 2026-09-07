"""The canonical shapes every channel adapter converts to and from.

Adapters contain no LLM and no business logic - they normalize a provider
payload into one InboundMessage and render an OutboundMessage back into the
provider's format. Everything downstream (ingress, the orchestrator) only
ever sees these types, never a raw webhook payload.
"""

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class Channel(StrEnum):
    web = "web"
    whatsapp = "whatsapp"
    email = "email"
    voice = "voice"


class ResponseStyle(BaseModel):
    """Per-channel rendering constraints - length budget, formatting, latency."""

    max_length: int
    markdown: bool = False
    latency_budget_ms: int = 10_000


class Attachment(BaseModel):
    url: str
    content_type: str | None = None


class InboundMessage(BaseModel):
    channel: Channel
    external_thread_id: str  # phone number, email thread id, session id
    external_message_id: str  # used for dedupe
    sender_external_id: str  # who sent it, on this channel
    text: str
    subject: str | None = None
    attachments: list[Attachment] = []
    received_at: datetime
    raw: dict = {}  # the untouched provider payload


class OutboundMessage(BaseModel):
    channel: Channel
    external_thread_id: str
    text: str


class DeliveryReceipt(BaseModel):
    ok: bool
    detail: str | None = None


class ChannelAdapter(Protocol):
    channel: Channel

    async def parse(self, payload: dict) -> InboundMessage: ...
    async def send(self, reply: OutboundMessage) -> DeliveryReceipt: ...
    def style(self) -> ResponseStyle: ...
