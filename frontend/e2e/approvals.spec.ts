import { expect, test, type Page } from "@playwright/test";
import { APPROVALS, json, mockApi, signIn } from "./mocks";

/** Stateful approvals mock: a successful decision removes the refund from
 * the next GET, the way the backend would. */
async function mockApprovals(page: Page, rejectStatus = 200) {
  let pending = [...APPROVALS];
  await signIn(page);
  await mockApi(page, {
    "/api/console/approvals": (route) => json(route, pending),
  });
  await page.route(/\/api\/console\/approvals\/\d+\/(approve|reject)$/, (route) => {
    const [, id, action] = new URL(route.request().url()).pathname.match(/approvals\/(\d+)\/(\w+)/)!;
    if (action === "reject" && rejectStatus !== 200) {
      return json(route, { detail: "Refund was already settled" }, rejectStatus);
    }
    pending = pending.filter((a) => a.refund_id !== Number(id));
    return json(route, action === "approve" ? { approved: true } : { rejected: true });
  });
}

const row = (page: Page, ref: string) => page.getByRole("listitem", { name: `Refund for ${ref}` });

test("nav badge counts the waiting refunds", async ({ page }) => {
  await mockApprovals(page);
  await page.goto("/console/approvals");
  await expect(page.getByRole("link", { name: "Approvals" })).toContainText("2");
});

test("approve removes the row", async ({ page }) => {
  await mockApprovals(page);
  await page.goto("/console/approvals");

  await row(page, "TCK-0007").getByRole("button", { name: "Approve" }).click();

  await expect(row(page, "TCK-0007")).toHaveCount(0);
  await expect(row(page, "TCK-0008")).toBeVisible();
  await expect(page.getByRole("link", { name: "Approvals" })).toContainText("1");
});

test("reject needs a note", async ({ page }) => {
  await mockApprovals(page);
  await page.goto("/console/approvals");

  const r = row(page, "TCK-0008");
  await r.getByRole("button", { name: "Reject", exact: true }).click();
  const submit = r.getByRole("button", { name: "Reject refund" });
  await expect(submit).toBeDisabled();

  await r.getByRole("textbox").fill("The order was delivered on 12 Sep.");
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect(row(page, "TCK-0008")).toHaveCount(0);
});

test("a failed reject puts the row back and shows the error", async ({ page }) => {
  await mockApprovals(page, 409);
  await page.goto("/console/approvals");

  const r = row(page, "TCK-0008");
  await r.getByRole("button", { name: "Reject", exact: true }).click();
  await r.getByRole("textbox").fill("Not eligible.");
  await r.getByRole("button", { name: "Reject refund" }).click();

  await expect(row(page, "TCK-0008")).toBeVisible();
  await expect(page.getByRole("alert").first()).toContainText("Refund was already settled");
  await expect(row(page, "TCK-0008").getByRole("textbox")).toHaveValue("Not eligible.");
});
