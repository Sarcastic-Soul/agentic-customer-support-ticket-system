# Evaluation

Small and cheap on purpose. Without it, "the AI resolves customer issues" is an
unsupported claim; with it you have a results section. Around 35 cases and one
script is enough for that — do not build a benchmarking framework.

## The dataset

`eval/dataset/tickets.jsonl` — roughly 35 hand-labelled cases. **Collect these as
you go.** Every time you manually test something during Stages 3-10, save it as a
case. Authoring 35 cases from scratch at the end is miserable; collecting them as
a by-product costs nothing.

```json
{
  "id": "ord-007",
  "channel": "whatsapp",
  "customer_id": 12,
  "turns": ["hey my order ORD-10432 hasn't arrived and it's been 9 days"],
  "expected_intent": "delivery_issue",
  "expected_tools": ["get_order", "track_shipment"],
  "expected_outcome": "answered",
  "must_mention": ["in transit", "11 Sep"],
  "must_not_mention": ["refund approved", "guaranteed"]
}
```

Composition:

| Bucket | Count | Why |
|---|---|---|
| Straightforward, AI should resolve | 12 | Baseline resolution rate |
| Multi-tool / needs a clarifying question | 5 | Tests the tool loop |
| Must escalate (policy limit, legal, abuse, angry priority customer) | 8 | The metric that matters most |
| Knowledge gap — answer genuinely absent from the KB | 5 | Tests refusal instead of invention |
| Adversarial (prompt injection, another customer's data) | 5 | Security |

The last two buckets are what make the evaluation credible. Anyone can score well
on the easy twelve.

## Metrics

| Metric | Definition | Target |
|---|---|---|
| **AI resolution rate** | resolved with no human, judged correct | ~60% |
| **Escalation recall** | of cases needing a human, fraction escalated | ~0.95 |
| **Escalation precision** | of escalated cases, fraction genuinely needing a human | ~0.85 |
| **Hallucination rate** | answers containing an unsupported factual claim | under 5% |
| Intent accuracy | classifier vs. label | — |
| Tool-selection accuracy | expected tool set called | — |
| Latency | median end to end | — |
| Cost per ticket | from `agent_runs` token counts | — |

Escalation **recall** matters far more than precision, and this is worth a
paragraph in the report: over-escalating wastes human time, under-escalating gives
a customer a confidently wrong answer about their money. Tune thresholds toward
recall and say why.

## How correctness is judged

Two layers. Skip the third that a production system would have.

1. **Deterministic assertions** — `must_mention` / `must_not_mention` substrings,
   expected tool set, expected outcome. Free, catches most regressions, and covers
   the majority of cases on its own.
2. **LLM-as-judge** for the open-ended ones — Groq `openai/gpt-oss-120b` scoring
   correctness and groundedness 1-5 against the reference. Deliberately a
   different provider from the system under test.

Spot-check about 10 judged cases yourself and note the agreement rate in the
report. One sentence, and it is what makes layer 2 defensible.

## Ablations

Two, plus one sweep. This is the table that earns marks:

| Configuration | Resolution rate | Hallucination rate | Escalation recall |
|---|---|---|---|
| Full system | | | |
| No RAG (model answers from parametric memory) | | | |
| No `verify` node | | | |

Expected, then confirm: removing RAG collapses groundedness; removing `verify`
raises resolution rate but raises hallucination more. Both are good findings.

Then sweep `INTENT_CONFIDENCE_MIN` across 0.4 / 0.5 / 0.6 / 0.7 / 0.8 and plot
escalation rate against hallucination rate. That single curve makes the
safety/automation trade-off explicit and is the most useful figure in the report.

## Harness

```
eval/
├─ dataset/tickets.jsonl
├─ run_eval.py
└─ reports/
```

- Runs against a freshly seeded database (`make reset`) so results are reproducible
- Records the model ids in the report header — a metric without its model id is
  not comparable later on, and this stack has already had a model deprecated
  out from under it
- Prints a Markdown table to stdout and saves JSON

No pytest regression gate, no nightly runs, no CI. Run it by hand when you change
prompts, and before the final report.

## Live metrics are not evaluation

The dashboard reports what happened in whatever traffic you sent it. The eval
harness reports controlled measurements on a fixed dataset. Report both, and do
not compare them — dashboard numbers move with traffic mix.
