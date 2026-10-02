import {
  ArrowLeftIcon,
  ArrowUUpLeftIcon,
  CheckCircleIcon,
  HandGrabbingIcon,
  PaperPlaneRightIcon,
  SparkleIcon,
  TrayIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, getRouteApi } from "@tanstack/react-router";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { AppShell } from "../components/AppShell";
import { Tabs } from "../components/Tabs";
import { Transcript } from "../components/Transcript";
import {
  Button,
  EmptyState,
  ErrorState,
  PanelHeading,
  PriorityMark,
  Skeleton,
  SkeletonRows,
  StatusMark,
  TextArea,
} from "../components/ui";
import { consoleApi, type EscalationDetail } from "../lib/console-api";
import { cx } from "../lib/cx";
import { errorMessage, humanize, relativeTime } from "../lib/format";

const route = getRouteApi("/console");

export type ConsoleSearch = { escalation?: number };

type QueueTab = "queue" | "mine";

export function ConsolePage() {
  const { escalation: selectedId } = route.useSearch();
  const navigate = useNavigate({ from: "/console" });
  const [tab, setTab] = useState<QueueTab>("queue");

  const queueQuery = useQuery({
    queryKey: ["console", "queue", tab],
    queryFn: () => consoleApi.queue(tab === "mine" ? { mine: true } : undefined),
    refetchInterval: 5000,
  });

  return (
    <AppShell>
      <div className="flex h-full">
        <aside
          aria-label="Escalation queue"
          className={cx(
            "flex w-full flex-col border-r border-rule bg-surface lg:w-80 lg:shrink-0",
            selectedId != null && "hidden lg:flex",
          )}
        >
          <div className="border-b border-rule px-4 pt-4">
            <div className="flex items-baseline justify-between">
              <h1 className="text-xl font-semibold">Escalations</h1>
              <span className="font-mono text-xs text-ink-3 tabular">
                {queueQuery.data ? `${queueQuery.data.length} ${tab === "mine" ? "claimed" : "open"}` : ""}
              </span>
            </div>
            <Tabs<QueueTab>
              label="Queue filter"
              className="mt-2 -ml-2"
              value={tab}
              onChange={setTab}
              items={[
                { value: "queue", label: "All open" },
                { value: "mine", label: "Claimed by me" },
              ]}
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {queueQuery.isPending ? (
              <SkeletonRows rows={6} />
            ) : queueQuery.isError ? (
              <ErrorState error={queueQuery.error} onRetry={() => queueQuery.refetch()} />
            ) : queueQuery.data.length === 0 ? (
              <EmptyState icon={TrayIcon} title={tab === "mine" ? "Nothing claimed" : "Queue is clear"}>
                {tab === "mine"
                  ? "Claim an escalation from the open list to work on it."
                  : "When the AI hands a ticket to a person, it shows up here with a summary."}
              </EmptyState>
            ) : (
              <ul className="divide-y divide-rule">
                {queueQuery.data.map((esc) => {
                  const selected = selectedId === esc.id;
                  return (
                    <li key={esc.id}>
                      <button
                        type="button"
                        onClick={() => navigate({ search: { escalation: esc.id } })}
                        aria-current={selected ? "true" : undefined}
                        className={cx(
                          "relative block w-full px-4 py-3 text-left transition-colors duration-100 hover:bg-paper",
                          selected && "bg-paper",
                        )}
                      >
                        {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-accent" />}
                        <span className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[13px] font-medium text-ink">{esc.ticket_reference}</span>
                          <PriorityMark priority={esc.priority} />
                        </span>
                        <span className="mt-1 block truncate text-sm text-ink-2">{humanize(esc.reason_code)}</span>
                        <span className="mt-1 flex items-center justify-between gap-2">
                          <StatusMark status={esc.status} />
                          <time
                            dateTime={esc.created_at}
                            className="font-mono text-[11px] text-ink-3 tabular"
                            title={new Date(esc.created_at).toLocaleString()}
                          >
                            {relativeTime(esc.created_at)}
                          </time>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        <section className={cx("min-w-0 flex-1 overflow-y-auto", !selectedId && "hidden lg:block")}>
          {selectedId ? (
            <WorkView key={selectedId} escalationId={selectedId} onBack={() => navigate({ search: {} })} />
          ) : (
            <div className="flex h-full items-center px-10">
              <div className="max-w-sm">
                <p className="font-display text-lg font-medium text-ink">Pick an escalation to work on it.</p>
                <p className="mt-2 text-sm text-ink-3">
                  Each one comes with the AI's summary, the customer's details and a suggested reply. You can
                  answer the customer, hand the ticket back to the AI with a note, or close it.
                </p>
              </div>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

type Action = "reply" | "return" | "resolve";

function WorkView({ escalationId, onBack }: { escalationId: number; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<Action>("reply");
  const [replyText, setReplyText] = useState("");
  const [note, setNote] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  const detailQuery = useQuery({
    queryKey: ["console", "escalation", escalationId],
    queryFn: () => consoleApi.detail(escalationId),
  });

  const transcriptQuery = useQuery({
    queryKey: ["console", "transcript", escalationId],
    queryFn: () => consoleApi.transcript(escalationId),
    refetchInterval: 5000,
  });

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["console", "queue"] }),
      queryClient.invalidateQueries({ queryKey: ["console", "escalation", escalationId] }),
      queryClient.invalidateQueries({ queryKey: ["console", "transcript", escalationId] }),
    ]);
  }

  async function run(task: () => Promise<unknown>, done: string, reset: () => void) {
    setBusy(true);
    setFeedback(null);
    try {
      await task();
      reset();
      setFeedback({ tone: "ok", text: done });
      await refreshAll();
    } catch (err) {
      setFeedback({ tone: "error", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <button
      type="button"
      onClick={onBack}
      className="mb-2 inline-flex min-h-9 items-center gap-1.5 text-sm text-ink-3 hover:text-ink lg:hidden"
    >
      <ArrowLeftIcon size={14} aria-hidden />
      Queue
    </button>
  );

  if (detailQuery.isPending) {
    return (
      <div className="space-y-4 px-6 py-5" aria-busy="true">
        {back}
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (detailQuery.isError) {
    return (
      <div className="px-6 py-5">
        {back}
        <ErrorState error={detailQuery.error} onRetry={() => detailQuery.refetch()} className="px-0" />
      </div>
    );
  }

  const esc = detailQuery.data;
  const packet = esc.handoff_packet;
  const closed = esc.status === "resolved" || esc.status === "returned_to_ai";

  return (
    <div className="grid min-h-full xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <section aria-label="Handoff packet" className="border-rule bg-surface px-5 py-5 sm:px-6 xl:border-r">
        {back}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="font-mono text-2xl font-medium tracking-tight">{esc.ticket_reference}</h2>
          <PriorityMark priority={esc.priority} />
          <StatusMark status={esc.status} />
        </div>
        <p className="mt-1 text-sm text-ink-2">
          {humanize(esc.reason_code)}
          {esc.required_skill && <span className="text-ink-3"> · needs {humanize(esc.required_skill)}</span>}
        </p>

        {esc.status === "queued" && (
          <Button
            variant="primary"
            icon={HandGrabbingIcon}
            onClick={() => run(() => consoleApi.claim(escalationId), "Claimed. It's yours now.", () => {})}
            disabled={busy}
            className="mt-4 w-full sm:w-auto"
          >
            Claim this escalation
          </Button>
        )}

        <div className="mt-6">
          <PanelHeading
            aside={
              packet.ai_confidence != null ? (
                <span className="font-mono tabular">AI confidence {Math.round(packet.ai_confidence * 100)}%</span>
              ) : undefined
            }
          >
            What happened
          </PanelHeading>
          <p className="mt-2 text-[15px] leading-relaxed text-ink">{packet.summary}</p>
          {packet.reason_detail && <p className="mt-2 text-sm text-ink-3">{packet.reason_detail}</p>}
        </div>

        <dl className="mt-6 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 border-t border-rule pt-4 text-sm">
          <dt className="text-ink-3">Customer</dt>
          <dd className="text-ink">
            {packet.customer.name ?? "Unknown"}
            <span className="text-ink-3"> · {humanize(packet.customer.tier)}</span>
            {!packet.customer.verified && <span className="ml-1.5 text-xs font-medium text-ochre">Not verified</span>}
          </dd>
          {packet.intent && (
            <>
              <dt className="text-ink-3">Intent</dt>
              <dd className="text-ink">{humanize(packet.intent)}</dd>
            </>
          )}
          {Object.entries(packet.entities).map(([k, v]) => (
            <Entity key={k} name={k} value={v} />
          ))}
        </dl>

        {packet.timeline.length > 0 && (
          <div className="mt-6 border-t border-rule pt-4">
            <PanelHeading>Timeline</PanelHeading>
            <ol className="mt-3 space-y-3 border-l border-rule-strong pl-4">
              {packet.timeline.map((step, i) => (
                <li key={i} className="relative text-sm">
                  <span aria-hidden className="absolute top-1.5 -left-[19.5px] size-1.5 rounded-[1px] bg-ink-3" />
                  <p className="text-xs font-medium text-ink-3">{humanize(step.who)}</p>
                  <p className="text-ink-2">{step.what}</p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      <section aria-label="Conversation" className="flex min-h-[32rem] flex-col px-5 py-5 sm:px-6">
        <PanelHeading aside={transcriptQuery.data ? `${transcriptQuery.data.length} messages` : undefined}>
          Conversation
        </PanelHeading>
        <div className="mt-1 min-h-0 flex-1">
          {transcriptQuery.isPending ? (
            <SkeletonRows rows={4} />
          ) : transcriptQuery.isError ? (
            <ErrorState error={transcriptQuery.error} onRetry={() => transcriptQuery.refetch()} className="px-0" />
          ) : (
            <Transcript messages={transcriptQuery.data} />
          )}
        </div>

        {closed ? (
          <p className="mt-4 border-t border-rule pt-4 text-sm text-ink-3">
            {esc.status === "resolved" ? "This escalation is resolved." : "This ticket is back with the AI."}
            {esc.human_note && <span className="mt-1 block text-ink-2">Note: {esc.human_note}</span>}
          </p>
        ) : (
          <Composer
            esc={esc}
            action={action}
            setAction={(a) => {
              setAction(a);
              setFeedback(null);
            }}
            busy={busy}
            replyText={replyText}
            setReplyText={setReplyText}
            note={note}
            setNote={setNote}
            summary={summary}
            setSummary={setSummary}
            onReply={() => run(() => consoleApi.reply(escalationId, replyText), "Reply sent.", () => setReplyText(""))}
            onReturn={() =>
              run(() => consoleApi.returnToAI(escalationId, note), "Handed back to the AI.", () => setNote(""))
            }
            onResolve={() =>
              run(() => consoleApi.resolve(escalationId, summary), "Resolved.", () => setSummary(""))
            }
          />
        )}

        <AnimatePresence>
          {feedback && (
            <motion.p
              key={feedback.text}
              role={feedback.tone === "error" ? "alert" : "status"}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ type: "spring", bounce: 0, duration: 0.25 }}
              className={cx(
                "mt-3 inline-flex items-center gap-1.5 text-sm",
                feedback.tone === "ok" ? "text-moss" : "text-accent-strong",
              )}
            >
              {feedback.tone === "ok" ? (
                <CheckCircleIcon size={16} aria-hidden />
              ) : (
                <WarningCircleIcon size={16} aria-hidden />
              )}
              {feedback.text}
            </motion.p>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}

function Entity({ name, value }: { name: string; value: string }) {
  return (
    <>
      <dt className="text-ink-3">{humanize(name)}</dt>
      <dd className="font-mono text-[13px] break-all text-ink">{value}</dd>
    </>
  );
}

function Composer(props: {
  esc: EscalationDetail;
  action: Action;
  setAction: (a: Action) => void;
  busy: boolean;
  replyText: string;
  setReplyText: (v: string) => void;
  note: string;
  setNote: (v: string) => void;
  summary: string;
  setSummary: (v: string) => void;
  onReply: () => void;
  onReturn: () => void;
  onResolve: () => void;
}) {
  const { esc, action, setAction, busy } = props;
  const suggested = esc.handoff_packet.suggested_reply;

  return (
    <div className="mt-4 rounded-md border border-rule-strong bg-surface">
      <Tabs<Action>
        label="What to do next"
        className="border-b border-rule px-2"
        value={action}
        onChange={setAction}
        items={[
          { value: "reply", label: "Reply" },
          { value: "return", label: "Hand back to AI" },
          { value: "resolve", label: "Resolve" },
        ]}
      />
      <div className="p-3">
        {action === "reply" && (
          <>
            <label htmlFor="reply" className="sr-only">
              Reply to the customer
            </label>
            <TextArea
              id="reply"
              value={props.replyText}
              onChange={(e) => props.setReplyText(e.target.value)}
              placeholder="Write to the customer…"
              rows={4}
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              {suggested ? (
                <Button size="sm" variant="quiet" icon={SparkleIcon} onClick={() => props.setReplyText(suggested)}>
                  Use the AI's draft
                </Button>
              ) : (
                <span />
              )}
              <Button
                variant="primary"
                icon={PaperPlaneRightIcon}
                onClick={props.onReply}
                disabled={busy || !props.replyText.trim()}
              >
                {busy ? "Sending…" : "Send reply"}
              </Button>
            </div>
          </>
        )}
        {action === "return" && (
          <>
            <label htmlFor="note" className="text-xs text-ink-3">
              The AI resumes the conversation with this note as an instruction.
            </label>
            <TextArea
              id="note"
              value={props.note}
              onChange={(e) => props.setNote(e.target.value)}
              placeholder="For example: refund approved, tell the customer 5 to 7 business days."
              rows={3}
              className="mt-1.5"
            />
            <div className="mt-2 flex justify-end">
              <Button
                variant="primary"
                icon={ArrowUUpLeftIcon}
                onClick={props.onReturn}
                disabled={busy || !props.note.trim()}
              >
                {busy ? "Handing back…" : "Hand back to AI"}
              </Button>
            </div>
          </>
        )}
        {action === "resolve" && (
          <>
            <label htmlFor="summary" className="text-xs text-ink-3">
              A one-line summary for the ticket record.
            </label>
            <TextArea
              id="summary"
              value={props.summary}
              onChange={(e) => props.setSummary(e.target.value)}
              placeholder="For example: refunded the duplicate charge of INR 1,499."
              rows={2}
              className="mt-1.5"
            />
            <div className="mt-2 flex justify-end">
              <Button
                variant="primary"
                icon={CheckCircleIcon}
                onClick={props.onResolve}
                disabled={busy || !props.summary.trim()}
              >
                {busy ? "Resolving…" : "Resolve"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
