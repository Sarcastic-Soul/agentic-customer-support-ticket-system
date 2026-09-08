"""Stage 11 evaluation harness. Replays eval/dataset/tickets.jsonl through
the real LangGraph orchestrator against a live database, scores each case
deterministically plus an LLM judge, and prints a Markdown table + writes
JSON to eval/reports/.

Not a benchmarking framework - one script, ~50 cases. See docs/08-evaluation.md.

Usage (run from backend/, matching `make eval`; see Makefile):
    python ../eval/run_eval.py                    # full system, all cases
    python ../eval/run_eval.py --limit 10          # smoke test subset
    python ../eval/run_eval.py --ablation no_rag   # one ablation config
    python ../eval/run_eval.py --sweep-confidence  # INTENT_CONFIDENCE_MIN sweep
    python ../eval/run_eval.py --skip-judge        # deterministic scoring only, no LLM judge calls

IMPORTANT: run against a freshly seeded database (`make reset`) for
reproducible numbers - this script does not reset the database itself, so
results after ad-hoc manual testing will include that testing's side
effects (extra tickets/conversations do not affect scoring, which is scoped
per-case by conversation, but a mutated KB document would).
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agent.nodes.answer import format_context, format_tool_results  # noqa: E402
from app.agent.run import run_agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402
from app.ingress.pipeline import ingest_message  # noqa: E402
from app.llm.registry import AllProvidersFailedError, get_llm  # noqa: E402
from app.llm.roles import LLMRole  # noqa: E402
from app.models import (  # noqa: E402
    AgentRun,
    CustomerIdentity,
    Message,
    Ticket,
)

DATASET_PATH = Path(__file__).resolve().parent / "dataset" / "tickets.jsonl"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"

ESCALATED_STATUSES = ("escalated", "human_working")

# Unique per invocation so re-running the harness (e.g. after a killed/partial
# run) always creates fresh tickets rather than deduping against a stale
# external_message_id from a prior attempt and silently scoring an empty result.
RUN_NONCE = str(int(time.time()))


def load_cases(limit: int | None = None) -> list[dict]:
    cases = []
    with open(DATASET_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases[:limit] if limit else cases


class JudgeVerdict(BaseModel):
    correctness: int  # 1-5
    groundedness: int  # 1-5
    hallucinated: bool
    reasoning: str


async def resolve_sender_identity(session, case: dict) -> str:
    """Real seeded customers get their real phone/email so identity
    resolution matches them to their real order history; cases with no
    customer_id get a synthetic per-case identity (a fresh, unverified
    identity - correct for chitchat/policy/adversarial cases that aren't
    about any specific account).

    This is deliberately NOT used as the conversation's external_thread_id
    (see run_case) - several cases share the same real customer (there are
    only a handful of seeded customers with interesting order histories),
    and threading them into one shared conversation means whichever case
    escalates first poisons every other case against that customer for the
    rest of the run (ticket stays "escalated", so handle_message-equivalent
    logic correctly, but unhelpfully, stays quiet on all of them). Found
    live during Stage 11/12: cases sharing customer_id=5's WhatsApp number
    all silently no-op'd once any one of them escalated.
    """
    customer_id = case.get("customer_id")
    channel = case["channel"]
    if customer_id is None:
        return f"eval-{case['id']}"

    column = {"whatsapp": "whatsapp", "email": "email"}.get(channel)
    if column is None:
        return f"eval-{case['id']}"

    row = (
        await session.execute(
            select(CustomerIdentity.external_id).where(
                CustomerIdentity.customer_id == customer_id,
                CustomerIdentity.channel == column,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(
            f"case {case['id']!r}: no {channel} identity seeded for customer_id={customer_id}"
        )
    return row


async def run_case(case: dict, *, run_tag: str) -> dict:
    """Runs every turn in the case through the real ingress pipeline and the
    real graph, sequentially, in one conversation thread. Returns the last
    turn's final_state plus whatever's needed to score it.

    run_tag must be unique per run_all() invocation (config name, or sweep
    threshold) - it's folded into external_message_id so two invocations of
    the same case (e.g. the "full" config, then a confidence-sweep pass)
    don't dedupe against each other and silently produce an empty result.
    Found live: the confidence sweep originally reused settings.eval_ablation
    (always None, since the sweep doesn't touch it) as the only
    per-invocation tag, so every sweep threshold deduped against the "full"
    config run moments earlier and every case "passed" in 0.0s with no
    graph run at all.
    """
    async with async_session_factory() as session:
        sender_external_id = await resolve_sender_identity(session, case)
        channel = case["channel"]
        # Conversations key on (channel, external_thread_id) alone
        # (app/core/conversation.py) - a thread unique per case+run keeps
        # every case isolated even when several cases share one real
        # customer's identity for their order history.
        external_thread_id = f"eval-thread-{case['id']}-{run_tag}-{RUN_NONCE}"

        final_state = None
        ticket_id = None
        run_id = None
        for i, turn_text in enumerate(case["turns"]):
            message = await ingest_message(
                session,
                channel=channel,
                external_thread_id=external_thread_id,
                sender_external_id=sender_external_id,
                text=turn_text,
                external_message_id=f"eval-{case['id']}-{i}-{run_tag}-{RUN_NONCE}",
                raw_payload={"eval_case": case["id"], "turn": i},
            )
            await session.commit()
            if message is None:
                continue  # deduped - shouldn't happen with unique per-run ids, but not fatal

            loaded = (
                await session.execute(
                    select(Message)
                    .options(selectinload(Message.conversation))
                    .where(Message.id == message.id)
                )
            ).scalar_one()
            conversation = loaded.conversation

            ticket = (
                await session.execute(
                    select(Ticket)
                    .where(Ticket.conversation_id == conversation.id)
                    .order_by(Ticket.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if ticket is None:
                continue
            ticket_id = ticket.id

            if ticket.status in ESCALATED_STATUSES:
                # A prior turn already escalated this conversation to a
                # human - matches production's handle_message, which stays
                # quiet rather than re-running the graph on an
                # interrupted/human-owned thread.
                continue

            final_state = await run_agent(
                session,
                ticket_id=ticket.id,
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                channel=channel,
                external_thread_id=external_thread_id,
                message_id=message.id,
                latest_message=message.body_redacted or message.body,
            )
            run_id = final_state.get("run_id") if isinstance(final_state, dict) else None

        # Escalation pauses the graph at interrupt() - ainvoke() returns
        # without ever reaching respond_node, so AgentRun.outcome/state
        # "outcome" is never set to "escalated" on this path. The ticket's
        # own status is the reliable signal instead.
        ticket = await session.get(Ticket, ticket_id) if ticket_id else None
        actual_outcome = "escalated" if ticket and ticket.status in ESCALATED_STATUSES else (
            (final_state or {}).get("outcome") or "unknown"
        )

        reply = (
            await session.execute(
                select(Message)
                .where(
                    Message.conversation_id == ticket.conversation_id,
                    Message.role == "assistant",
                )
                .order_by(Message.id.desc())
                .limit(1)
            )
        ).scalars().first() if ticket else None

        run = await session.get(AgentRun, run_id) if run_id else None

        return {
            "ticket_id": ticket_id,
            "actual_intent": ticket.intent if ticket else None,
            "actual_outcome": actual_outcome,
            "actual_tools": [t["tool"] for t in (final_state or {}).get("tool_results", [])],
            "reply_text": reply.body if reply else "",
            "citations": (final_state or {}).get("citations", []),
            # Ground truth for judge_case() - without these the judge grades
            # blind and flags every specific, correctly-grounded detail (a
            # KB-cited policy number, a system-generated ticket reference)
            # as "unverifiable", inflating hallucination_rate on facts that
            # were never invented. See docs/PROGRESS.md Stage 11/12.
            "retrieved": (final_state or {}).get("retrieved", []),
            "tool_results": (final_state or {}).get("tool_results", []),
            "ticket_reference": ticket.reference if ticket else None,
            "latency_ms": run.latency_ms if run else None,
            "est_cost_usd": float(run.est_cost_usd) if run and run.est_cost_usd else 0.0,
        }


def score_deterministic(case: dict, result: dict) -> dict:
    reply = result["reply_text"] or ""
    reply_lower = reply.lower()

    intent_correct = result["actual_intent"] == case["expected_intent"]
    outcome_correct = result["actual_outcome"] == case["expected_outcome"]

    expected_tools = set(case.get("expected_tools", []))
    actual_tools = set(result["actual_tools"])
    # Subset match, not exact equality: the model calling one extra
    # cheap lookup tool isn't the failure mode this metric is meant to
    # catch, missing an expected tool entirely is.
    tools_correct = expected_tools.issubset(actual_tools) if expected_tools else True

    must_mention = case.get("must_mention", [])
    must_not_mention = case.get("must_not_mention", [])
    mentions_ok = all(m.lower() in reply_lower for m in must_mention)
    no_forbidden = not any(m.lower() in reply_lower for m in must_not_mention)

    return {
        "intent_correct": intent_correct,
        "outcome_correct": outcome_correct,
        "tools_correct": tools_correct,
        "mentions_ok": mentions_ok,
        "no_forbidden": no_forbidden,
        "deterministic_pass": mentions_ok and no_forbidden,
    }


async def judge_case(case: dict, result: dict) -> JudgeVerdict | None:
    if not result["reply_text"]:
        return None
    # Grading blind (no access to what the agent actually retrieved/looked
    # up) makes every specific, correctly-grounded detail look unverifiable
    # to the judge - a real bug found in Stage 11/12: a KB-cited policy
    # number ("24 hours", "7 days") and a system-generated escalation
    # reference both got flagged as "hallucinated" across most of the
    # dataset, because the judge had nothing to check them against. Passing
    # the same context/tool-results the agent itself was given, plus the
    # real ticket reference, lets it actually verify instead of guess.
    prompt = (
        "You are grading a customer support agent's reply. Score strictly, "
        "but only flag a claim as unverifiable if it contradicts or goes "
        "beyond the evidence below - not just because you personally can't "
        "independently confirm it.\n\n"
        f"Customer's message(s): {' | '.join(case['turns'])}\n\n"
        f"Knowledge base excerpts the agent had access to:\n"
        f"{format_context(result['retrieved'])}\n\n"
        f"Tool/account-data results the agent had access to:\n"
        f"{format_tool_results(result['tool_results'])}\n\n"
        f"Agent's reply: {result['reply_text']}\n\n"
        f"Note: \"reference {result['ticket_reference']}\" (or similar) in "
        "an escalation acknowledgement is a real, system-generated ticket "
        "id, already confirmed to exist - it is not an invented claim, "
        "score it as fine.\n\n"
        "correctness (1-5): does the reply correctly and completely address "
        "what the customer asked, given what the agent had available? An "
        "honest escalation/deferral is correct behaviour (not a low score) "
        "when the evidence above genuinely doesn't answer the question or "
        "the request needs human approval - it is only incorrect if the "
        "evidence *did* support answering directly and the agent failed to.\n"
        "groundedness (1-5): does every factual claim trace to the "
        "knowledge base excerpts or tool results above, with nothing "
        "invented beyond them?\n"
        "hallucinated (bool): does the reply state a specific fact that "
        "contradicts the evidence above, or that isn't supported by it, "
        "excluding the ticket reference per the note above?\n"
        "reasoning: one sentence."
    )
    try:
        outcome = await get_llm(LLMRole.judge).ainvoke(prompt, structured=JudgeVerdict)
    except AllProvidersFailedError:
        return None
    return outcome.structured


async def run_all(
    cases: list[dict], *, ablation: str | None, skip_judge: bool, run_tag: str
) -> list[dict]:
    settings.eval_ablation = ablation
    rows = []
    for case in cases:
        start = time.monotonic()
        try:
            result = await run_case(case, run_tag=run_tag)
        except Exception as exc:  # noqa: BLE001 - one bad case must not kill the run
            rows.append({"case": case, "error": str(exc)})
            print(f"  [ERROR] {case['id']}: {exc}", file=sys.stderr)
            continue

        det = score_deterministic(case, result)
        verdict = None if skip_judge else await judge_case(case, result)
        elapsed = time.monotonic() - start

        rows.append({
            "case": case,
            "result": result,
            "scores": det,
            "judge": verdict.model_dump() if verdict else None,
            "wall_seconds": round(elapsed, 1),
        })
        status = "PASS" if det["deterministic_pass"] and det["outcome_correct"] else "FAIL"
        print(f"  [{status}] {case['id']} ({case['bucket']}) - {elapsed:.1f}s")
    return rows


def summarize(rows: list[dict]) -> dict:
    ok_rows = [r for r in rows if "result" in r]
    n = len(ok_rows)
    if n == 0:
        return {"n": 0}

    def rate(pred) -> float:
        return round(sum(1 for r in ok_rows if pred(r)) / n, 3)

    escalate_cases = [r for r in ok_rows if r["case"]["expected_outcome"] == "escalated"]
    non_escalate_cases = [r for r in ok_rows if r["case"]["expected_outcome"] != "escalated"]
    predicted_escalated = [r for r in ok_rows if r["result"]["actual_outcome"] == "escalated"]

    escalation_recall = (
        round(
            sum(1 for r in escalate_cases if r["result"]["actual_outcome"] == "escalated")
            / len(escalate_cases),
            3,
        )
        if escalate_cases else None
    )
    escalation_precision = (
        round(
            sum(1 for r in predicted_escalated if r["case"]["expected_outcome"] == "escalated")
            / len(predicted_escalated),
            3,
        )
        if predicted_escalated else None
    )

    judged = [r for r in ok_rows if r.get("judge")]
    hallucination_rate = (
        round(sum(1 for r in judged if r["judge"]["hallucinated"]) / len(judged), 3)
        if judged else None
    )
    groundedness = (
        round(sum(r["judge"]["groundedness"] for r in judged) / len(judged) / 5, 3)
        if judged else None
    )
    correctness = (
        round(sum(r["judge"]["correctness"] for r in judged) / len(judged) / 5, 3)
        if judged else None
    )

    latencies = [r["result"]["latency_ms"] for r in ok_rows if r["result"]["latency_ms"]]
    costs = [r["result"]["est_cost_usd"] for r in ok_rows]

    return {
        "n": n,
        "errors": len(rows) - n,
        "intent_accuracy": rate(lambda r: r["scores"]["intent_correct"]),
        "tool_selection_accuracy": rate(lambda r: r["scores"]["tools_correct"]),
        "outcome_accuracy": rate(lambda r: r["scores"]["outcome_correct"]),
        "ai_resolution_rate": (
            round(
                sum(1 for r in non_escalate_cases if r["result"]["actual_outcome"] == "answered")
                / len(non_escalate_cases),
                3,
            )
            if non_escalate_cases else None
        ),
        "escalation_recall": escalation_recall,
        "escalation_precision": escalation_precision,
        "hallucination_rate": hallucination_rate,
        "groundedness": groundedness,
        "judge_correctness": correctness,
        "median_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "total_cost_usd": round(sum(costs), 4),
        "cost_per_ticket_usd": round(sum(costs) / n, 6) if n else None,
    }


def print_table(label: str, summary: dict) -> None:
    print(f"\n### {label}\n")
    print("| Metric | Value |")
    print("|---|---|")
    for key, value in summary.items():
        print(f"| {key} | {value} |")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--ablation", choices=["no_rag", "no_verify", "dense_only", "all_tools"], default=None
    )
    parser.add_argument("--all-ablations", action="store_true")
    parser.add_argument("--sweep-confidence", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--bucket", default=None, help="only run cases from one bucket")
    parser.add_argument(
        "--sweep-only", action="store_true",
        help="skip the config loop (full/ablations) - just run --sweep-confidence",
    )
    args = parser.parse_args()

    cases = load_cases()
    if args.bucket:
        cases = [c for c in cases if c["bucket"] == args.bucket]
    if args.limit:
        cases = cases[: args.limit]

    print(f"Loaded {len(cases)} cases from {DATASET_PATH}")
    print(f"Model ids: reason={settings.model_reason} (fallback {settings.fallback_model_reason}), "
          f"classify={settings.model_classify}, verify={settings.model_verify}, "
          f"judge={settings.judge_model}")

    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_cases": len(cases),
        "model_ids": {
            "reason": settings.model_reason,
            "fallback_reason": settings.fallback_model_reason,
            "classify": settings.model_classify,
            "verify": settings.model_verify,
            "judge": settings.judge_model,
        },
        "runs": {},
    }

    configs: list[str] = []
    if args.sweep_only:
        pass
    elif args.ablation:
        configs = [args.ablation]
    elif args.all_ablations:
        configs = ["full", "no_rag", "no_verify", "dense_only", "all_tools"]
    else:
        configs = ["full"]

    for config_name in configs:
        ablation = None if config_name == "full" else config_name
        print(f"\n=== Running config: {config_name} ({len(cases)} cases) ===")
        rows = await run_all(
            cases, ablation=ablation, skip_judge=args.skip_judge, run_tag=config_name
        )
        summary = summarize(rows)
        print_table(config_name, summary)
        report["runs"][config_name] = {
            "summary": summary,
            "rows": [
                {
                    "id": r["case"]["id"],
                    "bucket": r["case"]["bucket"],
                    **({"error": r["error"]} if "error" in r else {
                        "expected_intent": r["case"]["expected_intent"],
                        "actual_intent": r["result"]["actual_intent"],
                        "expected_outcome": r["case"]["expected_outcome"],
                        "actual_outcome": r["result"]["actual_outcome"],
                        "scores": r["scores"],
                        "judge": r["judge"],
                        "wall_seconds": r["wall_seconds"],
                    }),
                }
                for r in rows
            ],
        }

    if args.sweep_confidence:
        print("\n=== INTENT_CONFIDENCE_MIN sweep ===")
        sweep_results = {}
        original = settings.intent_confidence_min
        try:
            for threshold in (0.4, 0.5, 0.6, 0.7, 0.8):
                settings.intent_confidence_min = threshold
                rows = await run_all(
                    cases, ablation=None, skip_judge=True, run_tag=f"sweep-{threshold}"
                )
                summary = summarize(rows)
                sweep_results[threshold] = {
                    "escalation_recall": summary.get("escalation_recall"),
                    "escalation_precision": summary.get("escalation_precision"),
                    "hallucination_rate": summary.get("hallucination_rate"),
                }
                print(f"  {threshold}: {sweep_results[threshold]}")
        finally:
            settings.intent_confidence_min = original
        report["confidence_sweep"] = sweep_results

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out_path}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
