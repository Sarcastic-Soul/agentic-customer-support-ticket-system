import { useEffect, useState } from "react";
import { fetchMyTickets, type CustomerTicket } from "../../lib/customer";
import { cx } from "../../lib/cx";
import { humanize, relativeTime } from "../../lib/format";

/* Customers don't need to know whether the AI or a person holds the
 * ticket internally - only whether it's still open and who to expect. */
const CUSTOMER_STATUS: Record<string, [string, string]> = {
  new: ["Open", "bg-slate"],
  ai_working: ["Open", "bg-slate"],
  escalated: ["With our team", "bg-ochre"],
  human_working: ["With our team", "bg-ochre"],
  closed: ["Closed", "bg-ink-4"],
};

function CustomerStatus({ status }: { status: string }) {
  const [label, dot] = CUSTOMER_STATUS[status] ?? [humanize(status), "bg-ink-4"];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span aria-hidden className={cx("size-1.5 rounded-[1px]", dot)} />
      {label}
    </span>
  );
}

/** The signed-in customer's past tickets. Plain fetch, same as before the
 * restyle - the customer side has no react-query client of its own. */
export function TicketList({ customerId }: { customerId: number }) {
  const [tickets, setTickets] = useState<CustomerTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMyTickets(customerId)
      .then((data) => {
        if (!cancelled) setTickets(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load your past tickets.");
      });
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  if (error) return <p className="px-4 py-3 text-sm text-accent-strong">{error}</p>;
  if (tickets === null) return <p className="px-4 py-3 text-sm text-ink-3">Loading your tickets…</p>;
  if (tickets.length === 0) {
    return <p className="px-4 py-3 text-sm text-ink-3">No past tickets. Anything you ask here gets a reference number.</p>;
  }

  return (
    <ul className="divide-y divide-rule">
      {tickets.map((t) => (
        <li key={t.id} className="px-4 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[13px] font-medium text-ink">{t.reference}</span>
            <CustomerStatus status={t.status} />
          </div>
          <div className="mt-0.5 flex items-center justify-between gap-2 text-xs text-ink-3">
            <span className="truncate">{humanize(t.intent)}</span>
            <time dateTime={t.created_at} className="shrink-0 font-mono tabular">
              {relativeTime(t.created_at)}
            </time>
          </div>
        </li>
      ))}
    </ul>
  );
}
