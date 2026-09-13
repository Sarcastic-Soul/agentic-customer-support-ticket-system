const STORAGE_KEY = "support-chat-customer";

export type CustomerSession = { email: string; customerId: number };

/** Logged-in customer for the chat widget - separate from the agent
 * console's JWT session (lib/auth.ts). No password: this just remembers
 * which email the browser last signed in as. */
export function getStoredCustomer(): CustomerSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CustomerSession) : null;
  } catch {
    return null;
  }
}

export function storeCustomer(session: CustomerSession) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // localStorage unavailable (private mode, etc.) - session just won't
    // survive a refresh.
  }
}

export function clearCustomer() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export async function loginByEmail(email: string): Promise<CustomerSession> {
  const res = await fetch("/api/customer/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(`login failed (${res.status})`);
  const data = (await res.json()) as { customer_id: number; email: string };
  return { email: data.email, customerId: data.customer_id };
}

export type CustomerTicket = {
  id: number;
  reference: string;
  channel: string;
  intent: string | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
};

export async function fetchMyTickets(customerId: number): Promise<CustomerTicket[]> {
  const res = await fetch(`/api/customer/tickets?customer_id=${customerId}`);
  if (!res.ok) throw new Error(`could not load tickets (${res.status})`);
  return res.json() as Promise<CustomerTicket[]>;
}

export type CustomerMessage = {
  id: number;
  role: "customer" | "assistant" | "human_agent";
  text: string;
  created_at: string;
};

/** History of the customer's current (not-closed) web conversation - lets
 * the chat widget restore it after a refresh instead of starting blank. */
export async function fetchCurrentMessages(customerId: number): Promise<CustomerMessage[]> {
  const res = await fetch(`/api/customer/messages?customer_id=${customerId}`);
  if (!res.ok) throw new Error(`could not load messages (${res.status})`);
  return res.json() as Promise<CustomerMessage[]>;
}
