import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test as base, type Page } from "@playwright/test";

const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";

type PrivacyAccount = { email: string; password: string };
type Fixtures = { privacyAccount: PrivacyAccount };

function helper(script: string, payload: object) {
  const output = execFileSync("../../.venv/bin/python", [`scripts/${script}`], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify(payload),
    encoding: "utf8",
  });
  return output ? JSON.parse(output) : null;
}

function runtimeFailures(page: Page) {
  const found: string[] = [];
  page.on("console", (message) => message.type() === "error" && found.push(message.text()));
  page.on("pageerror", (error) => found.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") {
      found.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`);
    }
  });
  return found;
}

const test = base.extend<Fixtures>({
  privacyAccount: async ({}, use) => {
    const account = {
      email: `e2e-privacy-${randomUUID()}@example.com`,
      password: "E2E-Privacy-Consent-123aA",
    };
    try {
      await use(account);
    } finally {
      helper("e2e_user.py", { email: account.email });
    }
  },
});

test("viewer grants and withdraws optional analytics consent with raw-event erasure", async ({ page, privacyAccount }, testInfo) => {
  const runtime = runtimeFailures(page);
  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Privacy Viewer");
  await page.getByLabel("Email").fill(privacyAccount.email);
  await page.getByLabel("Password").fill(privacyAccount.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);

  await page.goto("/account");
  const analytics = page.getByLabel("Share optional usage and playback-quality analytics");
  const homepageMode = page.getByLabel("Homepage personalization");
  await expect(analytics).not.toBeChecked();
  await expect(homepageMode).toHaveValue("curated");
  await expect(page.getByText("No analytics consent has been recorded.")).toBeVisible();

  const event = () => ({
    events: [{
      client_event_id: randomUUID(),
      event_type: "search",
      occurred_at: new Date().toISOString(),
      query: "privacy browser evidence",
      result_count: 0,
    }],
  });
  expect((await page.request.post(`${apiOrigin}/analytics/events`, { data: event() })).status()).toBe(403);

  await analytics.check();
  await page.getByRole("button", { name: "Save privacy choices" }).click();
  await expect(analytics).toBeChecked();
  await expect(page.getByText("Last changed", { exact: false })).toBeVisible();
  const granted = helper("e2e_privacy.py", { email: privacyAccount.email });
  expect(granted).toMatchObject({ analytics_enabled: true, homepage_mode: "curated", raw_events: 0 });
  expect(granted.consent_updated_at).not.toBeNull();

  const accepted = await page.request.post(`${apiOrigin}/analytics/events`, { data: event() });
  expect(accepted.status()).toBe(202);
  expect(await accepted.json()).toMatchObject({ accepted: 1 });
  expect(helper("e2e_privacy.py", { email: privacyAccount.email }).raw_events).toBe(1);

  await analytics.uncheck();
  await homepageMode.selectOption("no_algorithm");
  await page.getByRole("button", { name: "Save privacy choices" }).click();
  await expect(analytics).not.toBeChecked();
  await expect(homepageMode).toHaveValue("no_algorithm");
  const withdrawn = helper("e2e_privacy.py", { email: privacyAccount.email });
  expect(withdrawn).toMatchObject({ analytics_enabled: false, homepage_mode: "no_algorithm", raw_events: 0 });
  expect(withdrawn.consent_updated_at).not.toBe(granted.consent_updated_at);
  expect((await page.request.post(`${apiOrigin}/analytics/events`, { data: event() })).status()).toBe(403);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "No Algorithm" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("withdrawn-consent-no-algorithm.png"), fullPage: true });
  expect(runtime).toEqual([]);
});
