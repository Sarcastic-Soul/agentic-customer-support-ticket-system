import { HeadsetIcon, RobotIcon, UserIcon, type Icon } from "@phosphor-icons/react";
import { cx } from "../lib/cx";
import { humanize } from "../lib/format";

export type TranscriptLine = {
  id: number;
  role: string;
  body: string;
  created_at: string;
  delivery_status?: string | null;
};

const ROLE: Record<string, { label: string; icon: Icon; mark: string }> = {
  customer: { label: "Customer", icon: UserIcon, mark: "text-ink-3" },
  assistant: { label: "AI", icon: RobotIcon, mark: "text-ink" },
  human_agent: { label: "Agent", icon: HeadsetIcon, mark: "text-ochre" },
};

/** Read-only conversation log for agents: a ledger, not chat bubbles, so
 * long transcripts scan top to bottom without zig-zagging. */
export function Transcript({ messages }: { messages: TranscriptLine[] }) {
  if (messages.length === 0) {
    return <p className="py-6 text-sm text-ink-3">No messages on this ticket yet.</p>;
  }
  return (
    <ol className="divide-y divide-rule">
      {messages.map((m) => {
        const role = ROLE[m.role] ?? { label: humanize(m.role), icon: UserIcon, mark: "text-ink-3" };
        const RoleIcon = role.icon;
        const failed = m.delivery_status && !["sent", "delivered", "read"].includes(m.delivery_status);
        return (
          <li key={m.id} className="grid grid-cols-[4.75rem_minmax(0,1fr)] gap-3 py-3 sm:grid-cols-[6rem_minmax(0,1fr)]">
            <div className="pt-px">
              <span className={cx("inline-flex items-center gap-1.5 text-xs font-semibold", role.mark)}>
                <RoleIcon size={14} aria-hidden />
                {role.label}
              </span>
              <time dateTime={m.created_at} className="mt-0.5 block font-mono text-[11px] text-ink-3 tabular">
                {new Date(m.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </time>
            </div>
            <div className="min-w-0">
              <p
                className={cx(
                  "max-w-[68ch] text-sm leading-relaxed whitespace-pre-wrap break-words",
                  m.role === "customer" ? "text-ink-2" : "text-ink",
                )}
              >
                {m.body}
              </p>
              {m.delivery_status && m.delivery_status !== "sent" && (
                <p className={cx("mt-1 text-xs", failed ? "text-accent-strong" : "text-ink-3")}>
                  {humanize(m.delivery_status)}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
