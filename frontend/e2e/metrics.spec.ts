import { expect, test } from "@playwright/test";
import { json, mockApi, signIn } from "./mocks";

test("metrics page renders, with the per-agent table", async ({ page }) => {
  await signIn(page);
  await mockApi(page);
  await page.goto("/admin/metrics");

  await expect(page.getByText("Tickets by channel")).toBeVisible();
  await expect(page.getByText("Why tickets were escalated")).toBeVisible();
  await expect(page.getByText("Specialist agents")).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Payments" })).toBeVisible();
});

test("per-agent table is hidden when the endpoint is missing", async ({ page }) => {
  await signIn(page);
  await mockApi(page, {
    "/api/admin/metrics/agents": (route) => json(route, { detail: "Not Found" }, 404),
  });
  await page.goto("/admin/metrics");

  await expect(page.getByText("Tickets by channel")).toBeVisible();
  await expect(page.getByText("Top intents")).toBeVisible();
  await expect(page.getByText("Specialist agents")).toHaveCount(0);
});
