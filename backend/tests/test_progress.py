"""Live progress events for web chat (app/agent/progress.py). Pure: Redis is
an AsyncMock. The reply itself is never streamed - it is sent whole, after
verify - so these only check the progress frames and the reply frame shape.
"""

import json
from unittest.mock import AsyncMock

from app.agent.progress import TOOL_LABELS, emit_progress, web_progress_publisher
from app.channels.base import OutboundMessage
from app.channels.web import WebAdapter


async def test_no_publisher_is_a_no_op():
    await emit_progress(None, "classify", "Reading your message")
    await emit_progress({"configurable": {}}, "classify", "Reading your message")


async def test_publishes_progress_frame_to_the_customers_ws_channel():
    redis = AsyncMock()
    config = {"configurable": {"progress": web_progress_publisher(redis, "sess-1")}}

    await emit_progress(config, "specialist", "Checking your order", agent="orders")

    channel, payload = redis.publish.call_args.args
    assert channel == "ws:web:sess-1"
    assert json.loads(payload) == {
        "type": "progress", "stage": "specialist", "agent": "orders",
        "label": "Checking your order",
    }


async def test_a_failed_publish_never_fails_the_run():
    redis = AsyncMock()
    redis.publish.side_effect = ConnectionError("redis down")
    config = {"configurable": {"progress": web_progress_publisher(redis, "sess-1")}}

    await emit_progress(config, "verify", "Double-checking the answer")


def test_tool_labels_never_leak_tool_names():
    for name, label in TOOL_LABELS.items():
        assert "_" not in label
        assert name not in label


async def test_reply_frame_is_typed():
    redis = AsyncMock()
    await WebAdapter(redis=redis).send(
        OutboundMessage(channel="web", external_thread_id="sess-1", text="hi")
    )
    _, payload = redis.publish.call_args.args
    assert json.loads(payload) == {"type": "reply", "text": "hi"}
