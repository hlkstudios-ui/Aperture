import { expect, test, type Locator, type Page } from "@playwright/test";

const systemChromeExecutable = process.env.E2E_CHROME_EXECUTABLE;
if (systemChromeExecutable) {
  test.use({ launchOptions: { executablePath: systemChromeExecutable } });
}

type Viewport = {
  height: number;
  label: string;
  width: number;
};

const desktopViewports: Viewport[] = [
  { width: 1440, height: 900, label: "1440 desktop" },
  { width: 1024, height: 768, label: "1024 compact desktop" },
  { width: 931, height: 760, label: "931 desktop boundary" },
];

const mobileViewports: Viewport[] = [
  { width: 930, height: 900, label: "930 mobile boundary" },
  { width: 390, height: 844, label: "390 phone" },
  { width: 844, height: 390, label: "844x390 landscape" },
];

async function openRoute(page: Page, viewport: Viewport, route = "/movies") {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto(route, { waitUntil: "load" });
  const headers = page.locator("header.cinematic-nav");
  // Streaming routes briefly render their loading shell and resolved page together.
  await expect(headers).toHaveCount(1);
  await expect(headers.first()).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page, context: string) {
  const overflow = await page.evaluate(() => {
    const widest = Math.max(
      document.documentElement.scrollWidth,
      document.body?.scrollWidth ?? 0,
    );
    return widest - window.innerWidth;
  });
  expect(overflow, `${context} horizontal overflow`).toBeLessThanOrEqual(1);
}

async function expectMinimumTargetSize(scope: Locator, context: string) {
  const targets = scope.locator("a, button");
  const count = await targets.count();

  for (let index = 0; index < count; index += 1) {
    const target = targets.nth(index);
    if (!(await target.isVisible())) continue;

    const box = await target.boundingBox();
    const name = await target.evaluate((element) =>
      element.getAttribute("aria-label") || element.textContent?.replace(/\s+/g, " ").trim() || element.tagName,
    );
    expect(box, `${context}: ${name} has a measurable target`).not.toBeNull();
    expect(box!.width, `${context}: ${name} target width`).toBeGreaterThanOrEqual(44);
    expect(box!.height, `${context}: ${name} target height`).toBeGreaterThanOrEqual(44);
  }
}

async function openDisclosure(trigger: Locator) {
  // App Router HTML can finish loading just before React attaches delegated events.
  await expect(async () => {
    if (await trigger.getAttribute("aria-expanded") !== "true") {
      await trigger.click();
    }
    await expect(trigger).toHaveAttribute("aria-expanded", "true", { timeout: 1_000 });
  }).toPass({ intervals: [100, 250, 500], timeout: 15_000 });
}

for (const viewport of desktopViewports) {
  test(`shared navbar keeps its desktop links and active route at ${viewport.label}`, async ({ page }) => {
    await openRoute(page, viewport);

    const header = page.locator("header.cinematic-nav");
    const primary = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primary).toBeVisible();
    await expect(header.locator(".cinematic-mobile-actions")).toBeHidden();
    await expect(page.getByRole("navigation", { name: "Quick navigation" })).toBeHidden();

    const coreLinks = [
      { name: "Home", href: "/" },
      { name: "Browse", href: "/browse" },
      { name: "Movies", href: "/movies" },
      { name: "Series", href: "/series" },
    ];
    for (const link of coreLinks) {
      await expect(primary.getByRole("link", { name: link.name, exact: true })).toHaveAttribute("href", link.href);
    }

    await expect(primary.getByRole("link", { name: "Movies", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(primary.getByRole("link", { name: "Home", exact: true })).not.toHaveAttribute("aria-current", "page");
    await expect(primary.getByRole("button", { name: "Discover" })).toBeVisible();

    await expectMinimumTargetSize(header, viewport.label);
    await expectNoHorizontalOverflow(page, viewport.label);
  });
}

test("Discover opens as a bounded cinematic panel and returns focus on Escape", async ({ page }) => {
  const viewport = desktopViewports[0];
  await openRoute(page, viewport, "/trending");

  const header = page.locator("header.cinematic-nav");
  const discover = page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("button", { name: "Discover" });
  await expect(discover).toHaveAttribute("aria-controls", "aperture-discover-menu");
  await expect(discover).toHaveAttribute("aria-expanded", "false");
  await expect(discover).toHaveClass(/is-active/);

  await openDisclosure(discover);
  await expect(discover).toHaveAttribute("aria-expanded", "true");
  const menu = page.locator("#aperture-discover-menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("heading", { name: "Find the right story for tonight." })).toBeVisible();
  await expect(menu.getByRole("navigation", { name: "Watch now" })).toBeVisible();
  await expect(menu.getByRole("navigation", { name: "Explore deeper" })).toBeVisible();
  await expect(menu.getByRole("link", { name: /^Trending now/ })).toHaveAttribute("aria-current", "page");
  await expect(menu.getByRole("link", { name: /^Signal Run/ })).toBeVisible();

  const headerBox = await header.boundingBox();
  const menuBox = await menu.boundingBox();
  const linksBox = await menu.locator(".cinematic-mega-links").boundingBox();
  const featureBox = await menu.locator(".cinematic-mega-feature").boundingBox();
  expect(headerBox).not.toBeNull();
  expect(menuBox).not.toBeNull();
  expect(linksBox).not.toBeNull();
  expect(featureBox).not.toBeNull();
  expect(menuBox!.x).toBeGreaterThanOrEqual(headerBox!.x - 1);
  expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(headerBox!.x + headerBox!.width + 1);
  expect(menuBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height + 6);
  expect(menuBox!.y + menuBox!.height).toBeLessThanOrEqual(viewport.height + 1);
  expect(featureBox!.x).toBeGreaterThan(linksBox!.x);
  expect(featureBox!.y).toBeLessThan(linksBox!.y + linksBox!.height);

  await expectMinimumTargetSize(menu, "Discover panel");
  await expectNoHorizontalOverflow(page, "open Discover panel");

  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(discover).toHaveAttribute("aria-expanded", "false");
  await expect(discover).toBeFocused();

  await openDisclosure(discover);
  await expect(page.locator("#aperture-discover-menu")).toBeVisible();
  await page.mouse.click(2, Math.floor(viewport.height / 2));
  await expect(page.locator("#aperture-discover-menu")).toHaveCount(0);
  await expect(discover).toHaveAttribute("aria-expanded", "false");
});

for (const viewport of mobileViewports) {
  test(`mobile top bar, dock, and menu stay usable at ${viewport.label}`, async ({ page }) => {
    await openRoute(page, viewport, "/browse");

    const header = page.locator("header.cinematic-nav");
    const primary = page.getByRole("navigation", { name: "Primary navigation" });
    const mobileActions = header.locator(".cinematic-mobile-actions");
    const dock = page.getByRole("navigation", { name: "Quick navigation" });
    await expect(primary).toBeHidden();
    await expect(mobileActions).toBeVisible();
    await expect(mobileActions.getByRole("link", { name: "Search Aperture" })).toBeVisible();
    await expect(dock).toBeVisible();

    for (const link of [
      { name: "Home", href: "/" },
      { name: "Browse", href: "/browse" },
      { name: "Search", href: "/search" },
      { name: "My List", href: "/my-list" },
    ]) {
      await expect(dock.getByRole("link", { name: link.name, exact: true })).toHaveAttribute("href", link.href);
    }
    await expect(dock.getByRole("link", { name: "Browse", exact: true })).toHaveAttribute("aria-current", "page");

    const headerBox = await header.boundingBox();
    const dockBox = await dock.boundingBox();
    expect(headerBox).not.toBeNull();
    expect(dockBox).not.toBeNull();
    expect(headerBox!.x).toBeGreaterThanOrEqual(0);
    expect(headerBox!.x + headerBox!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(dockBox!.x).toBeGreaterThanOrEqual(0);
    expect(dockBox!.x + dockBox!.width).toBeLessThanOrEqual(viewport.width + 1);
    await expectMinimumTargetSize(header, `${viewport.label} top bar`);
    await expectMinimumTargetSize(dock, `${viewport.label} dock`);
    await expectNoHorizontalOverflow(page, `${viewport.label} closed`);

    const menuButton = mobileActions.locator('button[aria-controls="aperture-mobile-menu"]');
    await expect(menuButton).toHaveAttribute("aria-controls", "aperture-mobile-menu");
    await openDisclosure(menuButton);
    const panel = page.getByRole("dialog", { name: "Aperture menu" });
    await expect(panel).toBeVisible();
    await expect(menuButton).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("html")).toHaveClass(/aperture-nav-open/);
    await expect(panel.getByRole("link", { name: "Search films, series and cast" })).toBeVisible();
    await expect(panel.getByRole("link", { name: "Home", exact: true })).toBeVisible();
    await expect(panel.getByRole("link", { name: "Browse", exact: true })).toBeVisible();
    await expect(panel.getByRole("navigation", { name: "Your library" })).toBeVisible();
    await expect(panel.getByRole("navigation", { name: "More from Aperture" })).toBeVisible();
    await expect(dock).toBeHidden();

    const panelBox = await panel.boundingBox();
    expect(panelBox).not.toBeNull();
    expect(panelBox!.x).toBeGreaterThanOrEqual(0);
    expect(panelBox!.x + panelBox!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(panelBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height + 4);
    expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(viewport.height + 1);
    await expectMinimumTargetSize(panel, `${viewport.label} menu`);
    await expectNoHorizontalOverflow(page, `${viewport.label} open`);

    if (viewport.height === 390) {
      const scrolling = await panel.evaluate((element) => {
        const before = element.scrollTop;
        element.scrollTop = element.scrollHeight;
        return {
          before,
          after: element.scrollTop,
          clientHeight: element.clientHeight,
          overflowY: getComputedStyle(element).overflowY,
          scrollHeight: element.scrollHeight,
        };
      });
      expect(scrolling.scrollHeight, "short menu has content below the fold").toBeGreaterThan(scrolling.clientHeight);
      expect(scrolling.overflowY).toMatch(/auto|scroll/);
      expect(scrolling.after).toBeGreaterThan(scrolling.before);
      await expect(panel.getByRole("link", { name: "Switch or sign in" })).toBeVisible();
    }

    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    await expect(menuButton).toBeFocused();
    await expect(page.locator("html")).not.toHaveClass(/aperture-nav-open/);
    await expect(dock).toBeVisible();

    await openDisclosure(menuButton);
    await expect(page.getByRole("dialog", { name: "Aperture menu" })).toBeVisible();
    await page.mouse.click(2, Math.floor(viewport.height / 2));
    await expect(page.getByRole("dialog", { name: "Aperture menu" })).toHaveCount(0);
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    await expect(dock).toBeVisible();
  });
}
