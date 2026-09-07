"""Speech-to-text for voice notes.

docs/02-tech-stack.md's stated design is Parakeet TDT local primary, a
faster-whisper local fallback, and Groq's hosted whisper-large-v3 only as a
last resort "if local inference is too slow on the demo machine". This
build machine measures under 1GB free RAM with swap already in heavy use
and no GPU - local inference of either model is not practical here, so this
goes straight to that documented API fallback. See
docs/decisions/0004-voice-stt-groq-fallback.md.
"""

import httpx

from app.config import settings

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class TranscriptionError(RuntimeError):
    pass


async def transcribe(audio_bytes: bytes, content_type: str) -> str:
    if not settings.groq_api_key:
        raise TranscriptionError("voice transcription requires GROQ_API_KEY to be set")

    ext = (content_type or "audio/webm").split("/")[-1].split(";")[0] or "webm"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            data={"model": settings.stt_api_fallback},
            files={"file": (f"voice-note.{ext}", audio_bytes, content_type or "audio/webm")},
        )

    if response.status_code != 200:
        raise TranscriptionError(
            f"groq transcription failed: {response.status_code} {response.text}"
        )

    text = response.json().get("text", "").strip()
    if not text:
        raise TranscriptionError("transcription returned empty text")
    return text
