import { ArrowLeftIcon, RobotIcon } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { Link, getRouteApi } from "@tanstack/react-router";
import { useState } from "react";
import { RunTrace } from "../components/RunTrace";
import { Tabs } from "../components/Tabs";
import { Transcript } from "../components/Transcript";
import { ChannelMark, EmptyState, ErrorState, PanelHeading, PriorityMark, Skeleton, StatusMark } from "../components/ui";
import { adminApi, type TicketDetail } from "../lib/admin-api";
import { clockTime, humanize, relativeTime, statusLabel } from "../lib/format";

const route = getRouteApi("/admin/tickets/$ticketId");

type Tab = "conversation" | "reasoning";

export function TicketDetailPage() {
  const { ticketId } = route.useParams();
  const id = Number(ticketId);
  const [tab, setTab] = useState<Tab>("conversation");

  const ticketQuery = useQuery({
    queryKey: ["admin", "ticket", id],
    queryFn: () => adminApi.ticket(id),
    refetchInterval: 10000,
  });
  const runsQuery = useQuery({
    queryKey: ["admin", "ticket", id, "runs"],
    queryFn: () => adminApi.ticketRuns(id),
    refetchInterval: 10000,
  });

  if (ticketQuery.isPending) return <DetailSkeleton />;
  if (ticketQuery.isError) {
    return (
      <div>
        <BackLink />
        <ErrorState error={ticketQuery.error} onRetry={() => ticketQuery.refetch()} />
      </div>
    );
  }

  const ticket = ticketQuery.data;
  const runCount = runsQuery.data?.length;
  const conflictCount = runsQuery.data?.reduce((n, r) => n + (r.conflicts?.length ?? 0), 0) ?? 0;

  return (
    <div className="min-h-full bg-surface">
      <header className="border-b border-rule px-5 pt-4 sm:px-6">
        <BackLink />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h2 className="font-mono text-2xl font-medium tracking-tight text-ink">{ticket.reference}</h2>
          <StatusMark status={ticket.status} />
        </div>
        <TicketFacts ticket={ticket} />
        {ticket.resolution && (
          <p className="mt-3 max-w-[70ch] text-sm text-ink-2">
            <span className="font-medium text-ink">{humanize(ticket.resolution)}.</span>{" "}
            {ticket.resolution_summary}
          </p>
        )}
        <Tabs<Tab>
          label="Ticket views"
          className="mt-3 -ml-2"
          value={tab}
          onChange={setTab}
          items={[
            { value: "conversation", label: "Conversation" },
            {
              value: "reasoning",
              label: (
                <>
                  AI reasoning
                  {runCount != null && <span className="font-mono text-xs text-ink-3 tabular">{runCount}</span>}
                  {conflictCount > 0 && (
                    <span
                      className="size-1.5 rounded-[1px] bg-accent"
                      title={`${conflictCount} conflicts between agents`}
                    />
                  )}
                </>
              ),
            },
          ]}
        />
      </header>

      {tab === "conversation" ? (
        <div className="grid gap-8 px-5 py-5 sm:px-6 2xl:grid-cols-[minmax(0,1fr)_18rem]">
          <section aria-label="Transcript">
            <PanelHeading aside={`${ticket.messages.length} messages`}>Transcript</PanelHeading>
            <div className="mt-1">
              <Transcript messages={ticket.messages} />
            </div>
          </section>
          <section aria-label="Status history">
            <PanelHeading>Status history</PanelHeading>
            {ticket.events.length === 0 ? (
              <p className="mt-3 text-sm text-ink-3">No status changes yet.</p>
            ) : (
              <ol className="mt-3 space-y-3 border-l border-rule-strong pl-4">
                {ticket.events.map((e, i) => (
                  <li key={i} className="relative text-sm">
                    <span aria-hidden className="absolute top-1.5 -left-[19.5px] size-1.5 rounded-[1px] bg-ink-3" />
                    <p className="text-ink">
                      {e.from_status && e.to_status ? (
                        <>
                          {statusLabel(e.from_status)} <span className="text-ink-3">to</span> {statusLabel(e.to_status)}
                        </>
                      ) : (
                        humanize(e.event_type)
                      )}
                    </p>
                    <p className="font-mono text-[11px] text-ink-3 tabular">
                      {clockTime(e.created_at)} · {humanize(e.actor_type)}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      ) : (
        <section aria-label="AI reasoning">
          {runsQuery.isPending ? (
            <div className="space-y-3 px-6 py-5">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : runsQuery.isError ? (
            <ErrorState error={runsQuery.error} onRetry={() => runsQuery.refetch()} />
          ) : runsQuery.data.length === 0 ? (
            <EmptyState icon={RobotIcon} title="The AI hasn't worked on this ticket">
              Runs appear here once the AI picks up a message: every step, tool call and token count.
            </EmptyState>
          ) : (
            <div>
              {[...runsQuery.data].reverse().map((run, i) => (
                <RunTrace key={run.id} run={run} defaultOpen={i === 0} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/admin/tickets"
      search={(prev) => prev}
      className="mb-2 inline-flex min-h-9 items-center gap-1.5 text-sm text-ink-3 hover:text-ink lg:hidden"
    >
      <ArrowLeftIcon size={14} aria-hidden />
      All tickets
    </Link>
  );
}

function TicketFacts({ ticket }: { ticket: TicketDetail }) {
  const facts: [string, React.ReactNode][] = [
    ["Channel", <ChannelMark key="c" channel={ticket.channel} />],
    ["Intent", humanize(ticket.intent)],
    ["Priority", <PriorityMark key="p" priority={ticket.priority} />],
    ["Sentiment", humanize(ticket.sentiment)],
    ["AI turns", <span key="t" className="font-mono tabular">{ticket.ai_turns}</span>],
    ["Assigned", ticket.assigned_agent ?? "Nobody"],
    [
      "Opened",
      <time key="o" dateTime={ticket.created_at} title={new Date(ticket.created_at).toLocaleString()}>
        {relativeTime(ticket.created_at)}
      </time>,
    ],
  ];
  return (
    <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 sm:flex sm:flex-wrap">
      {facts.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-[11px] text-ink-3">{label}</dt>
          <dd className="mt-0.5 truncate text-sm text-ink sm:whitespace-nowrap">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4 px-6 py-5" aria-busy="true" aria-label="Loading ticket">
      <Skeleton className="h-7 w-40" />
      <div className="grid grid-cols-4 gap-6">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </div>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
