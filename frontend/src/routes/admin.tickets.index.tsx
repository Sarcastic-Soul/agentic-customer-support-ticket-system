import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/tickets/")({
  component: () => (
    <div className="flex h-full items-center justify-center text-sm text-neutral-400">
      Select a ticket to see its detail and reasoning trace.
    </div>
  ),
});
