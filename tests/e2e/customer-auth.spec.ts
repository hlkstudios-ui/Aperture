import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

const email = `e2e-viewer-${randomUUID()}@example.com`;
const password = "CinemaViewerPassword123";
const mailpitOrigin = process.env.E2E_MAILPIT_ORIGIN;

function removeUser() {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ email }),
  });
}

test.describe.configure({ mode: "serial" });
test.afterAll(removeUser);

test("customer registers, creates a second profile, and switches profiles", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));

  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Primary Viewer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  await expect(page.getByRole("heading", { name: "Who's watching?" })).toBeVisible();

  await page.getByLabel("Add another profile").fill("Cinephile Guest");
  await page.getByRole("button", { name: "Add profile" }).click();
  const secondProfile = page.getByRole("button", { name: /Cinephile Guest/ });
  await expect(secondProfile).toBeVisible();
  await secondProfile.click();
  await expect(secondProfile).toHaveClass(/active/);
  await page.screenshot({ path: testInfo.outputPath("profile-selection.png"), fullPage: true });

  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test("customer completes the development password-reset journey", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  await page.goto("/forgot-password");
  await page.getByLabel("Account email").fill(email);
  await page.getByRole("button", { name: "Send reset instructions" }).click();
  await page.getByRole("link", { name: "Open development reset link" }).click();
  await expect(page).toHaveURL(/\/reset-password\?token=/);
  const newPassword = "ReplacementCinemaPassword456";
  await page.getByLabel("New password").fill(newPassword);
  await page.getByLabel("Confirm password").fill(newPassword);
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByText("Password updated.", { exact: false })).toBeVisible();
  await page.getByRole("link", { name: "Continue to sign in" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(newPassword);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test("customer completes the staging SMTP password-reset journey", async ({ page }) => {
  test.skip(!mailpitOrigin, "staging Mailpit is not configured");
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));

  await page.goto("/forgot-password");
  await page.getByLabel("Account email").fill(email);
  await page.getByRole("button", { name: "Send reset instructions" }).click();
  await expect(page.getByText(/instructions have been issued/i)).toBeVisible();

  let messageId = "";
  await expect.poll(async () => {
    const response = await page.request.get(`${mailpitOrigin}/api/v1/messages`);
    const body = await response.json() as { messages: Array<{ ID: string; To: Array<{ Address: string }> }> };
    messageId = body.messages.find((message) => message.To.some((recipient) => recipient.Address === email))?.ID ?? "";
    return messageId;
  }).not.toBe("");
  const message = await (await page.request.get(`${mailpitOrigin}/api/v1/message/${messageId}`)).json() as { Subject: string; Text: string };
  expect(message.Subject).toBe("Reset your Aperture password");
  const resetUrl = message.Text.match(/https:\/\/[^\s]+\/reset-password\?token=[^\s]+/)?.[0];
  expect(resetUrl).toBeTruthy();

  await page.goto(resetUrl!);
  const newPassword = "StagingSmtpPassword789cC";
  await page.getByLabel("New password").fill(newPassword);
  await page.getByLabel("Confirm password").fill(newPassword);
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByText("Password updated.", { exact: false })).toBeVisible();
  await page.getByRole("link", { name: "Continue to sign in" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(newPassword);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
