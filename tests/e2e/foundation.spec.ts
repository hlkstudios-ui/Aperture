import { expect, test, type Page } from "@playwright/test";

function captureRuntimeFailures(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`);
  });

  return { consoleErrors, failedRequests };
}

test("customer shell renders and routes unauthenticated Studio access to sign-in", async ({ page }, testInfo) => {
  const failures = captureRuntimeFailures(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "View film" })).toBeVisible();
  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  const desktopNavigation = (page.viewportSize()?.width ?? 0) > 1000;
  if (desktopNavigation) {
    await expect(primaryNavigation).toBeVisible();
  } else {
    await expect(primaryNavigation).toBeHidden();
    await expect(page.locator(".cinematic-mobile-menu > summary")).toBeVisible();
  }
  await page.screenshot({ path: testInfo.outputPath("customer-shell.png"), fullPage: true });

  await expect(page.getByRole("link", { name: "Studio", exact: true })).toHaveCount(0);
  await page.goto("/studio");
  await expect(page).toHaveURL(/\/studio\/login/);
  await expect(page.getByRole("heading", { name: "Sign in to Studio" })).toBeVisible();

  expect(failures.consoleErrors).toEqual([]);
  expect(failures.failedRequests).toEqual([]);
});

test("Studio is blocked server-side and its login is responsive", async ({ page }, testInfo) => {
  const failures = captureRuntimeFailures(page);

  await page.goto("/studio");
  await expect(page).toHaveURL(/\/studio\/login/);
  await expect(page.getByText("There is no public administrator registration.")).toBeVisible();
  await expect(page.getByLabel("Administrator email")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("studio-login.png"), fullPage: true });

  expect(failures.consoleErrors).toEqual([]);
  expect(failures.failedRequests).toEqual([]);
});
