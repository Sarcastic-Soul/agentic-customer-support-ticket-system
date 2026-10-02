# 0007 — Fewer handoffs: approval queue, clarifying questions, recovery

**Date:** 2026-10-01 · **Status:** accepted · **Amends:** `docs/05-escalation-policy.md`

## Context

In manual testing the agent handed tickets to a human far too easily:

- any refund `authorize()` wouldn't approve on its own,
- any low-confidence classification,
- any question the knowledge base had no answer for,
- any mismatch between two data sources,
- a customer giving a wrong order number.

On the eval set, most non-trivial tickets ended up with a human. That defeats
the point of the project: the AI should take work off people, not pass it all
to them with extra steps.

Most of those handoffs didn't need a person to *talk to the customer*. They
needed a person to approve one thing, or the AI needed to ask one question.

## Decision

1. **Refund approval queue instead of a handoff.** A refund above
   `AUTO_REFUND_CEILING` or without a matching fault is still not approved by
   the AI. `authorize()` is unchanged. It is recorded as
   `refunds.status = 'requested'`. The AI tells the customer it is waiting for
   approval and keeps the conversation. Humans approve or reject it from
   `/api/console/approvals` in one click, and the customer is notified on
   their channel. The `policy_limit_exceeded` escalation is no longer fired by
   refunds.
2. **Ask before handing off.** On low intent confidence, or when nothing was
   found to answer from, the agent asks one specific question (`clarify.md`).
   It escalates only after `max_clarifications` (2) questions in a row. The
   counter resets on any real answer.
3. **Two verify repairs, not one** (`max_verify_repairs`), before
   `ungrounded_answer`.
4. **Fact conflicts are settled by a source-of-truth rule**, not escalated
   (see 0006).
5. **Carrier investigation tool.** `open_carrier_investigation` covers
   "marked delivered but I never got it" and "stuck for days", which used to
   end in a handoff. Timing comes from data (`delivered_at`,
   `promised_delivery`) through `authorize_carrier_investigation()`: a 24-hour
   wait after a delivery scan, and more than 3 days past the promised date.
6. **Prompts recover instead of giving up.**
   - Specialists call `list_recent_orders` when an order number is wrong or
     missing.
   - The answer prompt explains a denial and offers the alternatives the
     data allows.
   - No prompt accuses the customer of lying. When the story and the data
     disagree, the reply goes by the data, calmly.
7. **Refund dedupe in the tool.** One payment gets at most one non-rejected
   refund, so the AI can safely handle "refund it again" without a human
   watching.

## What still escalates, unchanged

Explicit request for a human, abuse or self-harm, legal or chargeback
language, `MAX_AI_TURNS`, and system errors.
These are cases where a human *should* take over, not ones where the AI was
unsure.

## Consequences

- The human workload moves from "take over the conversation" to "approve or
  reject a refund". That takes seconds, not minutes.
- Eval expectations changed: 21 cases moved from `escalated`/`no_context` to
  `answered`/`clarified`. `ai_resolution_rate` now counts `clarified` as
  handled by the AI, and `escalation_rate` is reported next to it.
- Risk: a customer who keeps being vague gets two questions before a human.
  That is the intended trade.
- Risk: a refund waits in the queue until someone approves it. There is no
  SLA timer on the queue (SLA crons are out of scope per 0003).
