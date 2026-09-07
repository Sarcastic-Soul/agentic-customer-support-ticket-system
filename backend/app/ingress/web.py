"""Web chat ingress: the WebSocket endpoint the /chat page connects to.

A thin transport layer only - it parses the inbound frame, runs it through the
same ingest_message pipeline every channel uses, enqueues the worker job, and
bridges the worker's reply (published over Redis, since the worker is a
different process) back onto this connection.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.channels.web import WebAdapter, ws_channel_name
from app.config import settings
from app.db.session import async_session_factory
from app.ingress.pipeline import ingest_message
from app.logging import get_logger
from app.workers.queue import enqueue_handle_message

router = APIRouter(prefix="/channels/web", tags=["channels"])
logger = get_logger(__name__)


@router.websocket("/ws")
async def web_chat_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    redis = Redis.from_url(settings.redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe(ws_channel_name(session_id))
    adapter = WebAdapter(redis)

    async def forward_replies() -> None:
        try:
            async for item in pubsub.listen():
                if item["type"] == "message":
                    # redis-py delivers pubsub payloads as bytes even though
                    # we published a str - decode, or Starlette rejects the
                    # frame (send_text requires str) and this task dies
                    # silently since nothing awaits it.
                    data = item["data"]
                    await websocket.send_text(data.decode() if isinstance(data, bytes) else data)
        except Exception:
            logger.exception("web_ws_forward_replies_failed", session_id=session_id)

    forwarder = asyncio.create_task(forward_replies())
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            inbound = await adapter.parse({"session_id": session_id, "text": payload["text"]})

            async with async_session_factory() as session:
                message = await ingest_message(
                    session,
                    channel=inbound.channel,
                    external_thread_id=inbound.external_thread_id,
                    sender_external_id=inbound.sender_external_id,
                    text=inbound.text,
                    external_message_id=inbound.external_message_id,
                    raw_payload=inbound.model_dump(mode="json"),
                )
                await session.commit()

            if message is not None:
                await enqueue_handle_message(message.id)
    except WebSocketDisconnect:
        logger.info("web_ws_disconnect", session_id=session_id)
    finally:
        forwarder.cancel()
        await pubsub.unsubscribe(ws_channel_name(session_id))
        await pubsub.aclose()
        await redis.aclose()
