import { expect, test, type Page } from "@playwright/test";

test.skip(process.env.E2E_FLAGS_OFF !== "1", "requires the isolated all-flags-off build");

function captureRuntimeFailures(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const serverErrors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") {
      failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`);
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });

  return { consoleErrors, failedRequests, serverErrors };
}

test("all risky customer features disappear and direct routes fail closed", async ({ page, request }, testInfo) => {
  const failures = captureRuntimeFailures(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const navigationName = (page.viewportSize()?.width ?? 0) > 1000
    ? "Primary navigation"
    : "Mobile navigation";
  if (navigationName === "Mobile navigation") await page.locator(".site-header summary").click();
  const navigation = page.getByRole("navigation", { name: navigationName });
  for (const name of ["Discover", "Community", "Clubs", "Prescription"]) {
    await expect(navigation.getByRole("link", { name, exact: true })).toHaveCount(0);
  }
  await page.screenshot({ path: testInfo.outputPath("all-risky-features-off.png"), fullPage: true });

  for (const path of ["/community", "/clubs", "/discover", "/prescription", "/clubs/parties/not-a-party"]) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), path).toBe(404);
  }

  expect(failures.consoleErrors).toEqual([]);
  expect(failures.failedRequests).toEqual([]);
  expect(failures.serverErrors).toEqual([]);
});

test("disabled API capabilities are absent instead of unauthorized", async ({ request }) => {
  const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";
  for (const path of [
    "/community/movies/00000000-0000-0000-0000-000000000000",
    "/clubs",
    "/recommendations",
    "/recommendations/movie-prescription",
    "/scene-intelligence/sources/00000000-0000-0000-0000-000000000000/context?timestamp=1",
  ]) {
    const response = await request.get(`${apiOrigin}${path}`, { maxRedirects: 0 });
    expect(response.status(), path).toBe(404);
  }
});
