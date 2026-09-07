"""Dev-only endpoints. Every external channel gets a simulator before the real
adapter - this is the web one, built in Stage 1 so the ingress pipeline can be
exercised (and tested) with the network unplugged. Since Stage 2, it enqueues
the same worker job the real /channels/web/ws endpoint does, so it stays a
faithful stand-in rather than a shortcut that quietly drifts from production.
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.ingress.pipeline import ingest_message
from app.workers.queue import enqueue_handle_message

router = APIRouter(prefix="/dev", tags=["dev"])


class SimulateWebMessage(BaseModel):
    session_id: str
    text: str
    external_message_id: str | None = None


class SimulateWebResponse(BaseModel):
    stored: bool
    message_id: int | None = None
    conversation_id: int | None = None


@router.post("/simulate/web", response_model=SimulateWebResponse)
async def simulate_web_message(
    body: SimulateWebMessage, session: AsyncSession = Depends(get_session)
) -> SimulateWebResponse:
    external_message_id = body.external_message_id or str(uuid.uuid4())

    message = await ingest_message(
        session,
        channel="web",
        external_thread_id=body.session_id,
        sender_external_id=body.session_id,
        text=body.text,
        external_message_id=external_message_id,
        raw_payload=body.model_dump(),
    )
    await session.commit()

    if message is None:
        return SimulateWebResponse(stored=False)

    await enqueue_handle_message(message.id)
    return SimulateWebResponse(
        stored=True, message_id=message.id, conversation_id=message.conversation_id
    )
