# 0004 — RETRIEVAL_SCORE_MIN calibrated to 0.55, not 0.35

**Date:** 2026-09-08 · **Status:** accepted

## Context

The blueprint's placeholder value (`RETRIEVAL_SCORE_MIN = 0.35`) was written
before any real embeddings existed, as a rough guess. Building Stage 3's
retrieval gate against the actual seeded KB and `bge-small-en-v1.5` showed it
was badly wrong: an obviously off-topic query ("what is the meaning of life")
returned a top dense cosine similarity of **0.42** — above the 0.35 gate — so
the system would have retrieved and answered from irrelevant chunks instead of
correctly returning nothing.

This is a known property of BERT-style sentence embeddings, not a bug in this
implementation: short generic English sentences tend to land in a "baseline
similarity" band (roughly 0.35-0.5 for this model) regardless of actual
semantic relatedness, because much of the cosine signal comes from shared
subword/vocabulary statistics. A threshold has to clear that band, not just be
above zero.

## Decision

Measured dense cosine similarity on the seeded 8-document KB:

| Query | Top score | Relevant? |
|---|---|---|
| "what is the meaning of life" | 0.418 | no |
| "recommend me a good movie" | 0.387 | no |
| "how do I bake a chocolate cake" | 0.423 | no |
| "asdkjaslkdj random gibberish text" | 0.441 | no |
| "tell me a joke" | 0.459 | no |
| "when will my refund arrive" | 0.771 | yes |
| "can I return jeans" | 0.765 | yes |
| "my order is late" | 0.720 | yes |
| "why was my card declined" | 0.793 | yes |
| "does warranty cover water damage" | 0.768 | yes |
| "can I change my address" | 0.806 | yes |
| "is this order cancellable" | 0.797 | yes |

Off-topic tops out at 0.46; on-topic starts at 0.72. `RETRIEVAL_SCORE_MIN` set
to **0.55** — comfortably inside that gap.

## Consequences

- This number is calibrated against the current 8-document/9-chunk seeded KB
  and `bge-small-en-v1.5`. **Re-check it** if the KB grows substantially
  (more documents narrows topic-to-topic similarity gaps), if the embedding
  model changes (e.g. the `bge-m3` swap noted in `02-tech-stack.md`), or if
  Stage 11's adversarial eval cases suggest it's off.
- The Stage 11 threshold sweep (`INTENT_CONFIDENCE_MIN` in the eval harness)
  should get a sibling sweep on `RETRIEVAL_SCORE_MIN` once the eval dataset
  exists, to replace this seven-query manual calibration with a real curve.
- Documented here rather than silently changed, because a wrong-looking
  number in `.env.example` with no explanation invites someone to "fix" it
  back to something that looks more normal (like 0.35) without realizing it
  was tested.
