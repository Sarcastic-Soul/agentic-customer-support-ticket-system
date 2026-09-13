import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, createFileRoute, useNavigate } from "@tanstack/react-router";
import { adminApi } from "../lib/admin-api";

type SortBy = "created_at" | "updated_at" | "priority" | "status";
type SortDir = "asc" | "desc";

type TicketsSearch = {
  status?: string;
  channel?: string;
  intent?: string;
  priority?: string;
  q?: string;
  sortBy?: SortBy;
  sortDir?: SortDir;
  offset?: number;
};

export const Route = createFileRoute("/admin/tickets")({
  validateSearch: (search: Record<string, unknown>): TicketsSearch => ({
    status: typeof search.status === "string" ? search.status : undefined,
    channel: typeof search.channel === "string" ? search.channel : undefined,
    intent: typeof search.intent === "string" ? search.intent : undefined,
    priority: typeof search.priority === "string" ? search.priority : undefined,
    q: typeof search.q === "string" ? search.q : undefined,
    sortBy: typeof search.sortBy === "string" ? (search.sortBy as SortBy) : undefined,
    sortDir: typeof search.sortDir === "string" ? (search.sortDir as SortDir) : undefined,
    offset: typeof search.offset === "number" ? search.offset : undefined,
  }),
  component: TicketsPage,
});

const STATUSES = ["new", "ai_working", "escalated", "human_working", "closed"];
const CHANNELS = ["web", "whatsapp", "email", "voice"];
const PRIORITIES = ["P1", "P2", "P3", "P4"];
const PAGE_SIZE = 25;

const SORT_OPTIONS: { value: string; label: string; sortBy: SortBy; sortDir: SortDir }[] = [
  { value: "created_desc", label: "Newest first (created)", sortBy: "created_at", sortDir: "desc" },
  { value: "created_asc", label: "Oldest first (created)", sortBy: "created_at", sortDir: "asc" },
  { value: "updated_desc", label: "Recently updated", sortBy: "updated_at", sortDir: "desc" },
  { value: "updated_asc", label: "Least recently updated", sortBy: "updated_at", sortDir: "asc" },
  { value: "priority_asc", label: "Priority (P1 first)", sortBy: "priority", sortDir: "asc" },
];

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
  const sortBy = search.sortBy ?? "created_at";
  const sortDir = search.sortDir ?? "desc";
  const currentSortValue =
    SORT_OPTIONS.find((o) => o.sortBy === sortBy && o.sortDir === sortDir)?.value ?? "created_desc";

  const query = useQuery({
    queryKey: ["admin", "tickets", search],
    queryFn: () =>
      adminApi.tickets({
        status: search.status,
        channel: search.channel,
        intent: search.intent,
        priority: search.priority,
        q: search.q,
        sort_by: sortBy,
        sort_dir: sortDir,
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

  function setSort(value: string) {
    const option = SORT_OPTIONS.find((o) => o.value === value);
    navigate({
      search: {
        ...search,
        sortBy: option?.sortBy,
        sortDir: option?.sortDir,
        offset: undefined,
      },
    });
  }

  return (
    <div className="flex h-full">
      <div className="flex w-full max-w-3xl flex-shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="flex flex-wrap gap-2 border-b border-neutral-200 px-4 py-3">
          <input
            type="text"
            defaultValue={search.q ?? ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") setFilter("q", (e.target as HTMLInputElement).value);
            }}
            onBlur={(e) => setFilter("q", e.target.value)}
            placeholder="Search reference (T-1227)…"
            className="w-44 rounded-md border border-neutral-300 px-2 py-1 text-xs"
          />
          <select
            value={currentSortValue}
            onChange={(e) => setSort(e.target.value)}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
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
                <th className="px-2 py-2 font-medium">Assigned</th>
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
                  <td className="px-2 py-2 text-neutral-600">{t.assigned_agent ?? "—"}</td>
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
