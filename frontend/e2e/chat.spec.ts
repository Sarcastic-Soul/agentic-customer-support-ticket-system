import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test("chat shows agent progress, then the reply", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("support-chat-customer", JSON.stringify({ email: "meera@example.com", customerId: 3 }));
  });
  await mockApi(page);

  // Frames are sent one at a time, each after the test has checked the
  // last one, so every intermediate state is seen.
  let ws: import("@playwright/test").WebSocketRoute | undefined;
  await page.routeWebSocket(/\/channels\/web\/ws/, (route) => {
    ws = route;
  });

  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();

  await page.getByPlaceholder("Type a message").fill("Where is my order?");
  await page.getByRole("button", { name: "Send" }).click();

  const progress = page.getByTestId("agent-progress");
  await expect(progress).toBeVisible();

  ws!.send(JSON.stringify({ type: "progress", stage: "classify", agent: null, label: "Reading your message" }));
  await expect(progress).toContainText("Reading your message");

  ws!.send(JSON.stringify({ type: "progress", stage: "specialist", agent: "logistics", label: "Checking your order" }));
  await expect(progress).toContainText("Checking your order");
  await expect(progress).not.toContainText("logistics");

  ws!.send(JSON.stringify({ type: "reply", text: "Your parcel ORD-1001 arrives tomorrow." }));
  await expect(page.getByText("Your parcel ORD-1001 arrives tomorrow.")).toBeVisible();
  await expect(progress).toHaveCount(0);
});

test("legacy frames with no type still count as replies", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("support-chat-customer", JSON.stringify({ email: "meera@example.com", customerId: 3 }));
  });
  await mockApi(page);
  await page.routeWebSocket(/\/channels\/web\/ws/, (ws) => {
    ws.onMessage(() => ws.send(JSON.stringify({ text: "Old-style reply." })));
  });

  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByPlaceholder("Type a message").fill("hi");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Old-style reply.")).toBeVisible();
  await expect(page.getByTestId("agent-progress")).toHaveCount(0);
});
