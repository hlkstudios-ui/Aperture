import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

const token = randomUUID();
const password = "CommunityBrowserViewer123";
const adminPassword = `Community-Admin-${token}-123aA`;
const headline = `Moderated review ${token.slice(0, 8)}`;

const identities = (projectName:string) => {
  const project=projectName.replace(/[^a-z]/g,"-");
  return {email:`e2e-community-${project}-${token}@example.com`,adminEmail:`e2e-community-admin-${project}-${token}@example.com`};
};
test.beforeEach(({},testInfo) => {
  const {adminEmail}=identities(testInfo.project.name);
  execFileSync("../../.venv/bin/python", ["scripts/e2e_admin.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action:"create", email:adminEmail, password:adminPassword }),
  });
});
test.afterEach(({},testInfo) => {
  const {email,adminEmail}=identities(testInfo.project.name);
  execFileSync("../../.venv/bin/python", ["scripts/e2e_user.py"], {
    cwd: `${process.cwd()}/apps/api`, input:JSON.stringify({email}),
  });
  execFileSync("../../.venv/bin/python", ["scripts/e2e_admin.py"], {
    cwd: `${process.cwd()}/apps/api`,
    input: JSON.stringify({ action:"delete", email:adminEmail, password:adminPassword }),
  });
});

test("review stays private until Studio moderation and preserves its spoiler flag", async ({page}, testInfo) => {
  const {email,adminEmail}=identities(testInfo.project.name);
  const consoleErrors:string[]=[]; const failedRequests:string[]=[];
  page.on("console",message=>{if(message.type()==="error")consoleErrors.push(message.text());});
  page.on("pageerror",error=>consoleErrors.push(error.message));
  page.on("requestfailed",request=>request.failure()?.errorText!=="net::ERR_ABORTED"&&failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Community Reviewer");
  await page.getByLabel("Email").fill(email); await page.getByLabel("Password").fill(password);
  await page.getByRole("button",{name:"Create account"}).click();
  await expect(page).toHaveURL(/\/profiles$/);
  await page.goto("/movies/the-lantern-sea");
  await expect(page).toHaveURL(/\/movies\/[^/]+$/);
  const movieUrl=page.url();
  await expect(page.getByRole("heading",{name:"Ratings & reviews"})).toBeVisible();
  await page.getByRole("button",{name:"Rate 5 out of 5"}).click();
  await expect(page.getByText("Rating saved privately to this profile.")).toBeVisible();
  await page.getByLabel("Review headline").fill(headline);
  await page.getByLabel("Your review").fill("The closing image deliberately echoes the first shot.");
  await page.getByLabel("Contains spoilers").check();
  await page.getByRole("button",{name:"Submit for moderation"}).click();
  await expect(page.getByText("Review submitted for moderation. It is not public yet.")).toBeVisible();
  await expect(page.getByText(headline)).toHaveCount(0);

  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(adminEmail);
  await page.getByLabel("Password").fill(adminPassword);
  await page.getByRole("button",{name:"Enter Studio"}).click();
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/studio/community");
  const pending=page.locator(".moderation-stack article",{hasText:headline});
  await expect(pending).toBeVisible();
  await page.screenshot({path:testInfo.outputPath("community-moderation-queue.png"),fullPage:true});
  await pending.getByLabel("Decision reason").first().fill("Spoiler flag is present and the review meets policy.");
  await pending.getByRole("button",{name:"Approve"}).click();
  await expect(page.locator(".moderation-stack article",{hasText:headline})).toHaveCount(0);

  await page.goto(movieUrl);
  await expect(page.getByText(headline)).toBeVisible();
  const approved=page.locator(".review-list article",{hasText:headline});
  await approved.getByText("Spoiler-tagged review — reveal").click();
  await expect(approved.getByText("The closing image deliberately echoes the first shot.")).toBeVisible();
  await page.screenshot({path:testInfo.outputPath("moderated-spoiler-review.png"),fullPage:true});
  expect(consoleErrors).toEqual([]); expect(failedRequests).toEqual([]);
});
