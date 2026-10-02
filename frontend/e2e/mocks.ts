import type { Page, Route } from "@playwright/test";

/** Shared fixtures and helpers. Shapes follow src/lib/*-api.ts. */

export const AGENT = { id: 1, email: "asha@example.com", full_name: "Asha Rao", role: "agent" };

const NOW = new Date().toISOString();

export const TICKET = {
  id: 7,
  reference: "TCK-0007",
  channel: "web",
  intent: "refund_request",
  status: "ai_handling",
  priority: "P3",
  sentiment: "neutral",
  created_at: NOW,
  updated_at: NOW,
  resolved_at: null,
  assigned_agent: null,
};

export const TICKET_DETAIL = {
  ...TICKET,
  ai_turns: 1,
  resolution: null,
  resolution_summary: null,
  first_response_at: NOW,
  messages: [
    { id: 1, role: "customer", body: "Where is ORD-1001, and refund the double charge.", direction: "inbound", delivery_status: null, created_at: NOW },
    { id: 2, role: "assistant", body: "Your parcel is on its way.", direction: "outbound", delivery_status: "sent", created_at: NOW },
  ],
  events: [{ event_type: "status_change", actor_type: "ai", from_status: "new", to_status: "ai_handling", created_at: NOW }],
};

function step(ordinal: number, node: string, agent: string | null = null, tools: string[] = []) {
  return {
    ordinal,
    node,
    agent,
    model: "stub",
    output: {},
    tokens_in: 100,
    tokens_out: 20,
    latency_ms: 300,
    error: null,
    tool_calls: tools.map((tool_name) => ({
      tool_name,
      arguments: { order_number: "ORD-1001" },
      result: { ok: true },
      authorized: true,
      deny_reason: null,
      latency_ms: 40,
    })),
  };
}

export const RUNS = [
  {
    id: 11,
    trigger: "inbound_message",
    outcome: "answered",
    intent: "refund_request",
    confidence: 0.91,
    total_tokens_in: 900,
    total_tokens_out: 200,
    est_cost_usd: "0.0004",
    latency_ms: 2400,
    started_at: NOW,
    finished_at: NOW,
    specialists: ["payments", "logistics"],
    conflicts: [
      {
        kind: "fact",
        agents: ["orders", "logistics"],
        subject: "ORD-1001",
        detail: "Order record says delivered, carrier says in transit.",
        resolution: "rule",
        rule: "carrier_is_truth_for_parcel",
        kept: "in_transit",
        dropped: [],
      },
    ],
    steps: [
      step(1, "classify"),
      step(2, "supervisor"),
      step(3, "specialist", "payments", ["get_transactions"]),
      step(4, "specialist", "logistics", ["track_shipment"]),
      step(5, "reconcile"),
      step(6, "answer"),
      step(7, "verify"),
    ],
  },
];

export const APPROVALS = [
  {
    refund_id: 31,
    ticket_id: 7,
    ticket_reference: "TCK-0007",
    customer_name: "Meera Iyer",
    order_number: "ORD-1001",
    txn_ref: "TXN-5501",
    payment_amount: "2400.00",
    amount: "2400.00",
    reason: "Charged twice",
    requested_by_type: "ai",
    created_at: NOW,
  },
  {
    refund_id: 32,
    ticket_id: 8,
    ticket_reference: "TCK-0008",
    customer_name: "Kabir Shah",
    order_number: "ORD-1002",
    txn_ref: "TXN-5502",
    payment_amount: "1800.00",
    amount: "900.00",
    reason: "Item arrived damaged",
    requested_by_type: "ai",
    created_at: NOW,
  },
];

export const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/** Puts a console session in localStorage before any page script runs. */
export async function signIn(page: Page) {
  await page.addInitScript((agent) => {
    localStorage.setItem("support-console-token", "test-token");
    localStorage.setItem("support-console-agent", JSON.stringify(agent));
  }, AGENT);
}

type Overrides = Record<string, (route: Route) => unknown>;

/** Mocks every /api/** call the console and admin pages make. `overrides`
 * maps a path (no query string) to a handler and wins over the defaults. */
export async function mockApi(page: Page, overrides: Overrides = {}) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (overrides[path]) return overrides[path](route);

    switch (path) {
      case "/api/auth/me":
        return json(route, AGENT);
      case "/api/admin/tickets":
        return json(route, { items: [TICKET], total: 1 });
      case `/api/admin/tickets/${TICKET.id}`:
        return json(route, TICKET_DETAIL);
      case `/api/admin/tickets/${TICKET.id}/runs`:
        return json(route, RUNS);
      case "/api/console/queue":
        return json(route, []);
      case "/api/console/approvals":
        return json(route, APPROVALS);
      case "/api/admin/metrics/overview":
        return json(route, {
          total_tickets: 120,
          open_tickets: 14,
          closed_tickets: 106,
          ai_resolution_rate: 0.72,
          escalation_rate: 0.18,
          avg_first_response_seconds: 9,
          avg_resolution_seconds: 840,
          total_est_cost_usd: 0.42,
        });
      case "/api/admin/metrics/channels":
        return json(route, [
          { channel: "web", count: 70, ai_resolved: 55, escalated: 10 },
          { channel: "email", count: 50, ai_resolved: 30, escalated: 12 },
        ]);
      case "/api/admin/metrics/intents":
        return json(route, [{ intent: "order_status", count: 40, escalation_rate: 0.05 }]);
      case "/api/admin/metrics/escalations":
        return json(route, [{ reason_code: "customer_requested_human", count: 9 }]);
      case "/api/admin/metrics/agents":
        return json(route, [
          { agent: "orders", runs: 30, tool_calls: 60, denied: 2, conflicts: 3 },
          { agent: "payments", runs: 25, tool_calls: 40, denied: 5, conflicts: 3 },
        ]);
      case "/api/customer/messages":
      case "/api/customer/tickets":
        return json(route, []);
      default:
        return json(route, { detail: `no mock for ${path}` }, 404);
    }
  });
}
