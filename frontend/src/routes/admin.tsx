import { Outlet, createFileRoute, redirect } from "@tanstack/react-router";
import { AppShell } from "../components/AppShell";
import { isAuthed } from "../lib/auth";

export const Route = createFileRoute("/admin")({
  beforeLoad: ({ location }) => {
    if (!isAuthed()) {
      throw redirect({ to: "/login", search: { next: location.href } });
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});
