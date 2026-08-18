import { expect, test, type Page } from "@playwright/test";

function captureRuntimeFailures(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on(
    "requestfailed",
    (request) =>
      request.failure()?.errorText !== "net::ERR_ABORTED" &&
      failedRequests.push(
        `${request.method()} ${request.url()}: ${request.failure()?.errorText}`,
      ),
  );
  return { consoleErrors, failedRequests };
}

test("published movie loads from the live catalog and exposes honest detail states", async ({
  page,
}, testInfo) => {
  const failures = captureRuntimeFailures(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Show slide 1: The Lantern Sea" })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "The Lantern Sea" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Every trap has a beginning — The Saw Marathon",
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "View film" }).click();
  await expect(page).toHaveURL(/\/movies\/the-lantern-sea/);
  await expect(
    page.getByRole("heading", { name: "The Lantern Sea", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "This catalog title has no licensed video asset attached yet.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "＋ My List" }).click();
  await expect(page).toHaveURL(/\/login\?next=my-list$/);
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "The universe around The Lantern Sea" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Canada/ })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("movie-detail.png"),
    fullPage: true,
  });
  expect(failures.consoleErrors).toEqual([]);
  expect(failures.failedRequests).toEqual([]);
});

test("series hierarchy and multi-domain search load from the running stack", async ({
  page,
}, testInfo) => {
  const failures = captureRuntimeFailures(page);
  await page.goto("/series/harbor-signals");
  await expect(
    page.getByRole("heading", { name: "Harbor Signals" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "The Bell" })).toBeVisible();
  await expect(page.getByLabel("Choose season")).toHaveValue(/.+/);
  await page.goto("/search?q=Speculative");
  await expect(
    page.getByRole("heading", { name: "Find anything." }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Related matches" })
      .getByRole("link", { name: "genre Speculative Drama" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("catalog-search.png"),
    fullPage: true,
  });
  expect(failures.consoleErrors).toEqual([]);
  expect(failures.failedRequests).toEqual([]);
});
