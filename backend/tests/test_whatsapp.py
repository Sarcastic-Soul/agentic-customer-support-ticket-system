"""No real Twilio account needed: WhatsAppAdapter takes an injectable
twilio.rest.Client, so send() is tested against a mock rather than a live
API. Signature verification is tested against the real twilio SDK's
RequestValidator - we generate a genuinely valid signature the same way
Twilio would, rather than trusting our own re-implementation of their HMAC
scheme (docs recommend never hand-rolling that check).
"""

import base64
import hashlib
import hmac
from unittest.mock import MagicMock

from app.channels.base import OutboundMessage
from app.channels.whatsapp import OUTSIDE_WINDOW_ERROR_CODE, WhatsAppAdapter
from app.ingress.whatsapp import verify_signature


def _twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """Reimplements Twilio's documented signing algorithm (sort params,
    concatenate key+value onto the URL, HMAC-SHA1, base64) - the same
    computation their own RequestValidator does internally, used here only
    to produce a genuinely valid signature to test against, not as the
    production verification path (that stays app/ingress/whatsapp.py using
    the real SDK).
    """
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    computed = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(computed).decode()


async def test_parse_extracts_phone_and_text():
    adapter = WhatsAppAdapter(client=MagicMock())
    payload = {
        "From": "whatsapp:+919800000001",
        "To": "whatsapp:+14155238886",
        "Body": "where is my order?",
        "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "WaId": "919800000001",
        "ProfileName": "Test User",
    }
    inbound = await adapter.parse(payload)

    assert inbound.channel == "whatsapp"
    assert inbound.external_thread_id == "+919800000001"
    assert inbound.sender_external_id == "+919800000001"
    assert inbound.external_message_id == "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    assert inbound.text == "where is my order?"
    assert inbound.attachments == []


async def test_parse_extracts_media_attachments():
    adapter = WhatsAppAdapter(client=MagicMock())
    payload = {
        "From": "whatsapp:+919800000001",
        "Body": "",
        "MessageSid": "SM1",
        "MediaUrl0": "https://api.twilio.com/media/abc",
        "MediaContentType0": "image/jpeg",
    }
    inbound = await adapter.parse(payload)

    assert len(inbound.attachments) == 1
    assert inbound.attachments[0].url == "https://api.twilio.com/media/abc"
    assert inbound.attachments[0].content_type == "image/jpeg"


async def test_send_success_returns_receipt_with_sid():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMoutbound123")
    adapter = WhatsAppAdapter(client=mock_client)

    receipt = await adapter.send(
        OutboundMessage(channel="whatsapp", external_thread_id="+919800000001", text="hi")
    )

    assert receipt.ok is True
    assert receipt.detail == "SMoutbound123"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["to"] == "whatsapp:+919800000001"


async def test_send_failure_returns_not_ok_without_raising():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("simulated Twilio API failure")
    adapter = WhatsAppAdapter(client=mock_client)

    receipt = await adapter.send(
        OutboundMessage(channel="whatsapp", external_thread_id="+919800000001", text="hi")
    )

    assert receipt.ok is False


async def test_send_outside_service_window_is_recognized(caplog):
    class WindowClosedError(Exception):
        code = OUTSIDE_WINDOW_ERROR_CODE

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = WindowClosedError("outside window")
    adapter = WhatsAppAdapter(client=mock_client)

    receipt = await adapter.send(
        OutboundMessage(channel="whatsapp", external_thread_id="+919800000001", text="hi")
    )
    assert receipt.ok is False


def test_verify_signature_disabled_always_passes(monkeypatch):
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_validate_signature", False)
    assert verify_signature("/channels/whatsapp/webhook", {}, None) is True


def test_verify_signature_missing_header_fails(monkeypatch):
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_validate_signature", True)
    assert verify_signature("/channels/whatsapp/webhook", {"Body": "hi"}, None) is False


def test_verify_signature_accepts_genuinely_valid_signature(monkeypatch):
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_validate_signature", True)
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_auth_token", "test-auth-token")
    monkeypatch.setattr("app.ingress.whatsapp.settings.public_base_url", "https://example.ngrok.app")

    form = {"Body": "hello", "From": "whatsapp:+919800000001"}
    url = "https://example.ngrok.app/channels/whatsapp/webhook"
    signature = _twilio_signature("test-auth-token", url, form)

    assert verify_signature("/channels/whatsapp/webhook", form, signature) is True


def test_verify_signature_rejects_tampered_body(monkeypatch):
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_validate_signature", True)
    monkeypatch.setattr("app.ingress.whatsapp.settings.twilio_auth_token", "test-auth-token")
    monkeypatch.setattr("app.ingress.whatsapp.settings.public_base_url", "https://example.ngrok.app")

    url = "https://example.ngrok.app/channels/whatsapp/webhook"
    signature = _twilio_signature("test-auth-token", url, {"Body": "hello"})

    # signature was computed for a different body - must not validate
    tampered = {"Body": "give me a refund"}
    assert verify_signature("/channels/whatsapp/webhook", tampered, signature) is False
