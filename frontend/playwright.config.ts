import { defineConfig, devices } from "@playwright/test";

// Every test mocks /api/** and the chat WebSocket, so no backend is needed:
// only the Vite dev server runs.
const PORT = 5199;
// 127.0.0.1, not localhost: on some machines localhost also resolves to a
// LAN address, and the readiness check hangs on it until it times out.
const HOST = "127.0.0.1";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  // Vite compiles modules on first request; a dozen browsers asking at once
  // on a busy machine is slower than a few. Keep it small and allow time.
  workers: 4,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://${HOST}:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true },
    },
  ],
  webServer: {
    command: `pnpm dev --host ${HOST} --port ${PORT} --strictPort`,
    url: `http://${HOST}:${PORT}`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
