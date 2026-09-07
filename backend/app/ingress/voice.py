"""Voice channel ingress: a REST upload endpoint for the web widget's
record button. Unlike Twilio/IMAP this is our own frontend calling our own
API directly - no provider signature to verify and no retry storm to guard
against - but it goes through the same ingest_message pipeline and worker
hand-off every other channel uses.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.voice import VoiceAdapter
from app.config import settings
from app.db.session import get_session
from app.ingress.pipeline import ingest_message
from app.logging import get_logger
from app.voice.stt import TranscriptionError
from app.workers.queue import enqueue_handle_message

router = APIRouter(prefix="/channels/voice", tags=["channels"])
logger = get_logger(__name__)


@router.post("/upload")
async def voice_upload(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not settings.voice_enabled:
        raise HTTPException(404, "voice channel is disabled")

    audio_bytes = await file.read()

    adapter = VoiceAdapter()
    try:
        inbound = await adapter.parse(
            {
                "session_id": session_id,
                "audio_bytes": audio_bytes,
                "content_type": file.content_type or "audio/webm",
                "external_message_id": str(uuid.uuid4()),
            }
        )
    except TranscriptionError as exc:
        logger.warning("voice_transcription_failed", session_id=session_id, error=str(exc))
        raise HTTPException(502, "could not transcribe voice note - please try again") from exc

    message = await ingest_message(
        session,
        channel=inbound.channel,
        external_thread_id=inbound.external_thread_id,
        sender_external_id=inbound.sender_external_id,
        text=inbound.text,
        external_message_id=inbound.external_message_id,
        raw_payload=inbound.raw,
    )
    await session.commit()

    if message is not None:
        await enqueue_handle_message(message.id)

    return {"transcript": inbound.text}
