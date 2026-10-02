import { CheckCircleIcon, CheckIcon, ReceiptIcon, WarningCircleIcon, XIcon } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { AppShell } from "../components/AppShell";
import { Button, EmptyState, ErrorState, SkeletonRows, TextArea } from "../components/ui";
import { APPROVALS_KEY, consoleApi, type ApprovalOut } from "../lib/console-api";
import { cx } from "../lib/cx";
import { errorMessage, inr, relativeTime } from "../lib/format";

const STALE_AFTER_MS = 24 * 60 * 60 * 1000;
const SPRING = { type: "spring", bounce: 0, duration: 0.3 } as const;

type Decision = { kind: "approve"; refund: ApprovalOut } | { kind: "reject"; refund: ApprovalOut; note: string };
type Notice = { tone: "ok" | "error"; text: string };

function omit<T>(record: Record<number, T>, id: number): Record<number, T> {
  const next = { ...record };
  delete next[id];
  return next;
}

function byAge(a: ApprovalOut, b: ApprovalOut) {
  return a.created_at.localeCompare(b.created_at);
}

function refundLabel(refund: ApprovalOut) {
  return refund.ticket_reference ?? `refund #${refund.refund_id}`;
}

export function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [failed, setFailed] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);

  const query = useQuery({
    queryKey: APPROVALS_KEY,
    queryFn: consoleApi.approvals,
    refetchInterval: 10000,
  });

  const decide = useMutation({
    mutationFn: (d: Decision): Promise<unknown> =>
      d.kind === "approve" ? consoleApi.approve(d.refund.refund_id) : consoleApi.reject(d.refund.refund_id, d.note),
    onMutate: async (d) => {
      const id = d.refund.refund_id;
      await queryClient.cancelQueries({ queryKey: APPROVALS_KEY });
      queryClient.setQueryData<ApprovalOut[]>(APPROVALS_KEY, (old) => old?.filter((a) => a.refund_id !== id));
      setFailed((f) => omit(f, id));
      setNotice(null);
      setRejectingId((current) => (current === id ? null : current));
    },
    onError: (err, d) => {
      const id = d.refund.refund_id;
      // Put back only this row. Restoring a whole snapshot would also undo
      // any other decision that succeeded in the meantime.
      queryClient.setQueryData<ApprovalOut[]>(APPROVALS_KEY, (old) =>
        old && !old.some((a) => a.refund_id === id) ? [...old, d.refund].sort(byAge) : old,
      );
      const verb = d.kind === "approve" ? "approve" : "reject";
      setFailed((f) => ({ ...f, [id]: errorMessage(err) }));
      setNotice({ tone: "error", text: `Could not ${verb} ${refundLabel(d.refund)}. ${errorMessage(err)}` });
      if (d.kind === "reject") setRejectingId(id);
    },
    onSuccess: (_data, d) => {
      const id = d.refund.refund_id;
      setDrafts((d) => omit(d, id));
      setNotice({
        tone: "ok",
        text:
          d.kind === "approve"
            ? `Approved ₹${inr(d.refund.amount)} for ${refundLabel(d.refund)}. The customer has been told.`
            : `Rejected the refund for ${refundLabel(d.refund)}. The customer has your note.`,
      });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: APPROVALS_KEY }),
  });

  const items = query.data ?? [];

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[96rem] px-4 py-5 sm:px-6">
          <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
            <div className="flex items-baseline gap-3">
              <h1 className="text-xl font-semibold">Refund approvals</h1>
              {query.data && (
                <span className="font-mono text-xs text-ink-3 tabular">{items.length} waiting</span>
              )}
            </div>
            <p className="max-w-xl text-sm text-ink-3">
              Refunds the AI could not approve on its own: over the automatic limit, or with no failed or duplicate
              charge to back them up. The AI keeps the conversation either way.
            </p>
          </header>

          <AnimatePresence>
            {notice && (
              <motion.p
                key={notice.text}
                role={notice.tone === "error" ? "alert" : "status"}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={SPRING}
                className={cx(
                  "mt-4 flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
                  notice.tone === "ok"
                    ? "border-moss/30 bg-moss-soft text-moss"
                    : "border-accent/30 bg-accent-soft text-accent-strong",
                )}
              >
                {notice.tone === "ok" ? (
                  <CheckCircleIcon size={16} aria-hidden className="mt-0.5 shrink-0" />
                ) : (
                  <WarningCircleIcon size={16} aria-hidden className="mt-0.5 shrink-0" />
                )}
                <span className="min-w-0 flex-1">{notice.text}</span>
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  aria-label="Dismiss"
                  className="-mr-1 inline-flex size-6 shrink-0 items-center justify-center rounded-sm opacity-70 hover:opacity-100"
                >
                  <XIcon size={14} aria-hidden />
                </button>
              </motion.p>
            )}
          </AnimatePresence>

          <section aria-label="Refunds waiting for a decision" className="mt-4 rounded-md border border-rule bg-surface">
            {items.length > 0 && (
              <div
                aria-hidden
                className="approval-row hidden border-b border-rule bg-paper px-4 py-2 text-[11px] font-medium text-ink-3 xl:grid"
              >
                <span>Ticket</span>
                <span>Customer</span>
                <span>Order</span>
                <span>Transaction</span>
                <span className="text-right">Refund (INR)</span>
                <span>Reason</span>
                <span>Waiting</span>
                <span className="text-right">Decision</span>
              </div>
            )}

            {query.isPending ? (
              <SkeletonRows rows={5} />
            ) : query.isError ? (
              <ErrorState error={query.error} onRetry={() => query.refetch()} />
            ) : items.length === 0 ? (
              <EmptyState icon={ReceiptIcon} title="No refunds waiting">
                When the AI asks for a refund it is not allowed to approve itself, it lands here for a one-click
                decision.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-rule">
                <AnimatePresence initial={false}>
                  {items.map((refund) => (
                    <ApprovalRow
                      key={refund.refund_id}
                      refund={refund}
                      now={query.dataUpdatedAt}
                      rejecting={rejectingId === refund.refund_id}
                      draft={drafts[refund.refund_id] ?? ""}
                      error={failed[refund.refund_id]}
                      onDraft={(text) => setDrafts((d) => ({ ...d, [refund.refund_id]: text }))}
                      onApprove={() => decide.mutate({ kind: "approve", refund })}
                      onStartReject={() => setRejectingId(refund.refund_id)}
                      onCancelReject={() => setRejectingId(null)}
                      onReject={(note) => decide.mutate({ kind: "reject", refund, note })}
                    />
                  ))}
                </AnimatePresence>
              </ul>
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function ApprovalRow(props: {
  refund: ApprovalOut;
  /** When the list was last fetched. Ages are measured from here so render stays pure. */
  now: number;
  rejecting: boolean;
  draft: string;
  error: string | undefined;
  onDraft: (text: string) => void;
  onApprove: () => void;
  onStartReject: () => void;
  onCancelReject: () => void;
  onReject: (note: string) => void;
}) {
  const { refund, rejecting, draft, now } = props;
  const partial = Number(refund.amount) < Number(refund.payment_amount);
  const stale = now - new Date(refund.created_at).getTime() > STALE_AFTER_MS;
  const noteId = `reject-note-${refund.refund_id}`;
  const label = refundLabel(refund);

  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, height: 0 }}
      transition={SPRING}
      className="overflow-hidden"
      aria-label={`Refund for ${label}`}
    >
      <div className="approval-row px-4 py-3 text-sm">
        <div className="area-head flex min-w-0 items-baseline gap-2 xl:contents">
          {refund.ticket_id != null ? (
            <Link
              to="/admin/tickets/$ticketId"
              params={{ ticketId: String(refund.ticket_id) }}
              className="shrink-0 font-mono whitespace-nowrap text-[13px] font-medium text-ink underline decoration-rule-strong underline-offset-3 hover:decoration-ink"
            >
              {refund.ticket_reference ?? `#${refund.ticket_id}`}
            </Link>
          ) : (
            <span className="shrink-0 font-mono whitespace-nowrap text-[13px] text-ink-3" title="Not linked to a ticket">
              No ticket
            </span>
          )}
          <span className="truncate text-ink">{refund.customer_name ?? "Unknown customer"}</span>
        </div>

        <div className="area-ids flex min-w-0 flex-wrap gap-x-2 font-mono text-xs text-ink-3 xl:contents">
          <span className="xl:truncate xl:text-ink-2">{refund.order_number ?? "No order"}</span>
          <span className="xl:truncate" title={refund.txn_ref}>
            {refund.txn_ref}
          </span>
        </div>

        <div className="area-amount text-right font-mono tabular">
          <span className="block text-[15px] font-medium text-ink">
            <span className="text-ink-3 xl:hidden">₹</span>
            {inr(refund.amount)}
          </span>
          <span className="block text-xs whitespace-nowrap text-ink-3">
            of {inr(refund.payment_amount)}
            {partial ? " · partial" : " · full"}
          </span>
        </div>

        <p className="area-reason mt-1 text-ink-2 xl:mt-0 xl:line-clamp-2" title={refund.reason ?? undefined}>
          {refund.reason ?? <span className="text-ink-3">No reason given</span>}
        </p>

        <div className="area-meta flex flex-wrap items-center gap-x-2 gap-y-0.5 self-center text-xs xl:contents">
          <time
            dateTime={refund.created_at}
            title={new Date(refund.created_at).toLocaleString()}
            className={cx("font-mono whitespace-nowrap tabular", stale ? "font-medium text-ochre" : "text-ink-3")}
          >
            {relativeTime(refund.created_at, now)}
          </time>
          <span className="whitespace-nowrap text-ink-3 xl:hidden">· from {refund.requested_by_type === "ai" ? "AI" : "agent"}</span>
        </div>

        <div className="area-actions flex items-center justify-end gap-1.5 self-center">
          <Button
            size="sm"
            variant="quiet"
            icon={XIcon}
            onClick={props.onStartReject}
            disabled={rejecting}
            aria-expanded={rejecting}
            aria-controls={noteId}
          >
            Reject
          </Button>
          <Button size="sm" variant="primary" icon={CheckIcon} onClick={props.onApprove}>
            Approve
          </Button>
        </div>
      </div>

      {props.error && !rejecting && (
        <p role="alert" className="flex items-center gap-1.5 px-4 pb-3 text-xs text-accent-strong">
          <WarningCircleIcon size={14} aria-hidden />
          Last try failed: {props.error}
        </p>
      )}

      <AnimatePresence initial={false}>
        {rejecting && (
          <motion.form
            key="reject"
            id={noteId}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={SPRING}
            className="overflow-hidden"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) props.onReject(draft.trim());
            }}
          >
            <div className="mx-4 mb-3 rounded-md border border-rule-strong bg-paper p-3 xl:ml-auto xl:max-w-xl">
              <label htmlFor={`${noteId}-text`} className="text-xs font-medium text-ink">
                Why not? This goes to the customer.
              </label>
              <TextArea
                id={`${noteId}-text`}
                value={draft}
                onChange={(e) => props.onDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") props.onCancelReject();
                }}
                required
                autoFocus
                rows={3}
                placeholder="For example: the charge went through and the order was delivered on 12 Sep."
                className="mt-1.5 bg-surface"
              />
              {props.error && (
                <p role="alert" className="mt-1.5 flex items-center gap-1.5 text-xs text-accent-strong">
                  <WarningCircleIcon size={14} aria-hidden />
                  Last try failed: {props.error}
                </p>
              )}
              <div className="mt-2 flex items-center justify-end gap-1.5">
                <Button size="sm" variant="quiet" onClick={props.onCancelReject}>
                  Cancel
                </Button>
                <Button size="sm" variant="primary" type="submit" icon={XIcon} disabled={!draft.trim()}>
                  Reject refund
                </Button>
              </div>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.li>
  );
}
