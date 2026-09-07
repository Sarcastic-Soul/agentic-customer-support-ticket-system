import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { consoleApi } from "../lib/console-api";

type ConsoleSearch = { escalation?: number };

export const Route = createFileRoute("/console")({
  validateSearch: (search: Record<string, unknown>): ConsoleSearch => ({
    escalation: search.escalation ? Number(search.escalation) : undefined,
  }),
  component: ConsolePage,
});

const PRIORITY_COLOR: Record<string, string> = {
  P1: "bg-red-100 text-red-700",
  P2: "bg-amber-100 text-amber-700",
  P3: "bg-sky-100 text-sky-700",
  P4: "bg-neutral-100 text-neutral-600",
};

function ConsolePage() {
  const { escalation: selectedId } = Route.useSearch();
  const navigate = useNavigate({ from: "/console" });

  const queueQuery = useQuery({
    queryKey: ["console", "queue"],
    queryFn: () => consoleApi.queue(),
    refetchInterval: 5000,
  });

  return (
    <div className="flex h-dvh bg-neutral-50 text-neutral-900">
      <aside className="w-80 flex-shrink-0 overflow-y-auto border-r border-neutral-200 bg-white">
        <div className="border-b border-neutral-200 px-4 py-3">
          <h1 className="text-sm font-semibold">Escalation Queue</h1>
          <p className="text-xs text-neutral-500">{queueQuery.data?.length ?? 0} waiting</p>
        </div>
        <ul>
          {queueQuery.data?.map((esc) => (
            <li key={esc.id}>
              <button
                onClick={() => navigate({ search: { escalation: esc.id } })}
                className={`block w-full border-b border-neutral-100 px-4 py-3 text-left text-sm hover:bg-neutral-50 ${
                  selectedId === esc.id ? "bg-neutral-100" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{esc.ticket_reference}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      PRIORITY_COLOR[esc.priority] ?? "bg-neutral-100"
                    }`}
                  >
                    {esc.priority}
                  </span>
                </div>
                <div className="mt-1 text-xs text-neutral-500">{esc.reason_code}</div>
              </button>
            </li>
          ))}
          {queueQuery.data?.length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-neutral-400">Queue is empty</li>
          )}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {selectedId ? <WorkView escalationId={selectedId} /> : <EmptyState />}
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-neutral-400">
      Select an escalation from the queue.
    </div>
  );
}

function WorkView({ escalationId }: { escalationId: number }) {
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState("");
  const [note, setNote] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);

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

  async function handleClaim() {
    setBusy(true);
    try {
      await consoleApi.claim(escalationId);
      await refreshAll();
    } finally {
      setBusy(false);
    }
  }

  async function handleReply() {
    if (!replyText.trim()) return;
    setBusy(true);
    try {
      await consoleApi.reply(escalationId, replyText);
      setReplyText("");
      await refreshAll();
    } finally {
      setBusy(false);
    }
  }

  async function handleReturnToAI() {
    if (!note.trim()) return;
    setBusy(true);
    try {
      await consoleApi.returnToAI(escalationId, note);
      setNote("");
      await refreshAll();
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve() {
    if (!summary.trim()) return;
    setBusy(true);
    try {
      await consoleApi.resolve(escalationId, summary);
      setSummary("");
      await refreshAll();
    } finally {
      setBusy(false);
    }
  }

  if (detailQuery.isLoading || !detailQuery.data) {
    return <div className="p-6 text-sm text-neutral-400">Loading…</div>;
  }

  const esc = detailQuery.data;
  const packet = esc.handoff_packet;

  return (
    <div className="grid h-full grid-cols-2 divide-x divide-neutral-200">
      <section className="overflow-y-auto p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{esc.ticket_reference}</h2>
          <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs">{esc.status}</span>
        </div>
        <p className="mt-1 text-xs text-neutral-500">
          {esc.reason_code} · {esc.priority}
          {esc.required_skill ? ` · ${esc.required_skill}` : ""}
        </p>

        <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase text-neutral-500">Summary</h3>
          <p className="mt-1 text-sm">{packet.summary}</p>
        </div>

        <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase text-neutral-500">Customer</h3>
          <p className="mt-1 text-sm">
            {packet.customer.name ?? "Unknown"} · {packet.customer.tier}
            {packet.customer.verified ? "" : " · unverified"}
          </p>
        </div>

        {Object.keys(packet.entities).length > 0 && (
          <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-4">
            <h3 className="text-xs font-semibold uppercase text-neutral-500">Entities</h3>
            <dl className="mt-1 space-y-1 text-sm">
              {Object.entries(packet.entities).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <dt className="text-neutral-500">{k}:</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase text-neutral-500">Timeline</h3>
          <ol className="mt-2 space-y-2 text-sm">
            {packet.timeline.map((step, i) => (
              <li key={i} className="border-l-2 border-neutral-200 pl-3">
                <span className="text-xs font-medium text-neutral-500">{step.who}</span>
                <p className="text-neutral-800">{step.what}</p>
              </li>
            ))}
          </ol>
        </div>

        {esc.status === "queued" && (
          <button
            onClick={handleClaim}
            disabled={busy}
            className="mt-4 w-full rounded-lg bg-neutral-900 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Claim
          </button>
        )}
      </section>

      <section className="flex h-full flex-col overflow-y-auto p-6">
        <h3 className="text-xs font-semibold uppercase text-neutral-500">Transcript</h3>
        <div className="mt-2 flex-1 space-y-2">
          {transcriptQuery.data?.map((m) => (
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
                <div className="text-[10px] font-medium uppercase text-neutral-500">{m.role}</div>
                {m.body}
              </div>
            </div>
          ))}
        </div>

        {packet.suggested_reply && (
          <button
            onClick={() => setReplyText(packet.suggested_reply ?? "")}
            className="mt-3 self-start text-xs text-sky-700 underline"
          >
            Use AI's suggested reply
          </button>
        )}

        <div className="mt-2 space-y-2 border-t border-neutral-200 pt-3">
          <textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder="Reply to the customer…"
            rows={3}
            className="w-full rounded-lg border border-neutral-300 p-2 text-sm"
          />
          <button
            onClick={handleReply}
            disabled={busy || !replyText.trim()}
            className="w-full rounded-lg bg-neutral-900 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Send reply
          </button>

          <div className="pt-2">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note for the AI (e.g. 'refund approved, tell the customer 5-7 business days')…"
              rows={2}
              className="w-full rounded-lg border border-neutral-300 p-2 text-sm"
            />
            <button
              onClick={handleReturnToAI}
              disabled={busy || !note.trim()}
              className="mt-1 w-full rounded-lg border border-neutral-300 py-2 text-sm font-medium disabled:opacity-40"
            >
              Return to AI
            </button>
          </div>

          <div className="pt-2">
            <input
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Resolution summary…"
              className="w-full rounded-lg border border-neutral-300 p-2 text-sm"
            />
            <button
              onClick={handleResolve}
              disabled={busy || !summary.trim()}
              className="mt-1 w-full rounded-lg border border-emerald-300 bg-emerald-50 py-2 text-sm font-medium text-emerald-800 disabled:opacity-40"
            >
              Resolve
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
