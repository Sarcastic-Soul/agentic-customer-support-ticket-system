# Final report

## In one paragraph

A support system where a customer writes in on web chat, WhatsApp, email or a
voice note, and AI agents try to actually fix the problem using real order,
delivery and payment data. Specialist agents (orders, delivery, payments) work
side by side and only *propose* actions; plain code checks the rules, settles
disagreements and carries out what is safe. Every reply is fact-checked before
it is sent. When the AI can't or shouldn't finish, a person gets the ticket with
a full case file and can hand it back. How it works:
[`architecture-overview.md`](architecture-overview.md) and
[`agent-orchestration.md`](agent-orchestration.md).

## What was built

| Area | What works |
|---|---|
| Channels | Web chat (live progress), WhatsApp (Twilio), email (Gmail IMAP/SMTP), voice notes (Groq Whisper). All tested with simulators; real WhatsApp and email need your own accounts. |
| Intake | Raw message saved first, duplicates dropped by a database rule, personal details hidden (Presidio + regex), queue + worker so webhooks answer at once. |
| AI agents | LangGraph flow with three specialists running in parallel, a conflict rule table, double-checked actions, a fact-check step with up to 2 rewrites, clarifying questions before handoff. |
| Knowledge | Help-article search by meaning and keyword, then a local reranker. |
| People | Console with a handoff queue, one-click refund approvals, direct replies, and "return to AI with a note" that resumes the paused agent. |
| Admin | Ticket list with the AI's step-by-step reasoning, metrics (per agent too), help-article editor, staff login. |
| Quality | 249 backend tests, 26 browser tests (Playwright), prompt checks (promptfoo), a 55-ticket evaluation harness with ablations. |
| Tracing | Every run, step and tool call saved in Postgres. Optional self-hosted Langfuse shows every prompt and response. |

## Results

55 test tickets, real models (Gemini answers, Groq judges), run on
2026-10-02. 53 of 55 pass every check.

| Measure | Result |
|---|---|
| Right outcome (answered, asked, or handed off as expected) | 98% |
| Solved by the AI without a person | 98% |
| Handed to a person | 6% |
| Tickets that needed a person and got one | 100% |
| Reply backed by the data (groundedness) | 98% |
| Replies with a made-up fact | 2% (1 ticket) |
| Right tools used | 93% |
| Cost per ticket | $0.0017 |
| Median reply time, live calls | about 6 seconds |

Intent labels match only 67% of the time, but almost all misses are a sibling
label owned by the same specialist (`refund_status` vs `refund_request`), so
the outcome is the same.

**What the first full run found** (15 of 55 failed):

- Two real bugs, now fixed: web chat customers weren't linked to their seeded
  account, so they had no orders; and the eligibility tools said "yes" without
  the deadline, so "until when?" couldn't be answered from data.
- The fact-check rejected honest "we don't have that information" replies. Its
  instructions now allow that when the help articles really don't cover it.
- Some test checks were too strict, not the agent. Policy-gap tickets now also
  accept a plain "we don't offer that", trick-prompt tickets also accept a
  clarifying question, and a few keyword checks that banned correct wording
  were fixed. All in `eval/dataset/tickets.jsonl`.

**Still failing:** a double-charge policy question gets an "which order?"
question instead of the policy, and a gift-return question with no matching
help article goes to a person instead of an honest "we don't know". Both are
safe, just less helpful than they could be.

Langfuse was also checked end to end: every ticket shows up as one trace with
each AI call, its tokens and cost.

## Decisions worth knowing

Each has a short file in [`decisions/`](decisions/).

- **Specialists split by area of work, not by channel** (0006). One brain for
  every channel; specialists keep each AI call small and focused.
- **Agents propose, code commits** (0006). Disagreements are settled before
  anything changes, by rules anyone can read and test.
- **Fewer handoffs** (0007). Ask a question first, send refunds to an approval
  queue, open carrier investigations. A person is pulled in only when one is
  really needed.
- **Keep the structure, tolerate rough edges** (0003). Queue, migrations, audit
  tables, PII hiding and the fact-check stayed even under time pressure. Polish
  did not.
- **Model names only in `.env`** (0002). Two candidate models were retired by
  their providers during planning alone.
- **No Next.js** (0001), **search threshold measured, not guessed** (0004),
  **speech-to-text through Groq** because this laptop can't run a local model
  (0005), **upgrades** such as the reranker and Langfuse (0008).

## Real bugs that only live testing found

Unit tests and the offline fake model prove the plumbing. These bugs only
showed up against real models, a real browser, or a real database:

- Web chat replies silently never arrived: Redis returned bytes where the
  WebSocket expected text.
- Email replies were sent to a Message-ID instead of an email address.
- Personal-data hiding existed as a database column but nothing filled it. The
  PII check caught it.
- If every AI provider was down, the customer got silence. Now they get an
  honest message and the ticket goes to a person.
- A slow free-tier day pushed one ticket past the worker's 5-minute job limit,
  so it was killed and retried mid-run.
- The eval judge graded replies without seeing what the agent looked up, so
  correct facts looked made up (a fake 57% hallucination rate).
- Seed dates were fixed in time, so weeks later every "still cancellable" order
  had expired. Seed dates now follow the clock.

## Known limits

- Real WhatsApp and email are manual tests, not automated.
- Voice replies are text only (no text-to-speech); speech-to-text needs
  internet and a Groq key.
- The small spaCy model can miss a lone first name ("this is Rahul").
- Free-tier quotas make a full run of every ablation a multi-day job.
- On purpose, not built: horizontal scaling, multi-tenancy, skill-based
  routing, SLA timers, CI.

## Lessons

- **A column or interface existing is not the feature working.** PII hiding
  and channel reply styles both "existed" for many stages before anything used
  them.
- **Check the ruler, not just the product.** A bad number from an AI judge was
  as likely a broken judge as a broken agent.
- **Put limits around the whole job, not just the loop.** Tool-call and turn
  limits bound the agent; a slow provider still needed a longer job timeout.
- **Most handoffs needed one approval or one question, not a person.** Fixing
  that changed the expected result of 21 of the 50 test tickets from "handed
  off" to "answered".
