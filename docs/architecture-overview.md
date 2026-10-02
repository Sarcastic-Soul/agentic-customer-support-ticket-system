# Architecture overview

A short, high-level tour of how the system answers a customer. For the full
detail see `01-architecture.md` and `04-agent-design.md`. The detailed diagram is
`architecture.svg`.

![How a support message gets answered](architecture-overview.svg)

Source: `architecture-overview.d2`. To rebuild the picture:

```bash
d2 docs/architecture-overview.d2 docs/architecture-overview.svg
```

## The big idea

A customer writes in on any channel. An AI agent tries to fix the problem using
real order, payment and delivery data. If it can't or shouldn't fix it, it hands
the ticket to a human with everything they need, and the human can hand it back.

Three rules shape everything below:

1. **One brain, many channels.** Web chat, WhatsApp, email and voice all feed the
   same AI agent. The channels only translate messages in and out. They contain
   no AI.
2. **The AI suggests, the code decides.** The AI can ask for a refund, but plain
   code checks the limits and approves it or not. Nothing the AI says can get
   past those rules.
3. **Handing off to a human is a valid outcome.** A good handoff counts as a
   success, not a failure.

## The journey of one message

### 1. Channels

The customer sends a message on web chat, WhatsApp, email or a voice note.
Each channel turns its own format (a Twilio webhook, an email, an audio file)
into one standard message shape. Voice notes are turned into text first.

### 2. Intake

Intake does three quick things and no AI work:

- **Saves the raw message** right away, so a crash never loses it.
- **Drops duplicates.** Twilio retries webhooks and email can arrive twice. A
  database rule (`UNIQUE (channel, external_message_id)`) makes sure the
  customer is answered once, not three times.
- **Puts the message in a queue** (Redis + `arq`) and replies "got it" to the
  provider at once.

It also works out who the customer is and which ticket the message belongs to.
Personal details such as phone numbers and card numbers are hidden before any
text reaches the AI.

A separate worker process picks the message off the queue and runs the AI
agent. That way a slow AI call never holds up the webhook.

### 3. The AI agent

This is the agentic part. It's a LangGraph state machine: a fixed set of steps
with clear rules about which step comes next. The AI does language and judgement
inside the steps. The order of the steps, and every rule that matters, is plain
code.

| Step | What happens | AI or code? | Code name |
|---|---|---|---|
| 1. Understand | Reads recent history and works out what the customer wants (e.g. "where is my order" + "refund the double charge"), and how sure it is. | AI | `prepare`, `classify` |
| 2. Safety check | Mentions of legal action, signs of distress, or "let me talk to a human" go straight to a person. If the AI isn't sure what the customer means, it asks one clear question instead (up to 2 in a row). | Code | `hard_route` |
| 3. Pick the experts | A fixed table maps what the customer wants to one or two experts. No AI guessing, so it is always clear who handled what. | Code | `supervisor` |
| 4. Search help articles | Finds the relevant policy and help text (e.g. the refund policy) using keyword and meaning-based search. | Code + search | `retrieve` |
| 5. Experts work | One or two experts run **at the same time**, each limited to its own area and its own tools (see below). They look up real data and **propose** actions. They change nothing. | AI | `specialist` |
| 6. Settle disagreements | If experts disagree (e.g. one wants to cancel the order, the other wants to refund it, which would pay the customer twice), a rule table in code picks the winner. | Code | `reconcile` |
| 7. Carry out actions | Does the actions that survived. Every rule is checked **again** against fresh data before anything changes. | Code | `commit` |
| 8. Write the reply | Drafts the answer from the data and help articles, in the right style for the channel (short and plain for WhatsApp and voice). | AI | `answer` |
| 9. Fact-check | A second AI pass checks that every claim in the draft is backed by the data or help articles. If not, it sends it back to step 8 with notes, up to 2 times. | AI | `verify` |

If the reply passes the fact-check, it goes back to the customer on the same
channel they used (`respond`).

### The three experts

Experts are split by **area of work**, not by channel.

| Expert | Handles | Can use |
|---|---|---|
| **Orders** | cancel, change, return an order | order lookup, cancellation and return eligibility, request a cancellation, start a return |
| **Delivery** | where is my order, late or damaged parcel | order lookup, shipment tracking, open a carrier investigation, returns |
| **Payments** | refund status, refund request, failed payment, invoices, billing disputes | transaction lookup, refund status, explain a failed payment, request a refund, make an invoice |

General questions ("what is your return policy?") don't need an expert. Step 4
answers them from the help articles.

A message that asks for two things ("where is my parcel, and why was I charged
twice?") gets two experts working side by side. They share the lookup budget.

### 4. Business tools and hard rules

Experts never touch the database directly. They call business tools, and each
tool:

- **Only sees this customer's data.** The customer's id comes from the ticket,
  never from what the AI typed. So if someone writes "show me order ORD-99999"
  for an order that isn't theirs, the tool simply finds nothing.
- **Reads eligibility from data, not from the AI.** Whether an order can still be
  cancelled or returned comes from stored dates and flags
  (`orders.cancellable_until`, `orders.return_window_ends`,
  `order_items.returnable`). The AI never decides if a window is open.
- **Goes through `authorize()`** for anything that changes something. It returns
  *allow*, *needs a human* or *deny*. For example, refunds above the
  automatic limit (1000 by default) are never approved by the AI.

A refund that needs approval doesn't hand the whole conversation to a human. It
waits in an **approval queue**. The AI tells the customer it is waiting, and a
person approves or rejects it with one click.

### 5. Handing off to a human

The agent hands the ticket to a person when:

- the safety check fires (legal, distress, asked for a human),
- the customer stays unclear after 2 questions,
- the experts disagree in a way no rule covers,
- the reply still fails the fact-check after 2 fixes,
- or the ticket has gone back and forth with the AI too many times (4 turns).

When that happens the agent builds a **handoff packet** (summary, the
customer's data, what the AI tried, a suggested reply), tells the customer
someone will help, and **pauses**. Its full state is saved in Postgres.

The human then either:

- **replies directly** through the same channel, so the customer sees one
  continuous conversation, or
- **hands it back to the AI with a note** ("the refund is approved, let them
  know"). The agent picks up exactly where it paused and writes the reply using
  the note.

## Safety limits

- **At most 5 tool lookups per message** and **4 AI turns per ticket**. An
  agent that loops forever burns through a free AI quota in under a minute.
- **The fact-check step always runs.** Nothing reaches a customer unchecked.
- **AI model names live only in `.env`.** Providers retire models often. The
  agent uses Gemini first and falls back to Groq if Gemini keeps failing.

## Everything is recorded

Every run, every step and every tool call is saved (`agent_runs`,
`agent_steps`, `tool_calls`), with timings and token counts. That powers the
"why did the AI do that?" screen in the admin console, and the evaluation
harness (`eval/run_eval.py`) grades the agent from the same tables.

## Where to look in the code

| Part | Location |
|---|---|
| Channels | `backend/app/channels/` |
| Intake | `backend/app/ingress/`, `backend/app/core/` |
| Queue and worker | `backend/app/workers/` |
| The AI agent's steps | `backend/app/agent/graph.py`, `backend/app/agent/nodes/` |
| Experts and their tools | `backend/app/agent/specialists.py` |
| Prompts | `backend/app/agent/prompts/` |
| Business tools | `backend/app/tools/` |
| Rules (`authorize()`, disagreements, safety triggers) | `backend/app/policy/` |
| Frontend (chat, console, admin) | `frontend/src/routes/` |
