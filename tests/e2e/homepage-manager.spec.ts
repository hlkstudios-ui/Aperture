import { execFileSync } from "node:child_process";
import { closeSync, openSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { expect, test as base, type Page } from "@playwright/test";

const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";

type Fixture = { account: { email: string; password: string; slugPrefix: string; snapshot: object } };
const lockPath = join(tmpdir(), "aperture-homepage-e2e.lock");
async function lock() {
  for (;;) {
    try { return openSync(lockPath, "wx"); }
    catch { await new Promise((resolve) => setTimeout(resolve, 200)); }
  }
}
function helper(script: string, payload: object) {
  const output = execFileSync("../../.venv/bin/python", [`scripts/${script}`], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify(payload), encoding: "utf8",
  });
  return output ? JSON.parse(output) : null;
}
function runtimeFailures(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  return errors;
}

const test = base.extend<Fixture>({
  account: async ({}, use) => {
    const lockHandle = await lock();
    const token = randomUUID();
    const account = {
      email: `e2e-homepage-${token}@example.com`, password: `E2E-Homepage-${token}-123aA`,
      slugPrefix: `e2e-studio-draft-homepage-${token.slice(0, 8)}`,
      snapshot: helper("e2e_homepage.py", { action: "snapshot" }),
    };
    helper("e2e_admin.py", { action: "create", email: account.email, password: account.password });
    try { await use(account); }
    finally {
      helper("e2e_homepage.py", { action: "restore", snapshot: account.snapshot });
      helper("e2e_catalog.py", { action: "delete_prefix", slug_prefix: account.slugPrefix });
      helper("e2e_admin.py", { action: "delete", email: account.email, password: account.password });
      closeSync(lockHandle); unlinkSync(lockPath);
    }
  },
});
test.describe.configure({ timeout: 120_000 });

test("Studio publishes a reordered homepage draft without source edits", async ({ page, account }, testInfo) => {
  const runtime = runtimeFailures(page);
  const title = `Homepage Feature ${testInfo.project.name}`;
  const railName = `Festival Picks ${testInfo.project.name}`;
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/movies/new");
  await page.getByLabel("Title *").fill(title);
  await page.getByLabel("URL slug *").fill(`${account.slugPrefix}-${testInfo.project.name}`);
  await page.getByLabel("Runtime (minutes) *").fill("96");
  await page.getByLabel("Short description *").fill("A Studio-programmed feature proving the homepage publication boundary.");
  await page.getByLabel("Full synopsis *").fill("Original homepage manager browser acceptance metadata.");
  await page.getByLabel("Speculative Drama").check();
  await page.getByRole("button", { name: "Create draft movie" }).click();
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(page.getByText("published", { exact: true }).first()).toBeVisible();

  await page.goto("/studio/homepage");
  await expect(page.getByRole("heading", { name: "Homepage manager" })).toBeVisible();
  await page.getByLabel("Hero title").selectOption({ label: `Movie · ${title}` });
  await page.getByRole("button", { name: "Set hero" }).click();
  await page.getByLabel("Rail name").first().fill("Recently programmed");
  await page.getByLabel("Source").first().selectOption("latest_movies");
  await page.getByRole("button", { name: "Create rail" }).click();
  await page.getByLabel("Rail name").first().fill(railName);
  await page.getByRole("button", { name: "Create rail" }).click();
  const festival = page.locator("article").filter({ hasText: railName });
  await festival.getByLabel("Pin title").selectOption({ label: `Movie · ${title}` });
  await festival.getByRole("button", { name: "Pin", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(festival.locator(".homepage-items").getByText(new RegExp(title))).toBeVisible();
  await festival.getByRole("button", { name: `Move ${railName} up` }).click();
  await expect(page.locator("article").first().getByRole("heading", { name: railName })).toBeVisible();

  await page.getByRole("link", { name: "Preview draft" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: railName })).toBeVisible();
  await page.goto("/studio/homepage");
  await page.getByRole("button", { name: "Publish homepage" }).click();
  await expect.poll(async () => {
    const response = await page.request.get(`${apiOrigin}/homepage`);
    return (await response.json()).rails.map((rail: { title: string }) => rail.title);
  }).toContain(railName);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: railName })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("published-homepage.png"), fullPage: true });
  expect(runtime).toEqual([]);
});
