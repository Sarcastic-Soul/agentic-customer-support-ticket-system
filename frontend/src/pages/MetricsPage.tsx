import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState, PanelHeading, Skeleton } from "../components/ui";
import { adminApi } from "../lib/admin-api";
import { cx } from "../lib/cx";
import { agentLabel, duration, humanize, percent, usd } from "../lib/format";

const RANGE_OPTIONS: [number, string][] = [
  [1, "Today"],
  [7, "7 days"],
  [30, "30 days"],
];

/* Chart colors come from the same tokens as the rest of the UI. The accent
 * only ever marks escalations, so it keeps one meaning everywhere. */
const INK_2 = "#4f4a42";
const ACCENT = "#c8461b";
const RULE = "#e4e0d7";
const INK_3 = "#6f695f";

const CHANNEL_LABEL: Record<string, string> = { web: "Web", whatsapp: "WhatsApp", email: "Email", voice: "Voice" };

export function MetricsPage() {
  const [rangeDays, setRangeDays] = useState(7);

  const overview = useQuery({
    queryKey: ["admin", "metrics", "overview", rangeDays],
    queryFn: () => adminApi.metricsOverview(rangeDays),
    refetchInterval: 15000,
  });
  const channels = useQuery({
    queryKey: ["admin", "metrics", "channels", rangeDays],
    queryFn: () => adminApi.metricsChannels(rangeDays),
    refetchInterval: 15000,
  });
  const intents = useQuery({
    queryKey: ["admin", "metrics", "intents", rangeDays],
    queryFn: () => adminApi.metricsIntents(rangeDays),
    refetchInterval: 15000,
  });
  const escalations = useQuery({
    queryKey: ["admin", "metrics", "escalations", rangeDays],
    queryFn: () => adminApi.metricsEscalations(rangeDays),
    refetchInterval: 15000,
  });
  const agents = useQuery({
    queryKey: ["admin", "metrics", "agents", rangeDays],
    queryFn: () => adminApi.metricsAgents(rangeDays),
    refetchInterval: 15000,
    retry: (count, error) => !String(error).includes("404") && count < 2,
  });
  const agentsMissing = agents.isError && String(agents.error).includes("404");

  const o = overview.data;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[88rem] px-5 py-6 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Metrics</h1>
            <p className="mt-1 text-sm text-ink-3">Refreshes every 15 seconds.</p>
          </div>
          <div role="radiogroup" aria-label="Time range" className="inline-flex rounded-md border border-rule-strong bg-surface p-0.5">
            {RANGE_OPTIONS.map(([d, label]) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={rangeDays === d}
                onClick={() => setRangeDays(d)}
                className={cx(
                  "h-7 rounded-[4px] px-3 text-xs font-medium transition-colors duration-150",
                  rangeDays === d ? "bg-ink text-paper" : "text-ink-3 hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {overview.isError ? (
          <div className="mt-6 border border-rule bg-surface">
            <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-2 border-t border-l border-rule-strong bg-surface lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div className="col-span-2 border-r border-b border-rule-strong p-5 lg:col-span-1 lg:row-span-2">
              <p className="text-sm text-ink-2">Resolved by the AI alone</p>
              <div className="mt-3 font-display text-6xl leading-none font-semibold tracking-tight text-ink tabular">
                {o ? percent(o.ai_resolution_rate) : <Skeleton className="h-14 w-36" />}
              </div>
              <p className="mt-4 max-w-[30ch] text-sm text-ink-3">
                Share of closed tickets the AI finished without handing them to a person.
              </p>
            </div>
            <Figure label="Tickets" value={o?.total_tickets.toLocaleString()} note={o && `${o.closed_tickets} closed`} />
            <Figure label="Open now" value={o?.open_tickets.toLocaleString()} />
            <Figure label="Escalated to a person" value={o && percent(o.escalation_rate)} accent />
            <Figure label="First reply, average" value={o && duration(o.avg_first_response_seconds)} />
            <Figure label="Time to resolve, average" value={o && duration(o.avg_resolution_seconds)} />
            <Figure label="LLM spend, estimated" value={o && usd(o.total_est_cost_usd)} />
          </div>
        )}

        <div className="mt-8 grid gap-x-8 gap-y-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <Panel title="Tickets by channel" aside={<Legend />}>
            {channels.isPending ? (
              <Skeleton className="h-[240px] w-full" />
            ) : channels.isError ? (
              <ErrorState error={channels.error} onRetry={() => channels.refetch()} />
            ) : channels.data.length === 0 ? (
              <Empty>No tickets in this range.</Empty>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={channels.data.map((c) => ({ ...c, label: CHANNEL_LABEL[c.channel] ?? c.channel }))}
                  margin={{ top: 8, right: 4, left: -18, bottom: 0 }}
                  barCategoryGap="28%"
                >
                  <CartesianGrid vertical={false} stroke={RULE} />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={{ stroke: RULE }}
                    tick={{ fontSize: 12, fill: INK_3, fontFamily: "IBM Plex Sans" }}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 11, fill: INK_3, fontFamily: "IBM Plex Mono" }}
                  />
                  <Tooltip
                    cursor={{ fill: "#eeebe4" }}
                    contentStyle={{
                      background: "#fbfaf7",
                      border: `1px solid ${RULE}`,
                      borderRadius: 4,
                      fontSize: 12,
                      fontFamily: "IBM Plex Sans",
                      boxShadow: "0 4px 16px -8px rgba(60, 50, 35, 0.25)",
                    }}
                    labelStyle={{ color: "#1d1b18", fontWeight: 600 }}
                  />
                  <Bar dataKey="ai_resolved" stackId="a" fill={INK_2} name="Resolved by AI" />
                  <Bar dataKey="escalated" stackId="a" fill={ACCENT} name="Escalated" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Panel>

          <Panel title="Why tickets were escalated">
            {escalations.isPending ? (
              <Skeleton className="h-[240px] w-full" />
            ) : escalations.isError ? (
              <ErrorState error={escalations.error} onRetry={() => escalations.refetch()} />
            ) : escalations.data.length === 0 ? (
              <Empty>Nothing was escalated in this range.</Empty>
            ) : (
              <BarList
                rows={[...escalations.data]
                  .sort((a, b) => b.count - a.count)
                  .map((e) => ({ key: e.reason_code, label: humanize(e.reason_code), value: e.count }))}
                tone="accent"
              />
            )}
          </Panel>

          <Panel title="Top intents" aside="count · escalated">
            {intents.isPending ? (
              <Skeleton className="h-[240px] w-full" />
            ) : intents.isError ? (
              <ErrorState error={intents.error} onRetry={() => intents.refetch()} />
            ) : intents.data.length === 0 ? (
              <Empty>No classified tickets in this range.</Empty>
            ) : (
              <BarList
                rows={intents.data.map((i) => ({
                  key: i.intent,
                  label: humanize(i.intent),
                  value: i.count,
                  extra: percent(i.escalation_rate),
                }))}
                tone="ink"
              />
            )}
          </Panel>

          {!agentsMissing && (
            <Panel title="Specialist agents">
              {agents.isPending ? (
                <Skeleton className="h-[160px] w-full" />
              ) : agents.isError ? (
                <ErrorState error={agents.error} onRetry={() => agents.refetch()} />
              ) : agents.data.length === 0 ? (
                <Empty>No specialist agents ran in this range.</Empty>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-rule-strong text-left text-xs text-ink-3">
                        <th scope="col" className="py-2 pr-3 font-medium">Agent</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">Runs</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">Tool calls</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">Denied</th>
                        <th scope="col" className="py-2 pl-3 text-right font-medium">Conflicts</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-rule font-mono tabular">
                      {agents.data.map((a) => (
                        <tr key={a.agent}>
                          <th scope="row" className="py-2.5 pr-3 text-left font-sans font-medium text-ink">
                            {agentLabel(a.agent)}
                          </th>
                          <td className="px-3 py-2.5 text-right text-ink-2">{a.runs}</td>
                          <td className="px-3 py-2.5 text-right text-ink-2">{a.tool_calls}</td>
                          <td className={cx("px-3 py-2.5 text-right", a.denied ? "text-accent-strong" : "text-ink-3")}>
                            {a.denied}
                          </td>
                          <td className={cx("py-2.5 pl-3 text-right", a.conflicts ? "text-accent-strong" : "text-ink-3")}>
                            {a.conflicts}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-3 text-xs text-ink-3">
                    Denied means the policy check blocked a tool call, for example a refund above the limit.
                  </p>
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function Figure({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="border-r border-b border-rule-strong px-4 py-4 sm:px-5">
      <p className="text-xs text-ink-3">{label}</p>
      <div
        className={cx(
          "mt-2 font-mono text-2xl leading-none font-medium tabular",
          accent ? "text-accent-strong" : "text-ink",
        )}
      >
        {value ?? <Skeleton className="h-6 w-16" />}
      </div>
      {note && <p className="mt-1.5 text-xs text-ink-3">{note}</p>}
    </div>
  );
}

function Panel({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <div className="border-b border-rule-strong pb-2">
        <PanelHeading aside={aside}>{title}</PanelHeading>
      </div>
      <div className="pt-4">{children}</div>
    </section>
  );
}

function Legend() {
  return (
    <span className="flex items-center gap-3">
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2 rounded-[1px] bg-ink-2" aria-hidden />
        Resolved by AI
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2 rounded-[1px] bg-accent" aria-hidden />
        Escalated
      </span>
    </span>
  );
}

function BarList({
  rows,
  tone,
}: {
  rows: { key: string; label: string; value: number; extra?: string }[];
  tone: "ink" | "accent";
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_auto] items-center gap-3 text-sm">
          <span className="truncate text-ink-2" title={r.label}>
            {r.label}
          </span>
          <span className="h-2.5 bg-sunk" aria-hidden>
            <span
              className={cx("block h-full", tone === "accent" ? "bg-accent" : "bg-ink-2")}
              style={{ width: `${(r.value / max) * 100}%` }}
            />
          </span>
          <span className="w-20 text-right font-mono text-xs text-ink-2 tabular">
            {r.value}
            {r.extra && <span className="text-ink-3"> · {r.extra}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-10 text-sm text-ink-3">{children}</p>;
}
