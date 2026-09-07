import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { adminApi, type AgentRunOut, type AgentStepOut } from "../lib/admin-api";

export const Route = createFileRoute("/admin/tickets/$ticketId")({
  component: TicketDetailPage,
});

function TicketDetailPage() {
  const { ticketId } = Route.useParams();
  const id = Number(ticketId);

  const ticketQuery = useQuery({
    queryKey: ["admin", "ticket", id],
    queryFn: () => adminApi.ticket(id),
  });
  const runsQuery = useQuery({
    queryKey: ["admin", "ticket", id, "runs"],
    queryFn: () => adminApi.ticketRuns(id),
  });

  if (ticketQuery.isLoading || !ticketQuery.data) {
    return <div className="p-6 text-sm text-neutral-400">Loading…</div>;
  }

  const ticket = ticketQuery.data;

  return (
    <div className="grid h-full grid-cols-2 divide-x divide-neutral-200">
      <section className="overflow-y-auto p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{ticket.reference}</h2>
          <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs">{ticket.status}</span>
        </div>
        <p className="mt-1 text-xs text-neutral-500">
          {ticket.channel} · {ticket.intent ?? "no intent"} · {ticket.priority}
          {ticket.sentiment ? ` · ${ticket.sentiment}` : ""}
        </p>
        {ticket.resolution && (
          <p className="mt-1 text-xs text-neutral-500">
            Resolution: {ticket.resolution}
            {ticket.resolution_summary ? ` — ${ticket.resolution_summary}` : ""}
          </p>
        )}

        <h3 className="mt-5 text-xs font-semibold uppercase text-neutral-500">Transcript</h3>
        <div className="mt-2 space-y-2">
          {ticket.messages.map((m) => (
            <div key={m.id} className={`flex ${m.direction === "outbound" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  m.role === "customer"
                    ? "bg-neutral-100"
                    : m.role === "human_agent"
                      ? "bg-emerald-100"
                      : "bg-sky-100"
                }`}
              >
                <div className="text-[10px] font-medium uppercase text-neutral-500">
                  {m.role}
                  {m.delivery_status && m.delivery_status !== "sent" ? ` · ${m.delivery_status}` : ""}
                </div>
                {m.body}
              </div>
            </div>
          ))}
        </div>

        <h3 className="mt-5 text-xs font-semibold uppercase text-neutral-500">Status timeline</h3>
        <ol className="mt-2 space-y-1 text-sm">
          {ticket.events.map((e, i) => (
            <li key={i} className="border-l-2 border-neutral-200 pl-3">
              <span className="text-xs text-neutral-500">{new Date(e.created_at).toLocaleString()}</span>{" "}
              <span className="font-medium">{e.event_type}</span>
              {e.from_status && e.to_status && (
                <span className="text-neutral-500">
                  {" "}
                  ({e.from_status} → {e.to_status})
                </span>
              )}
              <span className="text-neutral-400"> · {e.actor_type}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="overflow-y-auto p-6">
        <h3 className="text-xs font-semibold uppercase text-neutral-500">Agent reasoning trace</h3>
        {runsQuery.isLoading && <p className="mt-2 text-sm text-neutral-400">Loading…</p>}
        <div className="mt-2 space-y-3">
          {runsQuery.data?.map((run) => <RunCard key={run.id} run={run} />)}
          {runsQuery.data?.length === 0 && (
            <p className="text-sm text-neutral-400">No agent runs recorded for this ticket.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function RunCard({ run }: { run: AgentRunOut }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-lg border border-neutral-200 bg-white">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm"
      >
        <span className="font-medium">
          Run #{run.id} · {run.trigger}
          {run.outcome ? ` → ${run.outcome}` : ""}
        </span>
        <span className="text-xs text-neutral-400">
          {run.total_tokens_in + run.total_tokens_out} tok · ${Number(run.est_cost_usd).toFixed(4)}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-neutral-100 px-3 py-2">
          {run.steps.map((step) => (
            <StepRow key={step.ordinal} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

function StepRow({ step }: { step: AgentStepOut }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md bg-neutral-50 px-2 py-1.5">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-left text-xs"
      >
        <span className="font-medium text-neutral-700">
          {step.ordinal}. {step.node}
          {step.model ? ` (${step.model})` : ""}
        </span>
        <span className="text-neutral-400">
          {step.error ? "error" : ""}
          {step.latency_ms != null ? ` · ${step.latency_ms}ms` : ""}
          {step.tool_calls.length ? ` · ${step.tool_calls.length} tool call(s)` : ""}
        </span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 text-xs">
          {step.error && <p className="text-red-600">{step.error}</p>}
          {step.output && (
            <pre className="overflow-x-auto rounded bg-neutral-900 p-2 text-[11px] text-neutral-100">
              {JSON.stringify(step.output, null, 2)}
            </pre>
          )}
          {step.tool_calls.map((tc, i) => (
            <div key={i} className="rounded border border-neutral-200 bg-white p-1.5">
              <span className="font-medium">{tc.tool_name}</span>
              {!tc.authorized && <span className="ml-1 text-red-600">denied: {tc.deny_reason}</span>}
              <pre className="mt-1 overflow-x-auto text-[11px] text-neutral-600">
                {JSON.stringify(tc.arguments)}
              </pre>
              {tc.result && (
                <pre className="mt-1 overflow-x-auto text-[11px] text-neutral-500">
                  {JSON.stringify(tc.result)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
