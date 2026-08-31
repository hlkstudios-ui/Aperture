import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const email = `e2e-admin-${randomUUID()}@example.com`;
const password = `E2E-Admin-${randomUUID()}-123aA`;
const customerEmail = `e2e-support-${randomUUID()}@example.com`;
const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";
const axeSource = readFileSync(join(process.cwd(), "node_modules/axe-core/axe.min.js"), "utf8");

function manageAdmin(action: "create" | "delete") {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_admin.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action, email, password }),
  });
}
function currentTotp(secret: string) {
  return JSON.parse(execFileSync("../../.venv/bin/python", ["scripts/e2e_totp.py"], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify({ secret }), encoding: "utf8",
  })).code as string;
}

test.beforeAll(() => manageAdmin("create"));
test.afterAll(() => {
  manageAdmin("delete");
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify({ email: customerEmail }),
  });
});

test("provisioned administrator can sign in and reach the server-authorized Studio", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(`${request.method()} ${request.url()}`));

  const registration = await page.request.post(`${apiOrigin}/auth/register`, { data: { email: customerEmail, password: `Customer-${randomUUID()}-123aA`, profile_name: "Support fixture" } });
  expect(registration.status()).toBe(201);

  await page.goto("/studio");
  await expect(page).toHaveURL(/\/studio\/login/);
  await page.getByLabel("Administrator email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter Studio" }).click();

  await expect(page).toHaveURL(/\/studio$/);
  await expect(page.getByRole("heading", { name: "The projection room" })).toBeVisible();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await page.goto("/studio/operations");
  await expect(page).toHaveURL(/\/studio\/operations$/);
  await expect(page.getByRole("heading", { name: "Operations", exact: true })).toBeVisible();
  await expect(page.getByText("Overall state", { exact: true })).toBeVisible();
  await expect(page.getByText("Object storage: available", { exact: true })).toBeVisible();
  await page.goto("/studio/users");
  await expect(page.getByRole("heading", { name: "Users", exact: true })).toBeVisible();
  await expect(page.getByText(/customers$/).first()).toBeVisible();
  await page.getByLabel("Search customers").fill(customerEmail);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("link", { name: "Open" }).click();
  await expect(page.getByRole("heading", { name: customerEmail })).toBeVisible();
  const exportHref = await page.getByRole("link", { name: "Export portable customer JSON" }).getAttribute("href");
  expect(exportHref).toBeTruthy();
  const exportResponse = await page.request.get(`${apiOrigin}${new URL(exportHref!).pathname}`);
  expect(exportResponse.status()).toBe(200);
  expect((await exportResponse.json()).format).toBe("aperture-portable-customer-record-v1");
  await page.getByText("Authorized permanent deletion", { exact: true }).click();
  await page.getByLabel("Exact customer email").fill(customerEmail);
  await page.getByLabel("Type DELETE CUSTOMER").fill("DELETE CUSTOMER");
  await page.locator("details").getByLabel("Reason").fill("Approved isolated browser privacy request");
  await page.getByLabel("Authorization or request reference").fill("E2E-PRIVACY-REQUEST");
  await page.getByRole("button", { name: "Permanently delete customer" }).click();
  await expect(page).toHaveURL(/\/studio\/users\?deleted=1/);
  await expect(page.getByText(customerEmail)).toHaveCount(0);
  await page.goto("/studio/subscriptions");
  await expect(page.getByRole("heading", { name: "Subscriptions", exact: true })).toBeVisible();
  await expect(page.getByText("Provider-authoritative billing", { exact: true })).toBeVisible();
  await page.goto("/studio/storage");
  await expect(page.getByRole("heading", { name: "Storage", exact: true })).toBeVisible();
  await expect(page.getByText("Available", { exact: true })).toBeVisible();
  await expect(page.getByText("enabled", { exact: true })).toBeVisible();
  await page.goto("/studio/settings");
  await page.getByRole("button", { name: "Start MFA enrollment" }).click();
  const secret = await page.getByTestId("mfa-secret").textContent();
  expect(secret).toBeTruthy();
  await page.getByLabel("Current six-digit code").fill(currentTotp(secret!));
  await page.getByRole("button", { name: "Confirm and enable MFA" }).click();
  await expect(page.getByRole("heading", { name: "One-use recovery codes" })).toBeVisible();
  const recoveryCode = await page.locator(".mfa-recovery li code").first().textContent();
  expect(recoveryCode).toBeTruthy();
  const mobileMenu = page.getByText("Menu", { exact: true });
  if (await mobileMenu.isVisible()) await mobileMenu.click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/studio\/login\?signed-out=1/);
  await page.getByLabel("Administrator email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel(/Security code/).fill(recoveryCode!);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.addScriptTag({ content: axeSource });
  const accessibilityViolations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (root: Document, options: object) => Promise<{ violations: Array<{ id: string; impact: string | null; nodes: Array<{ target: unknown }> }> }> } }).axe;
    const result = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
    return result.violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.map((node) => node.target) }));
  });
  expect(accessibilityViolations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("operations-observability.png"), fullPage: true });
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
