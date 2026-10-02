import { createFileRoute } from "@tanstack/react-router";
import { TicketDetailPage } from "../pages/TicketDetailPage";

export const Route = createFileRoute("/admin/tickets/$ticketId")({
  component: TicketDetailPage,
});
