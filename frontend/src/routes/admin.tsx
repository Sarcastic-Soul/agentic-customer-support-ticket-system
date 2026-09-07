import { Link, Outlet, createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { clearSession, getAgent, isAuthed } from "../lib/auth";

export const Route = createFileRoute("/admin")({
  beforeLoad: ({ location }) => {
    if (!isAuthed()) {
      throw redirect({ to: "/login", search: { next: location.href } });
    }
  },
  component: AdminLayout,
});

const TABS = [
  { to: "/admin/tickets", label: "Tickets" },
  { to: "/admin/metrics", label: "Metrics" },
  { to: "/admin/kb", label: "Knowledge Base" },
];

function AdminLayout() {
  const navigate = useNavigate();
  const agent = getAgent();

  function handleLogout() {
    clearSession();
    navigate({ to: "/login" });
  }

  return (
    <div className="flex h-dvh flex-col bg-neutral-50 text-neutral-900">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold">Admin Dashboard</span>
          <nav className="flex gap-1">
            {TABS.map((tab) => (
              <Link
                key={tab.to}
                to={tab.to}
                className="rounded-md px-3 py-1.5 text-sm text-neutral-600 hover:bg-neutral-100 [&.active]:bg-neutral-900 [&.active]:text-white"
                activeProps={{ className: "active" }}
              >
                {tab.label}
              </Link>
            ))}
            <Link
              to="/console"
              className="rounded-md px-3 py-1.5 text-sm text-neutral-600 hover:bg-neutral-100"
            >
              Escalation Console
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm text-neutral-500">
          {agent && (
            <span>
              {agent.full_name} <span className="text-neutral-400">· {agent.role}</span>
            </span>
          )}
          <button onClick={handleLogout} className="text-neutral-400 hover:text-neutral-700">
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
