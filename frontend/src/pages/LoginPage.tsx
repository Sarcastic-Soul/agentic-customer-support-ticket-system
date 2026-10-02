import { WarningCircleIcon } from "@phosphor-icons/react";
import { useNavigate, getRouteApi } from "@tanstack/react-router";
import { useState } from "react";
import { Wordmark } from "../components/AppShell";
import { Button, Field, TextInput } from "../components/ui";
import { authApi } from "../lib/auth-api";
import { setSession, setToken } from "../lib/auth";

const route = getRouteApi("/login");

export type LoginSearch = { next?: string };

const AREAS = [
  { name: "Tickets", body: "Every conversation from web chat, WhatsApp, email and voice, with the AI's reasoning for each reply." },
  { name: "Escalations", body: "Tickets the AI handed to a person, with a summary, the customer's details and a suggested reply." },
  { name: "Metrics", body: "How many tickets the AI closed on its own, why others were escalated, and what it cost." },
  { name: "Knowledge base", body: "The policy and product documents the AI answers from." },
];

export function LoginPage() {
  const { next } = route.useSearch();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { access_token } = await authApi.login(email, password);
      setToken(access_token);
      const agent = await authApi.me();
      setSession(access_token, agent);
      await navigate({ to: next ?? "/admin/tickets" });
    } catch (err) {
      setError(
        err instanceof Error && err.message === "Failed to fetch"
          ? "Could not reach the server. Check that the API is running."
          : "That email and password don't match an agent account.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh bg-paper lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-10 lg:px-16">
        <Wordmark />
        <div className="flex flex-1 flex-col justify-center py-12">
          <form onSubmit={handleSubmit} className="w-full max-w-sm">
            <h1 className="text-[28px] leading-tight font-semibold text-ink">Sign in</h1>
            <p className="mt-2 text-sm text-ink-3">Use your agent or admin account.</p>

            <div className="mt-8 space-y-4">
              <Field label="Email" htmlFor="login-email">
                <TextInput
                  id="login-email"
                  type="email"
                  autoComplete="username"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field label="Password" htmlFor="login-password">
                <TextInput
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>
            </div>

            {error && (
              <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-accent-strong">
                <WarningCircleIcon size={18} aria-hidden className="mt-px shrink-0" />
                {error}
              </p>
            )}

            <Button type="submit" variant="primary" disabled={busy} className="mt-6 w-full">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>

      <aside className="hidden border-l border-rule bg-sunk px-16 py-6 lg:flex lg:flex-col lg:justify-center">
        <p className="max-w-md font-display text-2xl leading-snug font-medium text-ink">
          The AI answers what it can from real order and payment data. Everything else lands here, with context.
        </p>
        <dl className="mt-10 max-w-md divide-y divide-rule-strong border-y border-rule-strong">
          {AREAS.map((area) => (
            <div key={area.name} className="grid grid-cols-[8.5rem_1fr] gap-4 py-3.5">
              <dt className="text-sm font-medium text-ink">{area.name}</dt>
              <dd className="text-sm text-ink-3">{area.body}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  );
}
