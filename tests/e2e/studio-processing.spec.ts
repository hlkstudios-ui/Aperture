import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test as base, type Page } from "@playwright/test";

type Fixture = { mediaFixture: { email: string; password: string; filename: string; path: string } };
function helper(script: string, payload: object) {
  return JSON.parse(execFileSync("../../.venv/bin/python", [`scripts/${script}`], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify(payload), encoding: "utf8",
  }) || "null");
}
function failures(page: Page) {
  const found: string[] = [];
  page.on("console", (message) => message.type() === "error" && found.push(message.text()));
  page.on("pageerror", (error) => found.push(error.message));
  page.on("requestfailed", (request) => request.failure()?.errorText !== "net::ERR_ABORTED" && found.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  return found;
}

const test = base.extend<Fixture>({
  mediaFixture: async ({}, use) => {
    const token = randomUUID();
    const directory = mkdtempSync(join(tmpdir(), "aperture-e2e-media-"));
    const fixture = {
      email: `e2e-processing-${token}@example.com`, password: `E2E-Processing-${token}-123aA`,
      filename: `e2e-upload-processing-${token}.mp4`, path: join(directory, "source.mp4"),
    };
    execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24", "-f", "lavfi", "-i", "sine=frequency=523:sample_rate=48000", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", fixture.path]);
    helper("e2e_admin.py", { action: "create", email: fixture.email, password: fixture.password });
    try { await use(fixture); }
    finally {
      helper("e2e_upload.py", { action: "delete", filename: fixture.filename });
      helper("e2e_admin.py", { action: "delete", email: fixture.email, password: fixture.password });
      rmSync(directory, { recursive: true, force: true });
    }
  },
});

test("background worker produces a validated adaptive manifest from a Studio upload", async ({ page, mediaFixture }, testInfo) => {
  test.setTimeout(60_000);
  const runtime = failures(page);
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(mediaFixture.email);
  await page.getByLabel("Password").fill(mediaFixture.password);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/uploads");
  const fileInput = page.getByLabel(/Choose a permitted source file/);
  await expect(fileInput).toBeEnabled();
  await fileInput.setInputFiles({
    name: mediaFixture.filename, mimeType: "video/mp4", buffer: readFileSync(mediaFixture.path),
  });
  await page.getByRole("button", { name: "Start secure upload" }).click();
  const uploadRow = page.locator(".upload-list li").filter({ hasText: mediaFixture.filename });
  await expect(uploadRow.getByText("completed", { exact: true })).toBeVisible();
  await uploadRow.getByRole("button", { name: "Queue processing" }).click();
  await expect(page.getByText("Processing job queued", { exact: false })).toBeVisible();
  await page.goto("/studio/processing");
  const card = page.locator("article").filter({ hasText: mediaFixture.filename });
  await expect(card.locator(".catalog-badge", { hasText: "ready" })).toBeVisible({ timeout: 45_000 });
  await expect(card.getByText("Adaptive manifest validated")).toBeVisible();
  await expect(card.getByText("360p", { exact: true })).toBeVisible();
  const stored = helper("e2e_upload.py", { action: "inspect_processing", filename: mediaFixture.filename });
  expect(stored).toMatchObject({ state: "ready", progress_percent: 100, source_metadata: { video_codec: "h264", width: 640, height: 360 } });
  expect(stored.manifest).toContain("#EXTM3U");
  expect(stored.manifest).toContain("360p/index.m3u8");
  expect(stored.thumbnail_key).toBeTruthy(); expect(stored.sprite_key).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("studio-processing-ready.png"), fullPage: true });
  expect(runtime).toEqual([]);
});
