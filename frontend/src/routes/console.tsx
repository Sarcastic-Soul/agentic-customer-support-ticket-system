import { createFileRoute, redirect } from "@tanstack/react-router";
import { isAuthed } from "../lib/auth";
import { ConsolePage, type ConsoleSearch } from "../pages/ConsolePage";

export const Route = createFileRoute("/console")({
  validateSearch: (search: Record<string, unknown>): ConsoleSearch => ({
    escalation: search.escalation ? Number(search.escalation) : undefined,
  }),
  beforeLoad: ({ location }) => {
    if (!isAuthed()) {
      throw redirect({ to: "/login", search: { next: location.href } });
    }
  },
  component: ConsolePage,
});
