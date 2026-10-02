import { BooksIcon, ChartBarIcon, HeadsetIcon, ReceiptIcon, SignOutIcon, TicketIcon, type Icon } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { clearSession, getAgent } from "../lib/auth";
import { APPROVALS_KEY, consoleApi } from "../lib/console-api";
import { humanize } from "../lib/format";

type NavItem = {
  to: "/admin/tickets" | "/console" | "/console/approvals" | "/admin/metrics" | "/admin/kb";
  label: string;
  icon: Icon;
  /** Only highlight on this exact path, so Escalations is not lit on /console/approvals. */
  exact?: boolean;
  badge?: "escalations" | "approvals";
};

const NAV: NavItem[] = [
  { to: "/admin/tickets", label: "Tickets", icon: TicketIcon },
  { to: "/console", label: "Escalations", icon: HeadsetIcon, exact: true, badge: "escalations" },
  { to: "/console/approvals", label: "Approvals", icon: ReceiptIcon, badge: "approvals" },
  { to: "/admin/metrics", label: "Metrics", icon: ChartBarIcon },
  { to: "/admin/kb", label: "Knowledge base", icon: BooksIcon },
];

/** `compact` drops the name below sm so the app header nav fits a phone. */
export function Wordmark({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg viewBox="0 0 32 32" className="size-5 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="6" className="fill-ink" />
        <rect x="7" y="9" width="18" height="3" rx="1" className="fill-paper" />
        <rect x="7" y="15" width="12" height="3" rx="1" className="fill-paper" />
        <rect x="7" y="21" width="7" height="3" rx="1" className="fill-accent" />
      </svg>
      <span className={`font-display text-[15px] font-semibold tracking-tight text-ink ${compact ? "hidden sm:inline" : ""}`}>
        Support desk
      </span>
    </span>
  );
}

/** Waiting-escalation count for the nav. Same endpoint and cadence the
 * console already polls, so this adds no new backend load pattern. */
function useWaitingCount() {
  const query = useQuery({
    queryKey: ["console", "queue", "queue"],
    queryFn: () => consoleApi.queue(),
    refetchInterval: 10000,
  });
  return query.data?.filter((e) => e.status === "queued").length ?? 0;
}

/** Refunds waiting for a human decision. Shares its cache entry with the
 * approvals page, so an optimistic removal there updates this badge too. */
function useApprovalsCount() {
  const query = useQuery({
    queryKey: APPROVALS_KEY,
    queryFn: consoleApi.approvals,
    refetchInterval: 10000,
  });
  return query.data?.length ?? 0;
}

export function AppShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const agent = getAgent();
  const counts = { escalations: useWaitingCount(), approvals: useApprovalsCount() };

  function handleLogout() {
    clearSession();
    navigate({ to: "/login" });
  }

  return (
    <div className="flex h-dvh flex-col bg-paper text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-sm focus:text-paper"
      >
        Skip to content
      </a>
      <header className="flex h-12 shrink-0 items-center gap-4 border-b border-rule bg-surface px-3 sm:px-5">
        <Link to="/admin/tickets" className="rounded-sm" aria-label="Support desk, go to tickets">
          <Wordmark compact />
        </Link>

        <nav aria-label="Main" className="flex h-full min-w-0 flex-1 items-stretch overflow-x-auto sm:ml-4">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              activeOptions={{ exact: item.exact ?? false }}
              aria-label={item.label}
              className="group relative inline-flex items-center gap-2 px-2.5 text-sm text-ink-3 transition-colors duration-150 hover:text-ink sm:px-3 data-[status=active]:text-ink"
            >
              <item.icon size={17} aria-hidden className="shrink-0" />
              <span className="hidden md:inline">{item.label}</span>
              {item.badge && counts[item.badge] > 0 && (
                <span className="rounded-[3px] bg-accent px-1 font-mono text-[11px] leading-4 font-medium text-on-accent tabular">
                  {counts[item.badge]}
                  <span className="sr-only"> waiting</span>
                </span>
              )}
              <span
                aria-hidden
                className="absolute inset-x-2.5 bottom-0 h-0.5 scale-x-0 bg-accent transition-transform duration-200 ease-out group-data-[status=active]:scale-x-100 sm:inset-x-3"
              />
            </Link>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-3">
          {agent && (
            <span className="hidden text-right leading-tight lg:block">
              <span className="block text-sm text-ink">{agent.full_name}</span>
              <span className="block text-xs text-ink-3">{humanize(agent.role)}</span>
            </span>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex size-8 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-sunk hover:text-ink"
            aria-label="Sign out"
            title="Sign out"
          >
            <SignOutIcon size={18} aria-hidden />
          </button>
        </div>
      </header>
      <main id="main" className="relative min-h-0 flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
