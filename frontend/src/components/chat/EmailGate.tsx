import { WarningCircleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { loginByEmail, storeCustomer, type CustomerSession } from "../../lib/customer";
import { Button, Field, TextInput } from "../ui";

const CAN_DO = [
  "Track an order or a delivery",
  "Cancel an order or start a return",
  "Check a refund or a failed payment",
  "Get an invoice",
];

export function EmailGate({ onLogin }: { onLogin: (customer: CustomerSession) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed || busy) return;

    setBusy(true);
    setError(null);
    try {
      const session = await loginByEmail(trimmed);
      storeCustomer(session);
      onLogin(session);
    } catch {
      setError("Could not sign in with that email. Check it and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-paper px-5 py-8 sm:items-center sm:justify-center">
      <div className="w-full max-w-md">
        <h1 className="text-[28px] leading-tight font-semibold text-ink">Get help with an order</h1>
        <p className="mt-3 text-[15px] text-ink-2">
          Enter the email you shop with. We'll pick up any conversation you already started. First time here? That's
          fine, we'll set you up.
        </p>

        <form onSubmit={handleSubmit} className="mt-8">
          <Field label="Email" htmlFor="customer-email">
            <TextInput
              id="customer-email"
              type="email"
              required
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="h-11 text-[15px]"
            />
          </Field>
          {error && (
            <p role="alert" className="mt-3 flex items-start gap-2 text-sm text-accent-strong">
              <WarningCircleIcon size={18} aria-hidden className="mt-px shrink-0" />
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={busy} className="mt-4 h-11 w-full text-[15px]">
            {busy ? "Signing in…" : "Continue"}
          </Button>
        </form>

        <div className="mt-10 border-t border-rule-strong pt-5">
          <p className="text-sm font-medium text-ink">You can ask to</p>
          <ul className="mt-2 space-y-1.5 text-sm text-ink-3">
            {CAN_DO.map((item) => (
              <li key={item} className="flex gap-2.5">
                <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-[1px] bg-ink-4" />
                {item}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-3">If the assistant can't sort it out, a person from our team takes over.</p>
        </div>
      </div>
    </div>
  );
}
