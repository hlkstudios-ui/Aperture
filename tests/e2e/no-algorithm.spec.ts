import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

const email = `e2e-no-algorithm-${randomUUID()}@example.com`;
const password = "NoAlgorithmViewerPassword123";

test.afterAll(() => {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ email }),
  });
});

test("viewer switches to a persistent deterministic homepage", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) =>
    request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`),
  );

  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Index Explorer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);

  await page.goto("/");
  await expect(page.getByText("Homepage strategy")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Curated", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Switch to No Algorithm" }).click();
  await expect(page.getByRole("heading", { name: "No Algorithm" })).toBeVisible();
  await expect(page.getByText("Transparent catalog indexes.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recently added" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "A–Z" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Release year" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "No Algorithm" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("no-algorithm-homepage.png"), fullPage: true });
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
