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


class SimulateResponse(BaseModel):
    stored: bool
    message_id: int | None = None
    conversation_id: int | None = None


@router.post("/simulate/web", response_model=SimulateResponse)
async def simulate_web_message(
    body: SimulateWebMessage, session: AsyncSession = Depends(get_session)
) -> SimulateResponse:
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
        return SimulateResponse(stored=False)

    await enqueue_handle_message(message.id)
    return SimulateResponse(
        stored=True, message_id=message.id, conversation_id=message.conversation_id
    )


class SimulateWhatsAppMessage(BaseModel):
    phone: str  # E.164, e.g. '+919800000001' - no 'whatsapp:' prefix
    text: str
    external_message_id: str | None = None


@router.post("/simulate/whatsapp", response_model=SimulateResponse)
async def simulate_whatsapp_message(
    body: SimulateWhatsAppMessage, session: AsyncSession = Depends(get_session)
) -> SimulateResponse:
    """Exercises the exact same ingest path the real /channels/whatsapp/webhook
    does (identity resolution, dedupe, threading), without Twilio, a tunnel,
    or a phone - see docs/PROGRESS.md Stage 7 for why the real phone test is
    a manual step instead of an automated one.
    """
    external_message_id = body.external_message_id or str(uuid.uuid4())

    message = await ingest_message(
        session,
        channel="whatsapp",
        external_thread_id=body.phone,
        sender_external_id=body.phone,
        text=body.text,
        external_message_id=external_message_id,
        raw_payload=body.model_dump(),
    )
    await session.commit()

    if message is None:
        return SimulateResponse(stored=False)

    await enqueue_handle_message(message.id)
    return SimulateResponse(
        stored=True, message_id=message.id, conversation_id=message.conversation_id
    )
