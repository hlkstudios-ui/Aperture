import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test as base, type Page } from "@playwright/test";

type Fixture = { account: { email: string; password: string; nextPassword: string } };
function removeUser(email: string) {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify({ email }),
  });
}
function provisionSubscription(email: string) {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_subscription.py"], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify({ email }), encoding: "utf8",
  });
}
function runtimeFailures(page: Page) {
  const found: string[] = [];
  page.on("console", (message) => message.type() === "error" && found.push(message.text()));
  page.on("pageerror", (error) => found.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && found.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  return found;
}
const test = base.extend<Fixture>({
  account: async ({}, use) => {
    const token = randomUUID();
    const account = {
      email: `e2e-account-${token}@example.com`,
      password: "E2E-Account-Password-123aA",
      nextPassword: "E2E-Account-Changed-456bB",
    };
    try { await use(account); } finally { removeUser(account.email); }
  },
});
const axeSource = readFileSync(join(process.cwd(), "node_modules/axe-core/axe.min.js"), "utf8");
test.describe.configure({ timeout: 90_000 });

test("viewer manages device sessions and rotates a password without fake billing", async ({ page, browser, account }, testInfo) => {
  const runtime = runtimeFailures(page);
  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Account Viewer");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);

  const secondary = await browser.newContext({ userAgent: "Aperture Secondary Mobile Session" });
  const secondaryPage = await secondary.newPage();
  await secondaryPage.goto("/login");
  await secondaryPage.getByLabel("Email").fill(account.email);
  await secondaryPage.getByLabel("Password").fill(account.password);
  await secondaryPage.getByRole("button", { name: "Continue" }).click();
  await expect(secondaryPage).toHaveURL(/\/profiles$/);

  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "The projection ledger." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No active subscription" })).toBeVisible();
  await expect(page.getByText(/never simulates completed payment/i)).toBeVisible();
  await expect(page.getByText("Essential", { exact: true })).toBeVisible();
  await expect(page.getByText("Cinephile", { exact: true })).toBeVisible();
  provisionSubscription(account.email);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Cinephile" })).toBeVisible();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
  await expect(page.getByText("4K", { exact: true })).toBeVisible();
  await expect(page.getByText("4", { exact: true })).toBeVisible();
  const entitlementResponse = await page.request.get(`${process.env.E2E_API_ORIGIN ?? "http://localhost:8000"}/account`);
  expect(entitlementResponse.ok()).toBeTruthy();
  expect((await entitlementResponse.json()).entitlements).toEqual(expect.arrayContaining([
    expect.objectContaining({ key: "simultaneous_streams", value: { limit: 4 } }),
    expect.objectContaining({ key: "video_quality", value: { max_resolution: "4K" } }),
  ]));
  await page.getByLabel("Interface language").selectOption("fr");
  await page.getByLabel("Preferred audio").selectOption("fr");
  await page.getByLabel("Preferred subtitles").selectOption("en");
  await page.getByLabel("Timezone").selectOption("America/Toronto");
  await page.getByLabel("Enable subtitles by default").check();
  await page.getByRole("button", { name: "Save language preferences" }).click();
  await expect(page.getByLabel("Interface language")).toHaveValue("fr");
  await expect(page.getByLabel("Timezone")).toHaveValue("America/Toronto");
  await expect(page.getByLabel("Enable subtitles by default")).toBeChecked();
  await expect.poll(async () => {
    const response = await page.request.get(`${process.env.E2E_API_ORIGIN ?? "http://localhost:8000"}/auth/me`);
    const accountState = await response.json() as { profiles: Array<{ language: string }> };
    return accountState.profiles[0]?.language;
  }).toBe("fr");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.addScriptTag({ content: axeSource });
  const accessibilityViolations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (root: Document, options: object) => Promise<{ violations: Array<{ id: string; impact: string | null; nodes: unknown[] }> }> } }).axe;
    const result = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
    return result.violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.length }));
  });
  expect(accessibilityViolations).toEqual([]);
  await expect(page.locator(".session-list li")).toHaveCount(2);
  await page.getByRole("button", { name: "Sign out other sessions" }).click();
  await expect(page.locator(".session-list li")).toHaveCount(1);
  await secondaryPage.goto("/account");
  await expect(secondaryPage).toHaveURL(/\/login\?error=session-expired/);
  await secondary.close();

  await page.getByLabel("Current password").fill(account.password);
  await page.getByLabel("New password").fill(account.nextPassword);
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText("Password changed. Other sessions were signed out.")).toBeVisible();
  const verifier = await browser.newContext();
  const verifierPage = await verifier.newPage();
  await verifierPage.goto("/login");
  await verifierPage.getByLabel("Email").fill(account.email);
  await verifierPage.getByLabel("Password").fill(account.nextPassword);
  await verifierPage.getByRole("button", { name: "Continue" }).click();
  await expect(verifierPage).toHaveURL(/\/profiles$/);
  await verifier.close();
  await page.screenshot({ path: testInfo.outputPath("account-dashboard.png"), fullPage: true });
  expect(runtime).toEqual([]);
});
