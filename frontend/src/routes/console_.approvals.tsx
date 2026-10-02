import { createFileRoute, redirect } from "@tanstack/react-router";
import { isAuthed } from "../lib/auth";
import { ApprovalsPage } from "../pages/ApprovalsPage";

// `console_` keeps the URL under /console without nesting inside the
// escalations page, which has no <Outlet />.
export const Route = createFileRoute("/console_/approvals")({
  beforeLoad: ({ location }) => {
    if (!isAuthed()) {
      throw redirect({ to: "/login", search: { next: location.href } });
    }
  },
  component: ApprovalsPage,
});
