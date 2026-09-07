import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, createFileRoute, useNavigate } from "@tanstack/react-router";
import { adminApi } from "../lib/admin-api";

type TicketsSearch = {
  status?: string;
  channel?: string;
  intent?: string;
  priority?: string;
  offset?: number;
};

export const Route = createFileRoute("/admin/tickets")({
  validateSearch: (search: Record<string, unknown>): TicketsSearch => ({
    status: typeof search.status === "string" ? search.status : undefined,
    channel: typeof search.channel === "string" ? search.channel : undefined,
    intent: typeof search.intent === "string" ? search.intent : undefined,
    priority: typeof search.priority === "string" ? search.priority : undefined,
    offset: typeof search.offset === "number" ? search.offset : undefined,
  }),
  component: TicketsPage,
});

const STATUSES = ["new", "ai_working", "escalated", "human_working", "closed"];
const CHANNELS = ["web", "whatsapp", "email", "voice"];
const PRIORITIES = ["P1", "P2", "P3", "P4"];
const PAGE_SIZE = 25;

const STATUS_COLOR: Record<string, string> = {
  new: "bg-sky-100 text-sky-700",
  ai_working: "bg-violet-100 text-violet-700",
  escalated: "bg-amber-100 text-amber-700",
  human_working: "bg-amber-100 text-amber-700",
  closed: "bg-neutral-100 text-neutral-600",
};

function TicketsPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/admin/tickets" });
  const offset = search.offset ?? 0;

  const query = useQuery({
    queryKey: ["admin", "tickets", search],
    queryFn: () =>
      adminApi.tickets({
        status: search.status,
        channel: search.channel,
        intent: search.intent,
        priority: search.priority,
        limit: PAGE_SIZE,
        offset,
      }),
    refetchInterval: 10000,
  });

  function setFilter(key: keyof TicketsSearch, value: string) {
    navigate({
      search: { ...search, [key]: value || undefined, offset: undefined },
    });
  }

  return (
    <div className="flex h-full">
      <div className="flex w-full max-w-3xl flex-shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="flex flex-wrap gap-2 border-b border-neutral-200 px-4 py-3">
          <select
            value={search.status ?? ""}
            onChange={(e) => setFilter("status", e.target.value)}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={search.channel ?? ""}
            onChange={(e) => setFilter("channel", e.target.value)}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs"
          >
            <option value="">All channels</option>
            {CHANNELS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            value={search.priority ?? ""}
            onChange={(e) => setFilter("priority", e.target.value)}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs"
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">Reference</th>
                <th className="px-2 py-2 font-medium">Channel</th>
                <th className="px-2 py-2 font-medium">Intent</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 font-medium">Priority</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((t) => (
                <tr key={t.id} className="border-t border-neutral-100 hover:bg-neutral-50">
                  <td className="px-4 py-2">
                    <Link
                      to="/admin/tickets/$ticketId"
                      params={{ ticketId: String(t.id) }}
                      className="font-medium text-sky-700 hover:underline"
                    >
                      {t.reference}
                    </Link>
                  </td>
                  <td className="px-2 py-2 text-neutral-600">{t.channel}</td>
                  <td className="px-2 py-2 text-neutral-600">{t.intent ?? "—"}</td>
                  <td className="px-2 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${STATUS_COLOR[t.status] ?? "bg-neutral-100"}`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-neutral-600">{t.priority}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.items.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-neutral-400">No tickets match these filters.</p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-neutral-200 px-4 py-2 text-xs text-neutral-500">
          <span>
            {query.data ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, query.data.total)} of ${query.data.total}` : ""}
          </span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => navigate({ search: { ...search, offset: Math.max(0, offset - PAGE_SIZE) } })}
              className="rounded-md border border-neutral-300 px-2 py-1 disabled:opacity-30"
            >
              Prev
            </button>
            <button
              disabled={!query.data || offset + PAGE_SIZE >= query.data.total}
              onClick={() => navigate({ search: { ...search, offset: offset + PAGE_SIZE } })}
              className="rounded-md border border-neutral-300 px-2 py-1 disabled:opacity-30"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
