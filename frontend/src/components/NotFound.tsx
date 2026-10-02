import { Link } from "@tanstack/react-router";

export function NotFound() {
  return (
    <div className="flex min-h-dvh items-center bg-paper px-6">
      <div className="mx-auto w-full max-w-md">
        <p className="font-mono text-sm text-ink-3">404</p>
        <h1 className="mt-2 text-2xl font-semibold">No page at this address.</h1>
        <p className="mt-2 text-sm text-ink-3">The link may be old or mistyped.</p>
        <div className="mt-6 flex gap-4 text-sm font-medium">
          <Link to="/chat" className="text-ink underline underline-offset-4">
            Customer chat
          </Link>
          <Link to="/admin/tickets" className="text-ink underline underline-offset-4">
            Agent dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
