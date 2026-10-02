import { expect, test } from "@playwright/test";
import { mockApi, signIn } from "./mocks";

test("ticket detail shows specialist lanes and the conflicts panel", async ({ page }) => {
  await signIn(page);
  await mockApi(page);

  await page.goto("/admin/tickets");
  await page.getByRole("link", { name: /TCK-0007/ }).first().click();
  await expect(page).toHaveURL(/\/admin\/tickets\/7$/);

  await page.getByRole("tab", { name: /AI reasoning/ }).click();
  const reasoning = page.getByRole("region", { name: "AI reasoning" });

  await expect(reasoning.getByLabel("Payments agent")).toBeVisible();
  await expect(reasoning.getByLabel("Logistics agent")).toBeVisible();

  const conflicts = reasoning.getByRole("region", { name: "Conflicts between agents" });
  await expect(conflicts).toBeVisible();
  await expect(conflicts.getByText("Facts disagreed")).toBeVisible();
});
