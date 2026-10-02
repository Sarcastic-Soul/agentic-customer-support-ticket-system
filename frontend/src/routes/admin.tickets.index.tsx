import { createFileRoute } from "@tanstack/react-router";
import { NoTicketSelected } from "../pages/NoTicketSelected";

export const Route = createFileRoute("/admin/tickets/")({
  component: NoTicketSelected,
});
