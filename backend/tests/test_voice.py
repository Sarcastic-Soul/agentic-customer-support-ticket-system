"""VoiceAdapter and the generic ResponseStyle formatting it exercises.
transcribe() itself talks to a real API and is verified live (see
docs/PROGRESS.md Stage 10), not re-verified here - these mock it, same
convention as the graph tests mocking the LLM.
"""

from unittest.mock import AsyncMock

import pytest

from app.channels.base import OutboundMessage, ResponseStyle, format_for_style
from app.channels.voice import VoiceAdapter
from app.voice.stt import TranscriptionError


async def test_parse_transcribes_audio_into_text(monkeypatch):
    monkeypatch.setattr(
        "app.channels.voice.transcribe", AsyncMock(return_value="where is my order")
    )
    adapter = VoiceAdapter(redis=AsyncMock())

    inbound = await adapter.parse(
        {"session_id": "sess-1", "audio_bytes": b"fake", "content_type": "audio/webm"}
    )

    assert inbound.channel == "voice"
    assert inbound.external_thread_id == "sess-1"
    assert inbound.sender_external_id == "sess-1"
    assert inbound.text == "where is my order"


async def test_parse_propagates_transcription_failure(monkeypatch):
    monkeypatch.setattr(
        "app.channels.voice.transcribe",
        AsyncMock(side_effect=TranscriptionError("empty audio")),
    )
    adapter = VoiceAdapter(redis=AsyncMock())

    with pytest.raises(TranscriptionError):
        await adapter.parse(
            {"session_id": "sess-1", "audio_bytes": b"", "content_type": "audio/webm"}
        )


async def test_send_publishes_to_the_same_ws_channel_web_uses():
    redis = AsyncMock()
    adapter = VoiceAdapter(redis=redis)

    receipt = await adapter.send(
        OutboundMessage(channel="voice", external_thread_id="sess-1", text="hi")
    )

    assert receipt.ok is True
    redis.publish.assert_called_once()
    channel_name = redis.publish.call_args.args[0]
    assert channel_name == "ws:web:sess-1"


def test_style_is_short_plain_and_no_markdown():
    style = VoiceAdapter(redis=AsyncMock()).style()
    assert style.markdown is False
    assert style.max_length <= 400


def test_format_for_style_strips_markdown_and_urls_when_disallowed():
    style = ResponseStyle(max_length=1000, markdown=False)
    text = "See **our policy** [here](https://example.com/policy) for details."

    formatted = format_for_style(text, style)

    assert "**" not in formatted
    assert "http" not in formatted
    assert "here" in formatted  # link label kept, URL dropped


def test_format_for_style_leaves_markdown_untouched_when_allowed():
    style = ResponseStyle(max_length=1000, markdown=True)
    text = "See **our policy** [here](https://example.com/policy)."

    assert format_for_style(text, style) == text


def test_format_for_style_truncates_to_max_length():
    style = ResponseStyle(max_length=20, markdown=True)
    text = "a" * 50

    formatted = format_for_style(text, style)

    assert len(formatted) == 20
    assert formatted.endswith("…")
