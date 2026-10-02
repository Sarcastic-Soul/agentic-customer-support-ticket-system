import { createFileRoute } from "@tanstack/react-router";
import { TicketsPage, type SortBy, type SortDir, type TicketsSearch } from "../pages/TicketsPage";

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
