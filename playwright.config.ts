import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "test-results/playwright",
  fullyParallel: true,
  workers: 2,
  forbidOnly: true,
  retries: 0,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: externalBaseUrl ?? "http://localhost:3000",
    ignoreHTTPSErrors: Boolean(externalBaseUrl),
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
    { name: "tablet-chromium", use: { ...devices["iPad Pro 11"], browserName: "chromium" } },
    { name: "large-desktop-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } } },
    { name: "desktop-firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "desktop-webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: externalBaseUrl ? undefined : {
    command: "PATH=/opt/homebrew/bin:$PATH npm run dev:web",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
