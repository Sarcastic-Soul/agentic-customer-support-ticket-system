# Evaluation

Without this, "the AI resolves customer issues" is an unsupported claim; with it
you have a results section. Around 50 cases and one script — enough to be
credible, not a benchmarking framework.

## The dataset

`eval/dataset/tickets.jsonl` — roughly 50 hand-labelled cases. **Collect these as
you go.** Every time you manually test something during Stages 3-10, save it as a
case. Authoring 50 cases from scratch at the end is miserable; collecting them as a
by-product costs nothing.

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
| Straightforward, AI should resolve | 16 | Baseline resolution rate |
| Multi-tool / multi-turn / needs a clarifying question | 8 | Tests the tool loop |
| Must escalate (policy limit, legal, abuse, angry priority customer) | 10 | The metric that matters most |
| Knowledge gap — answer genuinely absent from the KB | 6 | Tests refusal instead of invention |
| Adversarial (prompt injection, another customer's data) | 6 | Security |
| Noisy input (typos, Hinglish, no order number) | 4 | Robustness |

The escalation, knowledge-gap and adversarial buckets are what make the
evaluation credible. Anyone can score well on the easy sixteen.

## Metrics

| Metric | Definition | Target |
|---|---|---|
| **AI resolution rate** | resolved with no human, judged correct | ~60% |
| **Escalation recall** | of cases needing a human, fraction escalated | ~0.95 |
| **Escalation precision** | of escalated cases, fraction genuinely needing a human | ~0.85 |
| **Hallucination rate** | answers containing an unsupported factual claim | under 3% |
| **Groundedness** | factual claims all trace to a citation or tool result | ~0.95 |
| Intent accuracy | classifier vs. label | — |
| Tool-selection accuracy | expected tool set called (`GROUP BY tool_name` over `tool_calls`) | — |
| Citation validity | cited chunk ids exist and support the claim | — |
| Latency | median end to end | — |
| Cost per ticket | from `agent_runs` token counts | — |

Escalation **recall** matters far more than precision, and this is worth a
paragraph in the report: over-escalating wastes human time, under-escalating gives
a customer a confidently wrong answer about their money. Tune thresholds toward
recall and say why.

## How correctness is judged

Three layers, cheapest first.

1. **Deterministic assertions** — `must_mention` / `must_not_mention` substrings,
   expected tool set, expected outcome. Free, catches most regressions, and covers
   the majority of cases on its own.
2. **LLM-as-judge** for the open-ended ones — Groq `openai/gpt-oss-120b` scoring
   correctness and groundedness 1-5 against the reference. Deliberately a
   different provider from the system under test.

3. **Human spot check** — review about 15 randomly sampled cases yourself and
   record agreement with the judge. One number, one sentence in the report, and it
   is what makes layer 2 defensible.

## Ablations

The table that earns marks:

| Configuration | Resolution rate | Groundedness | Hallucination | Escalation recall | Cost/ticket |
|---|---|---|---|---|---|
| Full system | | | | | |
| No RAG (parametric memory only) | | | | | |
| No `verify` node | | | | | |
| Dense-only retrieval (no `tsvector`) | | | | | |
| All tools exposed (no `plan` node) | | | | | |

State the predictions first, then confirm them: removing RAG collapses
groundedness; removing `verify` raises resolution rate but raises hallucination
more; dense-only search loses order-number and error-code lookups; exposing every
tool raises wrong-tool calls and cost. The last two are what justify hybrid search
and the `plan` node as design decisions rather than guesses.

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

No CI and no nightly runs — run it by hand after prompt changes and before the
final report. Keep `eval/reports/baseline.json` so you can diff against it and
notice when something regressed.

## Live metrics are not evaluation

The dashboard reports what happened in whatever traffic you sent it. The eval
harness reports controlled measurements on a fixed dataset. Report both, and do
not compare them — dashboard numbers move with traffic mix.
