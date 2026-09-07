"""Voice channel adapter: recorded audio from the web widget's microphone
button. Transcribes to text inside parse() - same contract as every other
adapter, no LLM call and no business logic here, and the transcript is the
only thing the orchestrator ever sees (docs/01-architecture.md: "text: plain
text, already extracted from HTML/audio").

Replies are delivered the same way WebAdapter delivers them: the customer's
browser already holds a WebSocket connected to /channels/web/ws for the same
session_id, so send() reuses that same Redis pub/sub channel rather than
inventing a second delivery path.
"""

import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.channels.base import (
    Channel,
    DeliveryReceipt,
    InboundMessage,
    OutboundMessage,
    ResponseStyle,
)
from app.channels.web import ws_channel_name
from app.config import settings
from app.voice.stt import transcribe


class VoiceAdapter:
    channel = Channel.voice

    def __init__(self, redis: Redis | None = None):
        self._redis = redis or Redis.from_url(settings.redis_url)

    async def parse(self, payload: dict) -> InboundMessage:
        """payload: {session_id, audio_bytes, content_type, external_message_id?}"""
        text = await transcribe(payload["audio_bytes"], payload["content_type"])
        return InboundMessage(
            channel=self.channel,
            external_thread_id=payload["session_id"],
            external_message_id=payload.get("external_message_id") or str(uuid.uuid4()),
            sender_external_id=payload["session_id"],
            text=text,
            received_at=datetime.now(UTC),
            raw={"content_type": payload["content_type"], "transcript": text},
        )

    async def send(self, reply: OutboundMessage) -> DeliveryReceipt:
        await self._redis.publish(
            ws_channel_name(reply.external_thread_id),
            json.dumps({"text": reply.text}),
        )
        return DeliveryReceipt(ok=True)

    def style(self) -> ResponseStyle:
        # Short sentences, no markdown, no URLs - matches docs/07-build-stages.md
        # Stage 10. Enforced generically for every non-markdown channel by
        # app/channels/base.py:format_for_style, called from respond_node.
        return ResponseStyle(max_length=400, markdown=False, latency_budget_ms=20_000)
