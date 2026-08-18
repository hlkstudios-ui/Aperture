import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { expect, test as base, type Page } from "@playwright/test";

type Fixture = { account: { email: string; password: string; filename: string } };

function admin(action: "create" | "delete", email: string, password: string) {
  execFileSync("../../.venv/bin/python", ["scripts/e2e_admin.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action, email, password }),
  });
}
function upload(action: "inspect" | "delete", filename: string) {
  return JSON.parse(execFileSync("../../.venv/bin/python", ["scripts/e2e_upload.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action, filename }),
    encoding: "utf8",
  }));
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
    const token = randomUUID();
    const account = {
      email: `e2e-upload-${token}@example.com`,
      password: `E2E-Upload-${token}-123aA`,
      filename: `e2e-upload-${token}.mp4`,
    };
    admin("create", account.email, account.password);
    try { await use(account); }
    finally { upload("delete", account.filename); admin("delete", account.email, account.password); }
  },
});

test("administrator uploads a checksummed video directly into object storage", async ({ page, account }, testInfo) => {
  const failures = runtimeFailures(page);
  const content = Buffer.concat([
    Buffer.from([0, 0, 0, 24]), Buffer.from("ftypisom"),
    Buffer.from([0, 0, 2, 0]), Buffer.from("isomiso2"),
    Buffer.from("Aperture browser development fixture".repeat(64)),
  ]);
  const checksum = createHash("sha256").update(content).digest("hex");
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/uploads");
  await expect(page.getByRole("heading", { name: "Source uploads" })).toBeVisible();
  const fileInput = page.getByLabel(/Choose a permitted source file/);
  await expect(fileInput).toBeEnabled();
  await fileInput.setInputFiles({
    name: account.filename, mimeType: "video/mp4", buffer: content,
  });
  await page.getByRole("button", { name: "Start secure upload" }).click();
  const uploadRow = page.locator(".upload-list li").filter({ hasText: account.filename });
  await expect(uploadRow.getByText("completed", { exact: true })).toBeVisible();
  await expect(uploadRow.getByText(account.filename, { exact: true })).toBeVisible();
  const stored = upload("inspect", account.filename);
  expect(stored).toMatchObject({
    state: "completed", size_bytes: content.length, object_size: content.length,
    checksum_sha256: checksum, object_checksum: checksum,
  });
  expect(stored.storage_key).not.toContain(account.filename);
  await page.screenshot({ path: testInfo.outputPath("studio-upload-complete.png"), fullPage: true });
  expect(failures).toEqual([]);
});

test("administrator resumes a multipart upload after an interrupted part", async ({ page, account }) => {
  test.setTimeout(60_000);
  const content = Buffer.alloc(17 * 1024 * 1024, 0x61);
  Buffer.from([0, 0, 0, 24]).copy(content, 0); Buffer.from("ftypisom").copy(content, 4);
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/uploads");
  let interrupted = false;
  await page.route(/partNumber=2/, async (route) => {
    interrupted = true; await route.abort("failed");
  });
  const input = page.getByLabel(/Choose a permitted source file/);
  await input.setInputFiles({ name: account.filename, mimeType: "video/mp4", buffer: content });
  await page.getByRole("button", { name: "Start secure upload" }).click();
  await expect(page.getByText("Multipart upload retained", { exact: false })).toBeVisible();
  expect(interrupted).toBe(true);
  await page.unroute(/partNumber=2/);
  await page.getByRole("button", { name: "Start secure upload" }).click();
  const row = page.locator(".upload-list li").filter({ hasText: account.filename });
  await expect(row.getByText("completed", { exact: true })).toBeVisible({ timeout: 30_000 });
  expect(upload("inspect", account.filename)).toMatchObject({
    state: "completed", size_bytes: content.length, object_size: content.length,
  });
});
