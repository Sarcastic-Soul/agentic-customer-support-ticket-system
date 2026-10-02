import { createFileRoute, redirect } from "@tanstack/react-router";
import { isAuthed } from "../lib/auth";
import { LoginPage, type LoginSearch } from "../pages/LoginPage";

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    next: typeof search.next === "string" ? search.next : undefined,
  }),
  beforeLoad: ({ search }) => {
    if (isAuthed()) {
      throw redirect({ to: search.next ?? "/admin/tickets" });
    }
  },
  component: LoginPage,
});
