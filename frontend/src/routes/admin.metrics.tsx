import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { adminApi } from "../lib/admin-api";

export const Route = createFileRoute("/admin/metrics")({
  component: MetricsPage,
});

const RANGE_OPTIONS = [1, 7, 30];
const COLORS = ["#0ea5e9", "#f59e0b", "#a855f7", "#10b981", "#ef4444", "#6366f1"];

function MetricsPage() {
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

  const o = overview.data;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Metrics</h2>
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setRangeDays(d)}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                rangeDays === d ? "bg-neutral-900 text-white" : "border border-neutral-300 text-neutral-600"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total tickets" value={o?.total_tickets ?? "—"} />
        <StatCard label="Open" value={o?.open_tickets ?? "—"} />
        <StatCard
          label="AI resolution rate"
          value={o?.ai_resolution_rate != null ? `${Math.round(o.ai_resolution_rate * 100)}%` : "—"}
        />
        <StatCard
          label="Escalation rate"
          value={o?.escalation_rate != null ? `${Math.round(o.escalation_rate * 100)}%` : "—"}
        />
        <StatCard
          label="Avg first response"
          value={o?.avg_first_response_seconds != null ? `${Math.round(o.avg_first_response_seconds)}s` : "—"}
        />
        <StatCard
          label="Avg resolution"
          value={o?.avg_resolution_seconds != null ? `${Math.round(o.avg_resolution_seconds / 60)}m` : "—"}
        />
        <StatCard label="Closed" value={o?.closed_tickets ?? "—"} />
        <StatCard label="Est. LLM cost" value={o ? `$${o.total_est_cost_usd.toFixed(4)}` : "—"} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="Tickets by channel">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={channels.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
              <XAxis dataKey="channel" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="ai_resolved" stackId="a" fill="#0ea5e9" name="AI resolved" />
              <Bar dataKey="escalated" stackId="a" fill="#f59e0b" name="Escalated" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top intents">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={intents.data ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
              <YAxis dataKey="intent" type="category" width={90} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#a855f7" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Escalation reasons">
          {escalations.data?.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={escalations.data}
                  dataKey="count"
                  nameKey="reason_code"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={(props) => String((props as unknown as { name: string }).name)}
                >
                  {escalations.data.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[220px] items-center justify-center text-sm text-neutral-400">
              No escalations in range.
            </div>
          )}
        </ChartCard>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase text-neutral-500">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}
