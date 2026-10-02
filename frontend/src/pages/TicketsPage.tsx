import { CaretLeftIcon, CaretRightIcon, MagnifyingGlassIcon, TrayIcon } from "@phosphor-icons/react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams, getRouteApi } from "@tanstack/react-router";
import {
  Button,
  ChannelMark,
  EmptyState,
  ErrorState,
  PriorityMark,
  Select,
  SkeletonRows,
  StatusMark,
} from "../components/ui";
import { adminApi } from "../lib/admin-api";
import { cx } from "../lib/cx";
import { humanize, relativeTime, statusLabel } from "../lib/format";

const route = getRouteApi("/admin/tickets");

export type SortBy = "created_at" | "updated_at" | "priority" | "status";
export type SortDir = "asc" | "desc";

export type TicketsSearch = {
  status?: string;
  channel?: string;
  intent?: string;
  priority?: string;
  q?: string;
  sortBy?: SortBy;
  sortDir?: SortDir;
  offset?: number;
};

const STATUSES = ["new", "ai_working", "escalated", "human_working", "closed"];
const CHANNELS: [string, string][] = [
  ["web", "Web chat"],
  ["whatsapp", "WhatsApp"],
  ["email", "Email"],
  ["voice", "Voice"],
];
const PRIORITIES = ["P1", "P2", "P3", "P4"];
const PAGE_SIZE = 25;

const SORT_OPTIONS: { value: string; label: string; sortBy: SortBy; sortDir: SortDir }[] = [
  { value: "created_desc", label: "Newest first", sortBy: "created_at", sortDir: "desc" },
  { value: "created_asc", label: "Oldest first", sortBy: "created_at", sortDir: "asc" },
  { value: "updated_desc", label: "Recently updated", sortBy: "updated_at", sortDir: "desc" },
  { value: "updated_asc", label: "Least recently updated", sortBy: "updated_at", sortDir: "asc" },
  { value: "priority_asc", label: "Priority, P1 first", sortBy: "priority", sortDir: "asc" },
];

const ROW_GRID = "grid grid-cols-[5.5rem_minmax(0,1fr)_2.25rem_5.5rem] sm:grid-cols-[5.5rem_7.5rem_minmax(0,1fr)_1.5rem_2.25rem_5.5rem] items-center gap-x-3";

export function TicketsPage() {
  const search = route.useSearch();
  const navigate = useNavigate({ from: "/admin/tickets" });
  const params = useParams({ strict: false }) as { ticketId?: string };
  const selectedId = params.ticketId ? Number(params.ticketId) : null;
  const offset = search.offset ?? 0;
  const sortBy = search.sortBy ?? "created_at";
  const sortDir = search.sortDir ?? "desc";
  const currentSortValue =
    SORT_OPTIONS.find((o) => o.sortBy === sortBy && o.sortDir === sortDir)?.value ?? "created_desc";
  const hasFilters = Boolean(search.status || search.channel || search.priority || search.q || search.intent);

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
    placeholderData: keepPreviousData,
  });

  function setFilter(key: keyof TicketsSearch, value: string) {
    if ((search[key] ?? "") === value) return;
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

  const total = query.data?.total ?? 0;

  return (
    <div className="flex h-full">
      <section
        aria-label="Ticket list"
        className={cx(
          "flex w-full min-w-0 flex-col border-r border-rule bg-surface lg:w-[34rem] lg:shrink-0 xl:w-[38rem]",
          selectedId !== null && "hidden lg:flex",
        )}
      >
        <div className="border-b border-rule px-4 pt-4 pb-3">
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="text-xl font-semibold">Tickets</h1>
            <span className="font-mono text-xs text-ink-3 tabular">
              {query.data ? `${total.toLocaleString()} ${total === 1 ? "ticket" : "tickets"}` : ""}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="relative w-full sm:w-52">
              <span className="sr-only">Search by reference</span>
              <MagnifyingGlassIcon
                size={14}
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-4"
              />
              <input
                type="search"
                defaultValue={search.q ?? ""}
                key={search.q ?? ""}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setFilter("q", (e.target as HTMLInputElement).value.trim());
                }}
                onBlur={(e) => setFilter("q", e.target.value.trim())}
                placeholder="Reference, e.g. T-1227"
                className="h-8 w-full rounded-md border border-rule-strong bg-surface pr-2 pl-8 text-xs placeholder:text-ink-4 hover:border-ink-4 focus:border-ink focus:outline-none"
              />
            </label>
            <Select aria-label="Status" value={search.status ?? ""} onChange={(e) => setFilter("status", e.target.value)}>
              <option value="">Any status</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </Select>
            <Select aria-label="Channel" value={search.channel ?? ""} onChange={(e) => setFilter("channel", e.target.value)}>
              <option value="">Any channel</option>
              {CHANNELS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Select aria-label="Priority" value={search.priority ?? ""} onChange={(e) => setFilter("priority", e.target.value)}>
              <option value="">Any priority</option>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
            <Select aria-label="Sort" value={currentSortValue} onChange={(e) => setSort(e.target.value)}>
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div
          aria-hidden
          className={cx(ROW_GRID, "border-b border-rule bg-paper px-4 py-1.5 text-[11px] font-medium text-ink-3")}
        >
          <span>Reference</span>
          <span className="hidden sm:block">Status</span>
          <span>Intent</span>
          <span className="hidden sm:block" />
          <span>Pri.</span>
          <span className="text-right">Updated</span>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {query.isPending ? (
            <SkeletonRows rows={10} />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => query.refetch()} />
          ) : query.data.items.length === 0 ? (
            <EmptyState icon={TrayIcon} title={hasFilters ? "No tickets match these filters" : "No tickets yet"}>
              {hasFilters ? (
                <Link to="/admin/tickets" search={{}} className="font-medium text-ink underline underline-offset-2">
                  Clear filters
                </Link>
              ) : (
                "New conversations from any channel will show up here."
              )}
            </EmptyState>
          ) : (
            <ul className={cx("divide-y divide-rule", query.isPlaceholderData && "opacity-60")}>
              {query.data.items.map((t) => {
                const selected = t.id === selectedId;
                return (
                  <li key={t.id}>
                    <Link
                      to="/admin/tickets/$ticketId"
                      params={{ ticketId: String(t.id) }}
                      search={search}
                      aria-current={selected ? "page" : undefined}
                      className={cx(
                        ROW_GRID,
                        "relative px-4 py-2.5 text-sm transition-colors duration-100 hover:bg-paper",
                        selected && "bg-paper",
                      )}
                    >
                      {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-accent" />}
                      <span className="font-mono text-[13px] font-medium text-ink">{t.reference}</span>
                      <span className="hidden sm:block">
                        <StatusMark status={t.status} />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-ink-2">{humanize(t.intent)}</span>
                        <span className="block truncate text-xs text-ink-3 sm:hidden">{statusLabel(t.status)}</span>
                        {t.assigned_agent && (
                          <span className="hidden truncate text-xs text-ink-3 sm:block">{t.assigned_agent}</span>
                        )}
                      </span>
                      <span className="hidden sm:block">
                        <ChannelMark channel={t.channel} compact />
                      </span>
                      <span>
                        <PriorityMark priority={t.priority} />
                      </span>
                      <time
                        dateTime={t.updated_at}
                        title={new Date(t.updated_at).toLocaleString()}
                        className="text-right font-mono text-xs whitespace-nowrap text-ink-3 tabular"
                      >
                        {relativeTime(t.updated_at)}
                      </time>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {query.data && total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-rule px-4 py-2 text-xs text-ink-3">
            <span className="font-mono tabular">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-1.5">
              <Button
                size="sm"
                icon={CaretLeftIcon}
                disabled={offset === 0}
                onClick={() => navigate({ search: { ...search, offset: Math.max(0, offset - PAGE_SIZE) } })}
              >
                Previous
              </Button>
              <Button
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => navigate({ search: { ...search, offset: offset + PAGE_SIZE } })}
              >
                Next
                <CaretRightIcon size={14} aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </section>

      <div className={cx("min-w-0 flex-1 overflow-y-auto", selectedId === null && "hidden lg:block")}>
        <Outlet />
      </div>
    </div>
  );
}
