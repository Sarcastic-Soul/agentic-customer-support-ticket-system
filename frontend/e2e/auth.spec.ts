import { expect, test } from "@playwright/test";
import { AGENT, json, mockApi } from "./mocks";

test("signing in lands on the tickets dashboard", async ({ page }) => {
  let loginBody: unknown;
  await mockApi(page, {
    "/api/auth/login": (route) => {
      loginBody = route.request().postDataJSON();
      return json(route, { access_token: "test-token", role: AGENT.role, full_name: AGENT.full_name });
    },
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(AGENT.email);
  await page.getByLabel("Password").fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/admin\/tickets$/);
  await expect(page.getByText("TCK-0007").first()).toBeVisible();
  expect(loginBody).toEqual({ email: AGENT.email, password: "secret" });
});
