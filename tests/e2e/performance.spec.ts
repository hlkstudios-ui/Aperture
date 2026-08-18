import { expect, test } from "@playwright/test";

test("customer homepage stays within measured loading and hydration budgets", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main.customer-shell")).toBeVisible();
  await page.waitForLoadState("networkidle");

  const responsivePoster = page.locator(".catalog-rails .card-art img[srcset]").first();
  await expect(responsivePoster).toBeVisible();
  await expect(responsivePoster).toHaveAttribute("srcset", /w185\/.+185w.+w342\/.+342w.+w500\/.+500w/);
  await expect(responsivePoster).toHaveAttribute("sizes", /170px.+240px/);

  const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    return {
      domContentLoadedMs: navigation.domContentLoadedEventEnd,
      resourceCount: resources.length,
      scriptTransferBytes: resources
        .filter((resource) => resource.initiatorType === "script")
        .reduce((total, resource) => total + resource.transferSize, 0),
    };
  });

  expect(metrics.domContentLoadedMs).toBeLessThan(5_000);
  expect(metrics.resourceCount).toBeLessThan(40);
  expect(metrics.scriptTransferBytes).toBeLessThan(1_250_000);
});
