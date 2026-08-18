import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const axeSource = readFileSync(join(process.cwd(), "node_modules/axe-core/axe.min.js"), "utf8");
const representativeRoutes = ["/", "/login", "/movies", "/studio/login"];

test("representative public surfaces meet automated WCAG A/AA checks", async ({ page }) => {
  for (const route of representativeRoutes) {
    await page.goto(route);
    await page.addScriptTag({ content: axeSource });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as {
        axe: { run: (root: Document, options: object) => Promise<{ violations: Array<{ id: string; impact: string | null; nodes: unknown[] }> }> };
      }).axe;
      const result = await axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      });
      return result.violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.length }));
    });
    expect(violations, `${route} accessibility violations`).toEqual([]);
  }
});

test("global skip navigation is keyboard-visible and RTL layout does not overflow", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.keyboard.press(testInfo.project.name === "desktop-webkit" ? "Alt+Tab" : "Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await skip.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  await page.locator("html").evaluate((element) => {
    element.dir = "rtl";
    element.lang = "ar";
  });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
