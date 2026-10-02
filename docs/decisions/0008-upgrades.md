# 0008 — Upgrades: reranking, tracing, Presidio, progress events, LLM cache, prompt checks, e2e

**Date:** 2026-10-01 · **Status:** accepted · **Amends:** `0003-prototype-scope.md`

## Context

After the specialist agents (0006) and the fewer-handoffs work (0007), a
review listed eight upgrades. All eight were asked for. Two of them,
reranking and a trace UI, are listed as out of scope in 0003. This file
records why they are now in, and the choices made for each upgrade.

## Decisions

### 1. flashrank reranker over hybrid search

`app/rag/rerank.py`. Hybrid search now takes the top 20 RRF-fused candidates
and runs a cross-encoder (`ms-marco-TinyBERT-L-2-v2`, about 4MB, ONNX on the
CPU) over query and chunk together, then keeps the top `RETRIEVAL_FINAL_K`.

- **Why it is in now:** 0003 cut reranking because of time, not because it
  was a bad idea. It took one small module. The model runs locally, so it
  uses no API key and no quota.
- **Failure mode:** if the model can't load, reranking turns itself off for
  the process and retrieval uses plain RRF order.
- **Measured** by the `no_rerank` ablation in `make eval`.

### 2. Langfuse tracing, self-hosted, optional

`app/observability.py`, `docker-compose.langfuse.yml`, `make langfuse`.

- **Why it is in now:** 0003 ruled out *building* a trace UI. Langfuse is an
  existing one that we run rather than build. The integration is one
  callback handler in the graph config, so nothing in the nodes changes.
- **Off unless both `LANGFUSE_*` keys are set.**
- **Self-hosted,** so customer text never leaves the machine.
- **Not a replacement:** `agent_runs`, `agent_steps` and `tool_calls` stay
  the record of truth (non-negotiable #9). The console and the eval harness
  read those. Langfuse is a richer view for debugging prompts.
- **Verified 2026-10-02:** `make langfuse` starts it; real eval runs showed
  up as one trace per ticket with every Gemini call, its tokens and cost.

### 3. Presidio for PII, on top of the regex rules

`app/core/pii.py`.

- **Regex stays.** The regex rules for cards and OTPs still run first.
- **Presidio adds** spaCy NER plus pattern recognizers for names, emails,
  phone numbers, Aadhaar, PAN, IBAN and IPs.
- **Kept on purpose:**
  - Order and transaction references (`ORD-…`, `TXN-…`, `T-…`), because
    tools need them verbatim.
  - Locations, because "do you ship to Singapore?" needs the place.
- **Fallback:** if Presidio or the spaCy model fails, redaction falls back
  to regex only.
- **Known gap:** `en_core_web_sm` misses some Indian first names when they
  appear alone ("this is Rahul"). The small model is a speed and size trade.
  `PII_SPACY_MODEL=en_core_web_lg` is the fix if this matters.

### 4. Progress events, not token streaming

`app/agent/progress.py`, `useWebChat.ts`.

- **Why not token streaming:** it would send text to the customer before
  verify checks it. That breaks non-negotiable #5.
- **What happens instead:** the worker publishes short progress frames to
  the web chat over the existing Redis pub/sub channel, such as
  `{"type":"progress","stage":"specialist","agent":"orders","label":"Checking your order"}`.
  The verified reply still arrives whole as `{"type":"reply","text":…}`.
- **Customer-safe labels:** labels come from a fixed table, so tool names
  never reach the customer.
- **Scope:** only the worker and the console's "return to AI" path turn
  progress on. Tests and the eval harness never publish.
- **Failure mode:** a failed publish is logged and dropped.

### 5. Redis LLM cache, off for live traffic

`app/llm/cache.py`.

- **The key** is a hash of provider, model, the full prompt or message
  list, the tool schemas and the output schema.
- **Off by default.** Two customers can send the same words and need
  different answers. Hits would be rare live anyway.
- **Where it is on:**
  - `make eval`. Turn it off with `--no-cache` when you need latency
    numbers, since hits report 0ms.
  - The promptfoo provider.
- **The gain:** re-running 55 tickets after editing one prompt only spends
  quota on the calls that prompt changed.
- **Never caches the stub provider.**

### 6. promptfoo for prompt regression

`eval/promptfoo/`, `make promptfoo`.

- **What it checks:**
  - The real classify prompt against every case in `tickets.jsonl`, where
    the intent must match. The cases are generated, so the set grows with
    the dataset.
  - The real verify prompt against hand-written good and bad drafts.
- **How it runs:** the Python provider goes through `app/llm/registry.py`,
  so model ids stay in `.env`.
- **Cost:** one LLM call per case, with no DB and no graph. Much cheaper
  than `make eval` for checking a prompt edit.

### 7. Playwright end-to-end tests

`frontend/e2e/`, `make e2e`. These run against the Vite dev server with the
API mocked at the network layer, so they need no backend, no DB and no LLM.

They cover:

- the console flow: escalate, then claim, then return to AI;
- the approvals queue;
- chat progress frames.

They check that the UI is wired to the API contract, not that the agent
gives good answers. `make eval` covers that.

### 8. Fixable tool-argument errors

`app/tools/registry.py`.

- **What changed:** a tool call with bad arguments now comes back to the
  model as `{"error": "invalid_arguments", "fields": [...],
  "expected_schema": {...}}`. Before, it was a generic error string. The
  model can fix the named field on its next round.
- **Budget:** that retry counts against `MAX_TOOL_CALLS`, so the loop stays
  bounded.
- **Provider-side rejections** (Groq `tool_use_failed`) were already retried
  by the registry's retry loop. That is unchanged.
- **Why not pydantic-ai:** the tools are already Pydantic-validated
  LangChain tools, so adding pydantic-ai would mean two agent frameworks for
  one gain.

## Consequences

- **New dependencies:** `flashrank`, `presidio-analyzer`,
  `presidio-anonymizer`, `en-core-web-sm` (pinned wheel URL), `langfuse` and
  `langchain` (needed by Langfuse's LangChain handler). On the frontend:
  `@playwright/test`.
- **First run downloads:** the first reranker call downloads its model to
  `~/.cache/flashrank`. Without network on that first run, reranking stays
  off.
- **Wire format change:** WS reply frames now carry `"type": "reply"`. The
  frontend still accepts the old untyped `{"text"}` frame.
- **0003's out-of-scope list** should be read with this file. Skill-based
  routing, the SLA cron, CI, mypy and load testing are still out.
