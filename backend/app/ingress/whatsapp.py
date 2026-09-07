"""WhatsApp (Twilio) ingress: verifies the request actually came from
Twilio, normalizes the form-encoded webhook body, and runs it through the
same ingest_message pipeline every channel uses. Acknowledges fast (an
empty 200) and does the real work off the request path, same contract as
every other channel's ingress.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator

from app.channels.whatsapp import WhatsAppAdapter
from app.config import settings
from app.db.session import get_session
from app.ingress.pipeline import ingest_message
from app.logging import get_logger
from app.models import Message
from app.workers.queue import enqueue_handle_message

router = APIRouter(prefix="/channels/whatsapp", tags=["channels"])
logger = get_logger(__name__)


def verify_signature(path: str, form: dict, signature: str | None) -> bool:
    """Split from the route handler (taking a plain path instead of a
    Request) so it's unit-testable without constructing an ASGI request.
    """
    if not settings.twilio_validate_signature:
        return True
    if not signature:
        return False
    validator = RequestValidator(settings.twilio_auth_token)
    # Twilio signs the URL it believes it POSTed to - behind a tunnel, that's
    # the public tunnel URL, not whatever FastAPI sees internally. Reconstruct
    # it from PUBLIC_BASE_URL rather than trusting request.url, which a proxy
    # can rewrite.
    public_url = f"{settings.public_base_url.rstrip('/')}{path}"
    return validator.validate(public_url, form, signature)


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    form = dict((await request.form()).items())
    signature = request.headers.get("X-Twilio-Signature")

    if not verify_signature(request.url.path, form, signature):
        logger.warning("whatsapp_signature_invalid", from_=form.get("From"))
        raise HTTPException(403, "invalid Twilio signature")

    adapter = WhatsAppAdapter()
    inbound = await adapter.parse(form)

    message = await ingest_message(
        session,
        channel=inbound.channel,
        external_thread_id=inbound.external_thread_id,
        sender_external_id=inbound.sender_external_id,
        text=inbound.text,
        external_message_id=inbound.external_message_id,
        raw_payload=form,
    )
    await session.commit()

    if message is not None:
        await enqueue_handle_message(message.id)

    # Empty 200, not TwiML - the reply goes out later, asynchronously,
    # through WhatsAppAdapter.send() once the worker has actually processed
    # the message. Twilio only needs to know we received it.
    return Response(status_code=200)


@router.post("/status")
async def whatsapp_status_callback(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    """Delivery-status tracking for outbound messages: Twilio calls this as
    a sent message moves queued -> sent -> delivered (or -> failed /
    undelivered). Matched back to the Message row via the provider SID
    stashed in external_message_id when WhatsAppAdapter.send() succeeded.
    """
    form = dict((await request.form()).items())
    signature = request.headers.get("X-Twilio-Signature")
    if not verify_signature(request.url.path, form, signature):
        logger.warning("whatsapp_status_signature_invalid")
        raise HTTPException(403, "invalid Twilio signature")

    message_sid = form.get("MessageSid")
    status = form.get("MessageStatus")
    if message_sid and status:
        message = (
            await session.execute(
                select(Message).where(
                    Message.channel == "whatsapp", Message.external_message_id == message_sid
                )
            )
        ).scalar_one_or_none()
        if message is not None:
            message.delivery_status = status
            await session.commit()

    return Response(status_code=200)
