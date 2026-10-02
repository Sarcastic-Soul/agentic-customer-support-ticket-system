"""Live "what the agent is doing" events for the web chat.

The reply itself is never streamed token by token: every reply has to pass
the verify groundedness check first (CLAUDE.md non-negotiable #5), so it can
only be sent once it is whole. What can be sent early is *progress* - "Checking
your order", "Double-checking the answer" - so a customer waiting 5-15s on a
free-tier model sees the agent working instead of a frozen chat. See
docs/decisions/0008-upgrades.md.

Nodes call emit_progress(config, ...). It is a no-op unless the caller of the
graph put a publisher in config["configurable"]["progress"] - only the worker
does, and only for the web channel. Tests, the eval harness and other
channels never see these events. A failed publish is logged and dropped: a
progress event is never worth failing a run over.
"""

import json
from collections.abc import Awaitable, Callable

from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis

from app.channels.web import ws_channel_name
from app.logging import get_logger

logger = get_logger(__name__)

ProgressPublisher = Callable[[dict], Awaitable[None]]

# Customer-safe wording per tool. Tool names never reach the customer.
TOOL_LABELS: dict[str, str] = {
    "get_order": "Checking your order",
    "list_recent_orders": "Looking up your recent orders",
    "check_cancellation_eligibility": "Checking if your order can be cancelled",
    "request_cancellation": "Checking if your order can be cancelled",
    "check_return_eligibility": "Checking if the item can be returned",
    "initiate_return": "Checking if the item can be returned",
    "track_shipment": "Checking tracking with the carrier",
    "open_carrier_investigation": "Checking tracking with the carrier",
    "get_transaction": "Looking up your payment",
    "list_transactions_for_order": "Looking up your payment",
    "get_refund_status": "Checking your refund",
    "explain_payment_failure": "Looking up your payment",
    "request_refund": "Checking your refund",
    "generate_invoice": "Getting your invoice",
}
DEFAULT_TOOL_LABEL = "Looking into it"


def web_progress_publisher(redis: Redis, external_thread_id: str) -> ProgressPublisher:
    channel = ws_channel_name(external_thread_id)

    async def publish(event: dict) -> None:
        await redis.publish(channel, json.dumps({"type": "progress", **event}))

    return publish


async def emit_progress(
    config: RunnableConfig | None, stage: str, label: str, agent: str | None = None
) -> None:
    publish = ((config or {}).get("configurable") or {}).get("progress")
    if publish is None:
        return
    try:
        await publish({"stage": stage, "agent": agent, "label": label})
    except Exception:  # noqa: BLE001 - never fail a run over a progress event
        logger.warning("progress_publish_failed", stage=stage, exc_info=True)
