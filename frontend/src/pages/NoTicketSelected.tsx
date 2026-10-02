
export function NoTicketSelected() {
  return (
    <div className="flex h-full items-center px-10">
      <div className="max-w-sm">
        <p className="font-display text-lg font-medium text-ink">Pick a ticket to open it.</p>
        <p className="mt-2 text-sm text-ink-3">
          You'll see the conversation, how its status changed, and every step the AI took: which
          specialist agents ran, what tools they called, and where they disagreed.
        </p>
      </div>
    </div>
  );
}
