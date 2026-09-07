# 0005 — Voice STT goes straight to the Groq API fallback, not local models

**Date:** 2026-09-08 · **Status:** accepted

## Context

`docs/02-tech-stack.md` specifies a three-tier STT design for Stage 10: NVIDIA
Parakeet TDT 0.6B v3 local primary, `faster-whisper` (`distil-large-v3`) local
fallback for other languages, and Groq's hosted `whisper-large-v3` only "if
local inference is too slow on the demo machine". `config.py` already
scaffolds all three (`stt_primary`, `stt_fallback`, `stt_api_fallback`).

Measured on the actual build machine before writing any code: `free -h`
showed **~650MB free RAM with ~4.7GB of swap already in use**, and no GPU
(`nvidia-smi` not found). Parakeet TDT needs the NeMo toolkit (pulls in torch
and several GB of dependencies); `distil-large-v3` via `faster-whisper` is
lighter (`ctranslate2`, no torch) but still a few hundred MB of model weights
plus real CPU inference time, on a box that is already swapping under its
current load. Loading either into the same long-lived `uvicorn`/`arq`
processes that also hold two DB connection pools each risked OOM-killing the
whole stack, not just failing slowly.

## Decision

Implemented STT as a single function, `app/voice/stt.transcribe()`, that
calls Groq's `/openai/v1/audio/transcriptions` endpoint with
`settings.stt_api_fallback` (`whisper-large-v3`), reusing the same
`groq_api_key` already configured for LLM calls. No local model, no new heavy
dependency (`httpx` was already a dependency). Verified live against the real
Groq API with a synthesized speech clip - transcription round-trip works and
returns correct text.

`stt_primary` and `stt_fallback` are left as documented-but-unimplemented
config, same as this project already tolerates `reranker_enabled` existing
before it's wired up. Not a redesign of the documented architecture - the
docs already named the API path as the sanctioned fallback for exactly this
situation, this just uses it as the primary path given the measured
constraints of this machine, rather than as a rarely-hit escape hatch.

## Consequences

- Voice notes require a working internet connection and `GROQ_API_KEY` to be
  set; `voice_enabled=False` by default keeps this fully opt-in, matching
  `email_enabled`'s pattern.
- No offline/air-gapped voice demo path exists. If that's ever needed, the
  `stt_primary`/`stt_fallback` config fields are already there to swap in a
  local engine behind the same `transcribe()` signature - on a machine that
  actually has the RAM and, ideally, a GPU for it.
- This machine's resource numbers are a point-in-time measurement, not a
  permanent property of "the demo machine" in general - re-measure before
  assuming this decision still holds on different hardware.
