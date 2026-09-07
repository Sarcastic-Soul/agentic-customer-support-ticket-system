# Review of the Original Plan

This document records what was wrong or under-specified in the first draft (the
hand-drawn architecture and the two-phase feature list) and what replaces it.
Everything after this document assumes the corrected design.

## The original diagram

```
Input channel (WhatsApp / Voice / Mail)
        |
      Router
        |
  +-----+-----+-------------+
  |     |     |             |
Ticket  WhatsApp  Voice   Mail        -> each with its own agent
agent   agent     agent   agent
  |     +-----+-----+-------+
Ticket        |
  DB      Master agent  <---> human in loop
              |
  +-----------+-----------+
Transaction  Order      Q/A
agent        agent      agent
  |            |          |
Txn DB      Order DB    Q/A DB
```

## Problem 1 — Per-channel agents are the wrong decomposition

The diagram gives WhatsApp, Voice and Mail each their own agent. But the channel
does not change how you reason about a customer's problem. "Where is my order"
requires the same retrieval, the same order lookup and the same escalation rules
whether it arrived over WhatsApp or email. Building three agents means writing
the same reasoning three times and fixing every bug three times.

What actually differs per channel is narrow and mechanical:

| Concern | WhatsApp | Email | Voice |
|---|---|---|---|
| Message length budget | short, ~1000 chars | long, formatted | very short, spoken |
| Formatting | plain text, minimal markdown | HTML/plain body, subject line, quoting | SSML / plain sentences |
| Latency budget | seconds | minutes to hours | sub-second turns |
| Threading key | phone number + session window | `Message-ID` / `In-Reply-To` | call SID |
| Attachments | media URLs | MIME parts | audio blobs |

**Fix:** channels become *adapters*, not agents. An adapter has no LLM in it. It
translates a provider payload into one canonical `InboundMessage` and renders one
canonical `AgentReply` back into the provider's format. A single channel-agnostic
orchestrator sits behind all of them, and receives the channel only as a
`response_style` hint (max length, formatting, latency budget).

## Problem 2 — Two routers with unclear responsibilities

There is a "Router" before the channel agents and a "Master agent" after them.
Nothing in the plan says what each decides, and in the drawing the master agent
is both the thing that calls domain agents and the thing that talks to the human
queue. That is two different jobs (intent dispatch vs. conversation control)
merged into one box.

**Fix:** one orchestrator, expressed as an explicit state graph, with named
nodes that each do exactly one thing (resolve identity, classify, retrieve, act,
verify, respond, escalate). "Routing" is one node inside that graph, not a
separate service. See `04-agent-design.md`.

## Problem 3 — Four separate databases

The diagram shows Ticket DB, Txn DB, Order DB and Q/A DB as separate stores.
For this project that buys nothing and costs a lot: no joins, no foreign keys,
no transactional consistency, four connection pools, four migration paths, and
you cannot answer "show me every ticket from the customer who filed refund
#4412" without application-level joins.

**Fix:** one PostgreSQL instance. Separate *tables* (and optionally separate
schemas `support`, `commerce`, `kb`) inside it. The only genuinely different
storage need is the vector index for retrieval, and `pgvector` provides that in
the same database — so a retrieved knowledge-base chunk can be joined against
the ticket that cited it.

## Problem 4 — "Ticket agent" is not an agent

Ticket creation, status transitions and assignment are deterministic state
management. Putting an LLM in that path adds latency, cost and the possibility
of a hallucinated state transition, and buys nothing.

**Fix:** ticket lifecycle is a plain service with an explicit state machine.
The LLM may *call tools* that request a transition (`escalate_ticket`,
`resolve_ticket`), but the service validates and applies it.

## Problem 5 — Human-in-the-loop is a single arrow

The drawing has one arrow from the master agent to "human in loop" and one back
to the input channel. That is the hardest part of the whole project drawn as a
line. It leaves undefined: how a human is chosen, what context they receive,
how they reply into the same customer thread, what happens to messages that
arrive while a human owns the ticket, and how control returns to the AI.

**Fix:** a first-class handoff subsystem — an escalation queue, a structured
**handoff packet** (summary, timeline, entities, what the AI already tried and
why it stopped, suggested reply draft, links to the order/transaction records),
an agent console with claim/assign, and an explicit resume path. The graph pauses
at an interrupt point and resumes from the same state when the human is done.
See `05-escalation-policy.md`.

## Problem 6 — Missing infrastructure the system cannot work without

None of these appear in the original plan, and each one will break a demo:

1. **Identity resolution.** A WhatsApp message carries a phone number, an email
   carries an address. Neither is a customer ID. You need a `customer_identities`
   table mapping `(channel, external_id) -> customer_id`, and a defined behaviour
   for unknown senders.
2. **Idempotency and deduplication.** Twilio retries webhooks. IMAP will hand you
   the same message twice after a reconnect. Without a dedupe key you will reply
   to the same customer three times.
3. **Action authorization.** An LLM must never be able to issue a refund on its
   own judgement. Money-moving and destructive tools need policy limits
   (amount ceilings, order-age windows) enforced in code, plus mandatory human
   approval above the threshold.
4. **Audit trail.** Every state change, tool call and LLM decision needs a row.
   This is both a grading artifact and the only way to debug an agent.
5. **Failure paths.** What happens when Gemini times out, when the free tier rate
   limit hits, when a tool raises, when retrieval returns nothing. Right now the
   answer is "the customer gets silence."
6. **Grounding and hallucination control.** A support bot that invents a refund
   policy is worse than no bot. Answers must cite retrieved chunks and be checked
   against them.
7. **PII handling.** Do not send raw card numbers or full addresses to a
   third-party LLM. Redact before the prompt, re-inject after.
8. **Evaluation.** With no test set you cannot claim the system works. This is
   the single biggest difference between a demo and a project.

## Problem 7 — Phase ordering puts the hardest channel early and the core late

The draft has WhatsApp, email, transaction and order agents all in Phase I, and
the human-in-the-loop pipeline, the dashboard and the escalation workflow in
Phase II. That is backwards. The escalation loop *is* the thesis of the project;
three channels are variations on plumbing. If Phase II slips you are left with a
chatbot, not an agentic support system.

**Fix (reflected in `07-build-stages.md`):** build the full vertical slice first
— one channel, one domain tool, the orchestrator, escalation, and a minimal human
console — end to end. Then add channels and domains outward. Every stage after
stage 2 leaves you with something demonstrable.

## Problem 8 — Voice was scheduled too early

Voice needs streaming STT, turn detection, barge-in handling and a latency budget
an order of magnitude tighter than chat. It is a project on its own.

**Fix:** voice is explicitly deferred to the last stage and scoped down to
asynchronous voice notes (upload/record audio -> transcribe -> normal pipeline ->
optional spoken reply), not a live phone call. Real-time telephony is listed as a
stretch goal, not a deliverable.

## What survives from the original plan

Most of it, in a different shape:

- Multi-channel ingress — kept, as adapters.
- Intent routing — kept, as a node.
- Domain agents for orders / transactions / knowledge — kept, but as **tool
  groups under one orchestrator**, not independent agents with their own databases.
- Tickets, conversations, customers, orders, transactions schema — kept and
  expanded.
- RAG over an FAQ/knowledge base — kept, upgraded to hybrid search with citations.
- Human in the loop — kept and promoted to the centre of the design.
- Admin dashboard with metrics — kept, plus a working agent console.
