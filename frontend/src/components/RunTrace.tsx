import {
  CaretRightIcon,
  CheckIcon,
  HandPalmIcon,
  ProhibitIcon,
  ScalesIcon,
  WarningIcon,
  XIcon,
} from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useId, useState } from "react";
import type { AgentRunOut, AgentStepOut, ConflictOut, ToolCallOut } from "../lib/admin-api";
import { cx } from "../lib/cx";
import { agentLabel, clockTime, humanize, ms, usd } from "../lib/format";

const SPRING = { type: "spring", bounce: 0, duration: 0.3 } as const;

/** Consecutive steps either sit on the shared spine (agent null) or form a
 * block of specialist lanes that ran side by side. */
type Segment =
  | { kind: "shared"; steps: AgentStepOut[] }
  | { kind: "lanes"; lanes: { agent: string; steps: AgentStepOut[] }[] };

function segment(steps: AgentStepOut[]): Segment[] {
  const out: Segment[] = [];
  for (const step of steps) {
    const last = out[out.length - 1];
    if (!step.agent) {
      if (last?.kind === "shared") last.steps.push(step);
      else out.push({ kind: "shared", steps: [step] });
      continue;
    }
    if (last?.kind !== "lanes") out.push({ kind: "lanes", lanes: [] });
    const block = out[out.length - 1] as Extract<Segment, { kind: "lanes" }>;
    const lane = block.lanes.find((l) => l.agent === step.agent);
    if (lane) lane.steps.push(step);
    else block.lanes.push({ agent: step.agent, steps: [step] });
  }
  return out;
}

const OUTCOME_TONE: Record<string, string> = {
  answered: "text-moss",
  resolved: "text-moss",
  escalated: "text-accent-strong",
  failed: "text-accent-strong",
  no_context: "text-ochre",
};

export function RunTrace({ run, defaultOpen }: { run: AgentRunOut; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const segments = segment(run.steps);
  const conflicts = run.conflicts ?? [];
  const specialists = run.specialists ?? [];
  const tokens = run.total_tokens_in + run.total_tokens_out;

  return (
    <article className="border-b border-rule last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-paper"
      >
        <CaretRightIcon
          size={14}
          aria-hidden
          className={cx("mt-1 shrink-0 text-ink-3 transition-transform duration-200", open && "rotate-90")}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="font-display text-[15px] font-semibold text-ink">Run {run.id}</span>
            <span className="text-sm text-ink-3">{humanize(run.trigger)}</span>
            {run.outcome && (
              <span className={cx("text-sm font-medium", OUTCOME_TONE[run.outcome] ?? "text-ink-2")}>
                {humanize(run.outcome)}
              </span>
            )}
            {conflicts.length > 0 && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-accent-strong">
                <ScalesIcon size={14} aria-hidden />
                {conflicts.length} {conflicts.length === 1 ? "conflict" : "conflicts"}
              </span>
            )}
          </span>
          <span className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-xs text-ink-3 tabular">
            <span>{clockTime(run.started_at)}</span>
            {run.intent && (
              <span>
                {run.intent}
                {run.confidence != null ? ` ${Math.round(run.confidence * 100)}%` : ""}
              </span>
            )}
            <span>{tokens.toLocaleString()} tok</span>
            <span>{usd(run.est_cost_usd)}</span>
            <span>{ms(run.latency_ms)}</span>
          </span>
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={SPRING}
            className="overflow-hidden"
          >
            <div className="space-y-4 px-5 pb-5">
              {specialists.length > 0 && (
                <p className="text-xs text-ink-3">
                  Specialists dispatched:{" "}
                  {specialists.map((s, i) => (
                    <span key={s}>
                      <span className="font-medium text-ink-2">{agentLabel(s)}</span>
                      {i < specialists.length - 1 ? ", " : ""}
                    </span>
                  ))}
                </p>
              )}
              {conflicts.length > 0 && <ConflictsPanel conflicts={conflicts} />}
              <ol className="relative space-y-1" aria-label="Steps">
                {segments.map((seg, i) =>
                  seg.kind === "shared" ? (
                    seg.steps.map((step) => (
                      <li key={step.ordinal} className="relative pl-5">
                        <SpineDot />
                        <StepRow step={step} />
                      </li>
                    ))
                  ) : (
                    <li key={`lanes-${i}`} className="relative pl-5">
                      <SpineDot branch />
                      <div
                        className="grid gap-2"
                        style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, 14rem), 1fr))` }}
                      >
                        {seg.lanes.map((lane) => (
                          <section
                            key={lane.agent}
                            aria-label={`${agentLabel(lane.agent)} agent`}
                            className="min-w-0 rounded-md border border-rule bg-paper"
                          >
                            <header className="flex items-center justify-between border-b border-rule px-2.5 py-1.5">
                              <span className="text-xs font-semibold text-ink">{agentLabel(lane.agent)}</span>
                              <span className="font-mono text-[11px] text-ink-3 tabular">
                                {lane.steps.reduce((n, s) => n + s.tool_calls.length, 0)} tools
                              </span>
                            </header>
                            <div className="space-y-0.5 p-1">
                              {lane.steps.map((step) => (
                                <StepRow key={step.ordinal} step={step} />
                              ))}
                            </div>
                          </section>
                        ))}
                      </div>
                    </li>
                  ),
                )}
                <span aria-hidden className="absolute top-2 bottom-2 left-[5px] w-px bg-rule-strong" />
              </ol>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}

function SpineDot({ branch = false }: { branch?: boolean }) {
  return (
    <span
      aria-hidden
      className={cx(
        "absolute top-[11px] left-[2px] z-10 size-[7px] rounded-[1px] ring-2 ring-surface",
        branch ? "bg-accent" : "bg-ink-3",
      )}
    />
  );
}

function StepRow({ step }: { step: AgentStepOut }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(step.output || step.error || step.tool_calls.length);
  const denied = step.tool_calls.filter((tc) => !tc.authorized).length;
  const bodyId = useId();

  return (
    <div className={cx("rounded-[4px]", open && "bg-surface ring-1 ring-rule")}>
      <button
        type="button"
        onClick={() => hasDetail && setOpen(!open)}
        aria-expanded={hasDetail ? open : undefined}
        aria-controls={hasDetail ? bodyId : undefined}
        disabled={!hasDetail}
        className="flex w-full items-center gap-2 rounded-[4px] px-2 py-1.5 text-left text-xs transition-colors enabled:hover:bg-sunk disabled:cursor-default"
      >
        <span className="w-5 shrink-0 font-mono text-[11px] text-ink-3 tabular">{step.ordinal}</span>
        <span className="min-w-0 flex-1 truncate">
          <span className="font-medium text-ink">{humanize(step.node)}</span>
          {step.model && <span className="ml-1.5 font-mono text-[11px] text-ink-3">{step.model}</span>}
        </span>
        {step.error && (
          <span className="inline-flex items-center gap-1 font-medium text-accent-strong">
            <WarningIcon size={12} aria-hidden />
            Error
          </span>
        )}
        {denied > 0 && (
          <span className="inline-flex items-center gap-1 font-medium text-accent-strong">
            <ProhibitIcon size={12} aria-hidden />
            {denied} denied
          </span>
        )}
        {step.tool_calls.length > 0 && (
          <span className="shrink-0 font-mono text-[11px] text-ink-3 tabular">
            {step.tool_calls.length} {step.tool_calls.length === 1 ? "call" : "calls"}
          </span>
        )}
        <span className="w-12 shrink-0 text-right font-mono text-[11px] text-ink-3 tabular">{ms(step.latency_ms)}</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={SPRING}
            className="overflow-hidden"
          >
            <div className="space-y-2 px-2 pt-1 pb-2.5 text-xs">
              {step.error && <p className="text-accent-strong">{step.error}</p>}
              {step.output && <JsonBlock label="Output" value={step.output} />}
              {step.tool_calls.map((tc, i) => (
                <ToolCallRow key={i} call={tc} />
              ))}
              {(step.tokens_in != null || step.tokens_out != null) && (
                <p className="font-mono text-[11px] text-ink-3 tabular">
                  {step.tokens_in ?? 0} in · {step.tokens_out ?? 0} out tokens
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ToolCallRow({ call }: { call: ToolCallOut }) {
  return (
    <div className={cx("rounded-[4px] border", call.authorized ? "border-rule" : "border-accent/40 bg-accent-soft/40")}>
      <div className="flex items-center justify-between gap-2 border-b border-rule/70 px-2 py-1">
        <span className="font-mono text-[12px] font-medium text-ink">{call.tool_name}</span>
        <span className="flex items-center gap-2 font-mono text-[11px] text-ink-3 tabular">
          {call.authorized ? (
            <span className="inline-flex items-center gap-1 text-moss">
              <CheckIcon size={12} aria-hidden />
              allowed
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-accent-strong">
              <HandPalmIcon size={12} aria-hidden />
              denied{call.deny_reason ? `: ${call.deny_reason}` : ""}
            </span>
          )}
          {ms(call.latency_ms)}
        </span>
      </div>
      <div className="space-y-1 p-2">
        <JsonBlock label="Arguments" value={call.arguments} inline />
        {call.result && <JsonBlock label="Result" value={call.result} inline />}
      </div>
    </div>
  );
}

function JsonBlock({ label, value, inline = false }: { label: string; value: unknown; inline?: boolean }) {
  return (
    <div>
      <p className="mb-0.5 text-[11px] font-medium text-ink-3">{label}</p>
      <pre
        className={cx(
          "max-h-72 overflow-auto rounded-[3px] bg-sunk px-2 py-1.5 font-mono text-[11px] leading-relaxed text-ink-2",
          inline ? "whitespace-pre-wrap break-all" : "whitespace-pre",
        )}
      >
        {inline ? JSON.stringify(value) : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

const KIND_LABEL: Record<ConflictOut["kind"], string> = {
  action: "Actions clashed",
  fact: "Facts disagreed",
  duplicate: "Same action twice",
};

function ConflictsPanel({ conflicts }: { conflicts: ConflictOut[] }) {
  return (
    <section aria-label="Conflicts between agents" className="rounded-md border border-accent/35 bg-accent-soft/35">
      <header className="flex items-center gap-2 border-b border-accent/25 px-3 py-2">
        <ScalesIcon size={16} aria-hidden className="text-accent-strong" />
        <h4 className="font-display text-[13px] font-semibold text-ink">
          Conflicts between agents
          <span className="ml-1.5 font-mono text-xs font-normal text-ink-3 tabular">{conflicts.length}</span>
        </h4>
      </header>
      <ul className="divide-y divide-accent/20">
        {conflicts.map((c, i) => (
          <li key={i} className="px-3 py-2.5 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="font-medium text-ink">
                {KIND_LABEL[c.kind] ?? humanize(c.kind)}
                <span className="font-normal text-ink-3">
                  {" "}
                  between {c.agents.map(agentLabel).join(" and ")}
                </span>
              </p>
              <span className="font-mono text-xs text-ink-2">{c.subject}</span>
            </div>
            <p className="mt-1 text-ink-2">{c.detail}</p>
            <dl className="mt-2 grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-ink-3">Settled by</dt>
              <dd className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                {c.resolution === "escalated" ? (
                  <span className="font-medium text-accent-strong">Sent to a person</span>
                ) : (
                  <span className="text-ink-2">Rule</span>
                )}
                <code className="rounded-[3px] bg-surface px-1 py-px font-mono text-[11px] text-ink">{c.rule}</code>
              </dd>
              {c.kept && (
                <>
                  <dt className="text-ink-3">Kept</dt>
                  <dd className="flex items-start gap-1.5 text-ink">
                    <CheckIcon size={13} aria-hidden className="mt-0.5 shrink-0 text-moss" />
                    {c.kept}
                  </dd>
                </>
              )}
              {c.dropped.length > 0 && (
                <>
                  <dt className="text-ink-3">Not used</dt>
                  <dd className="space-y-0.5">
                    {c.dropped.map((d, j) => (
                      <span key={j} className="flex items-start gap-1.5 text-ink-3">
                        <XIcon size={13} aria-hidden className="mt-0.5 shrink-0" />
                        <span className="line-through decoration-ink-4">{d}</span>
                      </span>
                    ))}
                  </dd>
                </>
              )}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}
