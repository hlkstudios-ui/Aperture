import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

const email = `e2e-recommendations-${randomUUID()}@example.com`;
const password = "RecommendationViewerPassword123";

test.afterAll(() => {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ email }),
  });
});

test("viewer can inspect explainable cold-start recommendations", async ({
  page,
}, testInfo) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) =>
    request.failure()?.errorText !== "net::ERR_ABORTED" && failedRequests.push(
      `${request.method()} ${request.url()}: ${request.failure()?.errorText}`,
    ),
  );

  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Discovery Viewer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);

  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "Discover" })).toBeVisible();
  await expect(
    page.getByText("Explainable rules, not machine learning."),
  ).toBeVisible();
  await expect(page.getByText("Why this appears").first()).toBeVisible();
  await expect(page.getByText("A strong place to begin").first()).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("explainable-recommendations.png"),
    fullPage: true,
  });

  await page.goto("/prescription");
  await expect(
    page.getByRole("heading", { name: "Movie Prescription" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Taste DNA" })).toBeVisible();
  await expect(page.getByText("Cold-start state: no behavior is inferred.")).toBeVisible();
  await page.getByLabel("Time available (minutes)").fill("180");
  await page.getByRole("button", { name: "Prescribe one movie" }).click();
  await expect(page.getByText(/One best fit · \d+% match/)).toBeVisible();
  await expect(page.getByRole("link", { name: "View & play" })).toBeVisible();
  await expect(
    page.getByRole("definition").filter({
      hasText: /Runs \d+ minutes within your 180-minute limit/,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("movie-prescription-result.png"),
    fullPage: true,
  });

  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
