import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test as base, type Page } from "@playwright/test";

const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";

type CmsFixture = {
  cmsAccount: { email: string; password: string; slugPrefix: string };
};

function admin(action: "create" | "delete", email: string, password: string) {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_admin.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action, email, password }),
  });
}
function catalog(slugPrefix: string, payload: Record<string, string>) {
  return JSON.parse(
    execFileSync("../../.venv/bin/python", ["scripts/e2e_catalog.py"], {
      cwd: `${process.cwd()}/apps/api`,
      input: JSON.stringify({ slug_prefix: slugPrefix, ...payload }),
      encoding: "utf8",
    }),
  );
}

const test = base.extend<CmsFixture>({
  cmsAccount: async ({}, use) => {
    const account = {
      email: `e2e-cms-${randomUUID()}@example.com`,
      password: `E2E-Cms-${randomUUID()}-123aA`,
      slugPrefix: `e2e-studio-draft-${randomUUID().slice(0, 8)}`,
    };
    admin("create", account.email, account.password);
    try {
      await use(account);
    } finally {
      catalog(account.slugPrefix, { action: "delete_prefix" });
      admin("delete", account.email, account.password);
    }
  },
});
function failures(page: Page) {
  const consoleErrors: string[] = [];
  const requestFailures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("requestfailed", (request) =>
    request.failure()?.errorText !== "net::ERR_ABORTED" && requestFailures.push(
      `${request.method()} ${request.url()}: ${request.failure()?.errorText}`,
    ),
  );
  return { consoleErrors, requestFailures };
}

test("administrator creates a PostgreSQL draft and opens its private catalog preview", async ({
  page,
  request,
  cmsAccount,
}, testInfo) => {
  const { email, password, slugPrefix } = cmsAccount;
  const runtime = failures(page);
  const slug = `${slugPrefix}-${testInfo.project.name}`;
  const title = `E2E Studio Draft ${testInfo.project.name}`;
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/movies/new");
  await expect(
    page.getByRole("heading", { name: "Create a draft movie" }),
  ).toBeVisible();
  await page.getByLabel("Title *").fill(title);
  await page.getByLabel("URL slug *").fill(slug);
  await page.getByLabel("Runtime (minutes) *").fill("97");
  await page.getByLabel("Certification").fill("PG");
  await page.getByLabel("Original language code").fill("en");
  await page.getByLabel("Country code", { exact: true }).fill("CA");
  await page
    .getByLabel("Short description *")
    .fill(
      "A browser-created draft used to prove the Studio publishing boundary.",
    );
  await page
    .getByLabel("Full synopsis *")
    .fill(
      "This original automated fixture is created through the real Studio form and verified directly in PostgreSQL.",
    );
  await page.getByLabel("Speculative Drama").check();
  await page.getByRole("button", { name: "Create draft movie" }).click();
  await expect(page).toHaveURL(/\/studio\/movies\/[0-9a-f-]+\?created=1/);
  await expect(
    page.getByText("Draft created in PostgreSQL.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("draft", { exact: true }).first()).toBeVisible();
  const stored = catalog(slugPrefix, { action: "inspect", slug });
  expect(stored).toMatchObject({ title, slug, status: "draft" });
  const publicResponse = await request.get(
    `${apiOrigin}/catalog/movies/${slug}`,
  );
  expect(publicResponse.status()).toBe(404);
  await page.getByRole("link", { name: "Preview" }).click();
  await expect(page.getByText("Private to Studio")).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: title }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("studio-draft-preview.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Back to editor" }).click();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(
    page.getByText("published", { exact: true }).first(),
  ).toBeVisible();
  expect(
    (
      await request.get(`${apiOrigin}/catalog/movies/${slug}`)
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "Unpublish" }).click();
  await expect(page.getByText("draft", { exact: true }).first()).toBeVisible();
  expect(
    (
      await request.get(`${apiOrigin}/catalog/movies/${slug}`)
    ).status(),
  ).toBe(404);
  await page.goto(`/studio/content?q=${encodeURIComponent(title)}`);
  await expect(
    page.getByRole("cell", { name: new RegExp(title) }),
  ).toBeVisible();
  expect(runtime.consoleErrors).toEqual([]);
  expect(runtime.requestFailures).toEqual([]);
});

test("administrator builds an ordered episodic hierarchy from the series editor", async ({
  page,
  cmsAccount,
}, testInfo) => {
  const { email, password, slugPrefix } = cmsAccount;
  const runtime = failures(page);
  const slug = `${slugPrefix}-series-${testInfo.project.name}`;
  const title = `E2E Harbor Series ${testInfo.project.name}`;
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/series/new");
  await expect(
    page.getByRole("heading", { name: "Create a draft series" }),
  ).toBeVisible();
  await page.getByLabel("Title *").fill(title);
  await page.getByLabel("URL slug *").fill(slug);
  await page
    .getByLabel("Short description *")
    .fill("An ordered episodic Studio fixture.");
  await page
    .getByLabel("Synopsis *")
    .fill("Original development metadata for the browser series workflow.");
  await page.getByLabel("Speculative Drama").check();
  await page.getByRole("button", { name: "Create draft series" }).click();
  await expect(page).toHaveURL(/\/studio\/series\/[0-9a-f-]+\?created=1/);

  const seasonForm = page
    .locator("form")
    .filter({ has: page.getByRole("button", { name: "Create season" }) });
  await seasonForm.getByLabel("Title").fill("First Signals");
  await seasonForm.getByRole("button", { name: "Create season" }).click();
  await expect(page.getByText("Season created")).toBeVisible();

  const episodeForm = page
    .locator("form")
    .filter({
      has: page.getByRole("button", { name: "Create episode", exact: true }),
    });
  await episodeForm.getByLabel("Episode number").fill("1");
  await episodeForm.getByLabel("Title").fill("The Beacon");
  await episodeForm.getByLabel("Runtime (minutes)").fill("41");
  await episodeForm
    .getByLabel("Synopsis")
    .fill("A beacon returns after years of silence.");
  await episodeForm
    .getByRole("button", { name: "Create episode", exact: true })
    .click();
  await expect(page.getByText("Episode created")).toBeVisible();

  const bulkForm = page
    .locator("form")
    .filter({ has: page.getByRole("button", { name: "Create episode batch" }) });
  await bulkForm
    .getByLabel("Episode rows")
    .fill(
      "2 | Low Tide | 43 | A message waits below the pier.\n3 | Far Shore | 45 | The signal crosses the bay.",
    );
  await bulkForm
    .getByRole("button", { name: "Create episode batch" })
    .click();
  await expect(page.getByText("2 episodes created")).toBeVisible();

  expect(catalog(slugPrefix, { action: "inspect_series", slug })).toMatchObject({
    title,
    status: "draft",
    season_count: 1,
    episode_count: 3,
  });
  await page.getByRole("link", { name: "Preview" }).click();
  await expect(page.getByText("1. The Beacon", { exact: false })).toBeVisible();
  await expect(page.getByText("3. Far Shore", { exact: false })).toBeVisible();
  expect(runtime.consoleErrors).toEqual([]);
  expect(runtime.requestFailures).toEqual([]);
});
