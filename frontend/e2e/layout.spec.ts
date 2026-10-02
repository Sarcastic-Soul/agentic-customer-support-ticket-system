import { expect, test } from "@playwright/test";
import { mockApi, signIn } from "./mocks";

const PAGES = ["/chat", "/admin/tickets", "/admin/tickets/7", "/console", "/console/approvals", "/admin/metrics"];

test.describe("no horizontal scroll on a phone", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) > 400, "mobile project only");

  for (const path of PAGES) {
    test(path, async ({ page }) => {
      await signIn(page);
      await page.addInitScript(() => {
        localStorage.setItem("support-chat-customer", JSON.stringify({ email: "meera@example.com", customerId: 3 }));
      });
      await mockApi(page);
      await page.routeWebSocket(/\/channels\/web\/ws/, () => {});

      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("#root")).not.toBeEmpty();

      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
    });
  }
});
