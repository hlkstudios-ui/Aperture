import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test as base } from "@playwright/test";

type ClubFixture = { account: { email: string; password: string; movieTitle: string; slug: string } };

function helper(script: string, payload: object) {
  return JSON.parse(execFileSync("../../.venv/bin/python", [`scripts/${script}`], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify(payload), encoding: "utf8",
  }) || "null");
}

const test = base.extend<ClubFixture>({
  account: async ({}, use, testInfo) => {
    const token = randomUUID();
    const project = testInfo.project.name.replace(/[^a-z]/g, "-");
    const account = {
      email: `e2e-club-${project}-${token}@example.com`,
      password: "ClubBrowserViewerPassword123",
      movieTitle: `Playback Fixture ${project} ${token.slice(0, 6)}`,
      slug: `e2e-club-playback-${project}-${token}`,
    };
    helper("e2e_club_fixture.py", { action: "create", slug: account.slug, title: account.movieTitle });
    try { await use(account); }
    finally {
      helper("e2e_user.py", { email: account.email });
      helper("e2e_club_fixture.py", { action: "delete", slug: account.slug });
    }
  },
});

test("host creates a private club and controls an authorized synchronized party", async ({ page, account }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`);
  });
  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Club Host");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  await page.goto("/clubs");
  await expect(page.getByRole("heading", { name: "Movie Clubs" })).toBeVisible();
  await page.getByLabel("Club name").fill(`Midnight Frames ${account.slug.slice(-6)}`);
  await page.getByLabel("Description").fill("A private synchronized screening club.");
  await page.getByRole("button", { name: "Create private club" }).click();
  await expect(page.getByText("Private invitation token")).toBeVisible();
  const film = page.getByLabel("Film");
  const playbackValue = await film.locator("option").filter({ hasText: account.movieTitle }).getAttribute("value");
  expect(playbackValue).toBeTruthy();
  await film.selectOption(playbackValue!);
  await page.getByLabel("Event title").fill("Friday screening");
  await page.getByLabel("Local date and time").fill("2026-08-16T20:00");
  await page.getByRole("button", { name: "Schedule" }).click();
  await expect(page.getByText("Friday screening")).toBeVisible();
  await page.getByRole("button", { name: "Start party" }).click();
  await expect(page).toHaveURL(/\/clubs\/parties\//);
  await expect(page.getByRole("heading", { name: "waiting" })).toBeVisible();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("heading", { name: "playing" })).toBeVisible();
  await page.getByLabel("Message").fill("The projector is synchronized.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("The projector is synchronized.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open authorized stream" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("private-watch-party.png"), fullPage: true });
  expect(errors).toEqual([]);
});
