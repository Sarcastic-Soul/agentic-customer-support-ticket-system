"""Web chat adapter. The customer-facing surface is a WebSocket, not a
webhook, but it still goes through the same InboundMessage/OutboundMessage
shapes as every other channel - the WS handler in app/ingress/web.py is a
thin transport, this module is where "what a web message looks like" lives.
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
from app.config import settings


def ws_channel_name(external_thread_id: str) -> str:
    return f"ws:web:{external_thread_id}"


class WebAdapter:
    channel = Channel.web

    def __init__(self, redis: Redis | None = None):
        self._redis = redis or Redis.from_url(settings.redis_url)

    async def parse(self, payload: dict) -> InboundMessage:
        return InboundMessage(
            channel=self.channel,
            external_thread_id=payload["session_id"],
            external_message_id=payload.get("external_message_id") or str(uuid.uuid4()),
            sender_external_id=payload["session_id"],
            text=payload["text"],
            received_at=datetime.now(UTC),
            raw=payload,
        )

    async def send(self, reply: OutboundMessage) -> DeliveryReceipt:
        # The worker that sends this reply is a separate process from the one
        # holding the customer's WebSocket connection - Redis pubsub bridges
        # them. The WS handler subscribes to this same channel name.
        await self._redis.publish(
            ws_channel_name(reply.external_thread_id),
            json.dumps({"text": reply.text}),
        )
        return DeliveryReceipt(ok=True)

    def style(self) -> ResponseStyle:
        return ResponseStyle(max_length=2000, markdown=True, latency_budget_ms=15_000)
