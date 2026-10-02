# 0006 — Specialist agents per domain, with conflicts settled in code

**Date:** 2026-10-01 · **Status:** accepted · **Replaces:** the `plan` + `act`
"tool group" design in `docs/04-agent-design.md`

## Context

Feedback on the project asked for separate agents per domain: one for money
(refunds, payments, invoices), one for logistics (where is my parcel), and so
on, and for the system to show what happens when two of them disagree.

The earlier design had one `act` node with a tool group picked by `plan`. That
already restricted tools per intent, but it could only work one intent per
message. "Where is my order, and refund the double charge" was handled as
whichever intent the classifier picked first.

`docs/00-plan-review.md` argues against per-*channel* agents. Nothing here
changes that: there is still one channel-agnostic graph. The split is by
business domain, inside the graph.

## Decision

- `classify` returns an optional `secondary_intent` next to the primary one.
- A `supervisor` node maps each intent to a specialist (`app/agent/specialists.py`):
  - **orders**: cancel, change, return.
  - **logistics**: status, delivery problems, carrier investigations.
  - **payments**: refunds, failed payments, invoices, billing.

  It picks at most 2 specialists per message.
- The specialists run **in parallel** through LangGraph's `Send` API. Each one
  has its own prompt, its own tool list, and a share of `MAX_TOOL_CALLS`
  (5 → 3 + 2), so the whole turn stays inside the one limit.
- **Specialists never change anything.** Write tools run with
  `ToolContext.propose_only=True`. They still run eligibility checks and
  `authorize()`, then return what they *would* do.
- A `reconcile` node gathers every report and runs `app/policy/conflicts.py`,
  a plain rule table in code:

  | Conflict | Example | Rule |
  |---|---|---|
  | fact | order record says delivered, carrier says in transit | `carrier_is_truth_for_parcel`: use the carrier's status, hold writes on that order for this turn |
  | duplicate | orders and logistics both propose the same return | `same_action_once` |
  | action | cancel + refund on one order | `cancel_covers_refund` (cancelling refunds anyway) |
  | action | carrier investigation + refund | `investigation_before_refund` |
  | action | carrier investigation + return | `investigation_before_return` |
  | action | cancel + return | `cancel_over_return` |
  | action | return + refund | `return_covers_refund` |
  | action | two refunds, each under the ceiling, together over it | `combined_refund_over_ceiling`: both go to the approval queue |
  | action | any pair the table doesn't cover | escalate `agent_conflict` (P2) with both sides in the packet |

- A `commit` node carries out the proposals that survive. `authorize()` runs
  again on current data at commit time.
- Every conflict is written into the `reconcile` step's output. The ticket
  trace shows it and `/api/admin/metrics/agents` counts it. `agent_steps.agent`
  records which specialist took each step.

## Why

- **Propose, then commit** is what makes a conflict something we can settle
  instead of something that has already happened twice. If specialists wrote
  directly, a cancel and a refund on one order would both have gone through
  before anyone compared them.
- **Rules in code, not a "judge" LLM.** Same reasoning as `authorize()`: a
  model can be argued with, a rule table can't. It is also free to run, gives
  the same answer every time, and each rule is one unit test
  (`tests/test_conflicts.py`).
- **Escalation is the last resort.** Every conflict kind the current tools can
  produce has a rule. The `agent_conflict` escalation is a guard for tools
  added later.
- **At most 2 specialists and a split tool budget** keep one message at 3–6 LLM
  calls, inside the Groq free tier described in CLAUDE.md.

## Consequences

- Parallel specialists share one `AsyncSession`, and asyncpg allows only one
  statement at a time per connection. Database calls in `specialist_node` go
  through a lock stored in `session.info` (`app/agent/steps.py:session_lock`).
  LLM calls still run in parallel, and that is where the time goes.
- `specialist_reports` uses a reducer that `run_agent` resets with `None`
  every turn, because checkpointed state carries over on the ticket thread.
- The old design is still runnable as the `single_agent` eval ablation (one
  generalist with every tool), so the two can be compared on the same dataset.
- New migration `3b7d2c9a41f0` adds `agent_steps.agent`.
