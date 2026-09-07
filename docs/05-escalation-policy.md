# Escalation and Human-in-the-Loop

This is the core of the project. A support system that answers easy questions is
a chatbot; what makes this agentic is knowing when it is out of its depth and
handing over *well*.

## Escalation triggers

Two kinds: **deterministic** (checked in code, always win) and **judgemental**
(computed from model output). Deterministic rules run first, before any expensive
reasoning.

### Deterministic — fire immediately

| Code | Condition |
|---|---|
| `customer_requested_human` | Message matches human-request patterns ("talk to a person", "agent", "representative", "supervisor"). |
| `abusive_or_distress` | Abuse, threats, or self-harm signals. Never let a model improvise here. |
| `legal_or_regulatory` | Keywords: chargeback, consumer court, legal notice, fraud, police, GDPR/data deletion. |
| `policy_limit_exceeded` | A write tool was denied by `policy.authorize` (see limits below). |
| `high_value_customer` | `customer.tier == 'priority'` **and** `sentiment in (negative, angry)`. |
| `already_escalated` | Ticket has an open escalation; new messages route to the owning human. |
| `repeat_contact` | Third ticket from this customer about the same order within 7 days. |
| `system_error` | LLM or tool failure that retries did not clear. |
| `unverified_account_action` | Account-specific action requested by an unverified identity. |

### Judgemental — computed

| Code | Condition |
|---|---|
| `low_intent_confidence` | `intent_confidence < 0.60`, or `intent == unknown`. |
| `knowledge_gap` | Retrieval returned nothing above the score threshold for a knowledge-shaped intent. Logged separately as a KB backlog item. |
| `ungrounded_answer` | `verify.grounded == false` after one repair attempt. |
| `turn_budget_exceeded` | `turn_index >= 4` with the ticket still unresolved. |
| `negative_sentiment_trend` | Sentiment worsened across two consecutive turns. |
| `tool_repeated_failure` | Same tool failed twice in one run. |

All thresholds live in one place:

```python
# app/policy/thresholds.py
INTENT_CONFIDENCE_MIN     = 0.60
RETRIEVAL_SCORE_MIN       = 0.35     # post-RRF normalized
MAX_AI_TURNS              = 4
MAX_TOOL_CALLS            = 5
AUTO_REFUND_CEILING       = Decimal("1000.00")   # INR
AUTO_CANCEL_MAX_AGE_HOURS = 24
```

Having these tunable in one file is worth a slide in the report: you can show
escalation rate versus threshold on the eval set.

## Action authorization

```python
def authorize(action: Action, ctx: ToolContext) -> Decision:
    """Allow | RequireHuman | Deny, with a reason. Enforced in code, not prompt."""
```

| Action | AI may do alone | Requires human | Never |
|---|---|---|---|
| Read order / shipment / transaction | yes (own customer only) | — | other customers' data |
| Explain policy from KB | yes | — | invent policy |
| Cancel order | yes, if `now < cancellable_until` and not shipped | shipped, or past window | after delivery |
| Initiate return | yes, if within `return_window_ends` and item `returnable` | outside window, or damaged-goods claim | non-returnable SKUs |
| Refund | yes, if amount <= `AUTO_REFUND_CEILING` and a matching failed/duplicate payment exists | any larger amount, any goodwill refund, any dispute | issue without a linked transaction |
| Change address / contact | no | yes | — |
| Account deletion, plan change | no | yes | — |
| Promise a delivery date | only a date returned by `track_shipment` | — | estimate one |

The model cannot bypass this: `authorize` is called inside the tool wrapper, and
a `Deny` result becomes a structured tool error plus an automatic escalation.

## Priority and SLA

```
P1  system down, payment taken with no order, priority-tier + angry   -> 15 min
P2  refund stuck, delivery failed, policy_limit_exceeded              -> 2 h
P3  normal order/product questions                                    -> 8 h
P4  feedback, general enquiry                                         -> 24 h
```

Priority sets queue order, and the console shows elapsed time against these
targets. There is no breach-checking cron job — the SLA column above is a design
statement plus a display, not a scheduler. Escalating `abusive_or_distress` or
`legal_or_regulatory` always lifts priority to at least P2.

## The handoff packet

Stored as JSONB on the escalation row and rendered at the top of the agent
console. This is the difference between "the AI gave up" and "the AI did the
first 80% of the work".

```json
{
  "ticket_reference": "T-1041",
  "escalation_reason": "policy_limit_exceeded",
  "reason_detail": "Refund of 4200 INR exceeds auto-approval ceiling of 1000 INR",
  "priority": "P2",
  "required_skill": "refunds",
  "customer": {
    "id": 88, "name": "R. Sharma", "tier": "priority",
    "locale": "en-IN", "verified": true,
    "lifetime_orders": 34, "open_tickets": 1
  },
  "summary": "Customer paid twice for ORD-10432 on 2 Sep. Both charges captured. Wants the duplicate charge refunded.",
  "timeline": [
    {"at": "2026-09-02T10:14Z", "who": "customer", "what": "Reported double charge"},
    {"at": "2026-09-02T10:14Z", "who": "ai", "what": "Verified two captured payments TXN-88213, TXN-88219 for the same order"},
    {"at": "2026-09-02T10:15Z", "who": "ai", "what": "Refund request denied by policy: amount above ceiling"}
  ],
  "entities": {
    "order_number": "ORD-10432",
    "transactions": ["TXN-88213", "TXN-88219"],
    "amount": "4200.00", "currency": "INR"
  },
  "what_the_ai_verified": [
    "Both transactions are status=captured for the same order_id",
    "Order is delivered; return window still open until 2026-09-16"
  ],
  "what_the_ai_could_not_do": [
    "Approve a refund above 1000 INR"
  ],
  "knowledge_used": [
    {"chunk_id": 412, "title": "Duplicate charge handling", "excerpt": "..."}
  ],
  "suggested_reply": "Hi R. Sharma, I've confirmed a duplicate charge of 4200 INR ...",
  "suggested_action": {"tool": "request_refund", "args": {"txn_ref": "TXN-88219", "amount": "4200.00", "reason": "duplicate_charge"}},
  "sentiment": "negative",
  "ai_confidence": 0.88,
  "links": {"order": "/admin/orders/10432", "transactions": ["/admin/txn/88213", "/admin/txn/88219"]}
}
```

The `summary` and `suggested_reply` are LLM-generated; everything else is
assembled deterministically from state. Do not let the model author the timeline
or the entity list — those must be facts.

## Human agent console flow

1. **Queue view.** Sorted by priority then age, with a reason-code badge, elapsed
   time and a skill filter. Live-updated over WebSocket.
2. **Claim.** `FOR UPDATE SKIP LOCKED`, sets `claimed_by`, moves the ticket to
   `human_working`, and stops AI auto-replies for it. Keep the `SKIP LOCKED` — it
   is one clause and it removes a race you would otherwise spend an evening on.
3. **Work view.** Handoff packet, full transcript with AI reasoning collapsible
   per turn, linked order and transaction panels, editable draft.
4. **Act.** Three buttons:
   - **Send reply** — goes out through the original channel adapter, appended as a
     `human_agent` message so the customer sees one thread.
   - **Approve suggested action** — executes the gated tool with `approved_by` set.
   - **Return to AI** — writes `human_note`, resumes the graph with that note in
     state, so the AI continues with new information ("refund approved, tell the
     customer 5-7 business days").
5. **Resolve.** Sets `human_resolved`, prompts for a one-line resolution summary,
   and offers "save as knowledge-base article" when the reason was
   `knowledge_gap` — this closes the improvement loop and is a strong demo moment.

## Resume mechanics

LangGraph's `interrupt()` plus the Postgres checkpointer:

```python
# inside the escalate node
human_decision = interrupt({
    "type": "escalation",
    "packet": packet,
    "ticket_id": state["ticket_id"],
})
# execution stops here; state is persisted under thread_id = f"ticket:{ticket_id}"

# later, from the console API:
await graph.ainvoke(
    Command(resume={"action": "return_to_ai", "note": note}),
    config={"configurable": {"thread_id": f"ticket:{ticket_id}"}},
)
```

The graph resumes inside the same node with the human's decision as the return
value, keeping all prior state. No re-running of classification or retrieval, no
duplicated tool calls.

## Metrics this subsystem must expose

These come out of the eval harness and the dashboard; do not build separate
instrumentation for them.

- Escalation rate, and its breakdown by `reason_code`.
- **Escalation precision:** of escalated tickets, how many genuinely needed a
  human (labelled on the eval set).
- **Escalation recall:** of tickets the AI resolved, how many *should* have been
  escalated (the dangerous number — a false resolution costs more than a false
  escalation).
- Time to claim, and time to human resolution.
- Return-to-AI rate (how often the human hands control back).
- Draft acceptance rate: how often the human sends the suggested reply unedited or
  lightly edited. The clearest evidence that the AI does useful work even when it
  escalates.
