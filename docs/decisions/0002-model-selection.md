# 0002 — Model selection and the provider abstraction

**Date:** 2026-09-08 · **Status:** accepted

## Context

The first draft named `gemini-2.5-flash` as primary and Groq
`llama-3.3-70b-versatile` as fallback. Verification on 2026-09-08 found that
`gemini-2.0-flash` is shut down, `gemini-2.5-*` is a generation behind, and Groq
deprecated `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` on 16 August 2026.

## Decision

- Reasoning and summarization: `gemini-3.8-flash`, falling back to Groq
  `openai/gpt-oss-120b`.
- Classification and verification: `gemini-3.5-flash-lite`, falling back to Groq
  `openai/gpt-oss-20b`.
- Evaluation judge: `openai/gpt-oss-120b` — deliberately a different provider from
  the system under test.
- Embeddings: local `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX, CPU, offline).
- All model ids live in `.env` and are read through `app/llm/registry.py`. They
  appear nowhere else in the codebase.

## Reasoning

Two providers were already necessary for rate-limit resilience; the deprecation
found during planning shows they are also necessary for *continuity*. Providers
give roughly two months' notice, which is shorter than this project's timeline.

Embeddings are local rather than API-based for a specific reason: re-embedding the
knowledge base is a bulk operation that must never fail because a quota was
exhausted, and it must work offline.

## Consequences

- Changing a model is a one-line config change, verifiable by running the eval
  harness before and after.
- Every eval report header must record the resolved model ids; a metric without
  its model id is not comparable across weeks.
- Provider deprecation pages get re-checked at the start of Stage 11, before the
  numbers that go in the final report are generated.
