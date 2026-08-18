import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { closeSync, mkdtempSync, openSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test as base, type Page } from "@playwright/test";

const apiOrigin = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";
const playbackLockPath = join(tmpdir(), "aperture-playback-e2e.lock");

async function playbackLock() {
  for (;;) {
    try { return openSync(playbackLockPath, "wx"); }
    catch { await new Promise((resolve) => setTimeout(resolve, 200)); }
  }
}

type Fixture = { playbackFixture: { adminEmail: string; adminPassword: string; viewerEmail: string; viewerPassword: string; filename: string; path: string; slug: string; title: string } };
function helper(script: string, payload: object) {
  const output = execFileSync("../../.venv/bin/python", [`scripts/${script}`], {
    cwd: `${process.cwd()}/apps/api`, input: JSON.stringify(payload), encoding: "utf8",
  });
  return output ? JSON.parse(output) : null;
}
function runtimeFailures(page: Page, projectName: string) {
  const found: string[] = [];
  const expectedInterruptedPlay = (text: string) => text.includes("play() request was interrupted by a call to pause()");
  const expectedWebkitCancellation = (text: string) => projectName === "desktop-webkit" && (
    text === "TypeError: Load failed" ||
    (text.includes("due to access control checks.") && (text.includes("_rsc=") || text.includes("/progress")))
  );
  page.on("console", (message) => {
    const text = message.text();
    const interruptedPlay = expectedInterruptedPlay(text);
    const expectedFirefoxHlsAbort = projectName === "desktop-firefox" && text === "JSHandle@object";
    const expectedWebkitAbort = expectedWebkitCancellation(text);
    if (message.type() === "error" && !interruptedPlay && !expectedFirefoxHlsAbort && !expectedWebkitAbort) found.push(text);
  });
  page.on("pageerror", (error) => {
    if (!expectedInterruptedPlay(error.message) && !expectedWebkitCancellation(error.message)) found.push(error.message);
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText;
    const expectedBrowserAbort = failure === "net::ERR_ABORTED" || failure === "NS_BINDING_ABORTED" || failure === "NS_BASE_STREAM_CLOSED" || failure === "cancelled";
    if (!expectedBrowserAbort) found.push(`${request.method()} ${request.url()}: ${failure}`);
  });
  return found;
}

const test = base.extend<Fixture>({
  playbackFixture: async ({}, use) => {
    const lockHandle = await playbackLock();
    const token = randomUUID();
    const directory = mkdtempSync(join(tmpdir(), "aperture-player-e2e-"));
    const fixture = {
      adminEmail: `e2e-player-admin-${token}@example.com`, adminPassword: `E2E-Player-${token}-123aA`,
      viewerEmail: `e2e-player-viewer-${token}@example.com`, viewerPassword: "E2E-Viewer-Playback-123aA",
      filename: `e2e-upload-player-${token}.mp4`, path: join(directory, "source.mp4"),
      slug: `e2e-studio-draft-playback-${token}`, title: `E2E Playback ${token.slice(0, 8)}`,
    };
    const subtitlePath = join(directory, "captions.srt");
    const secondSubtitlePath = join(directory, "captions-fr.srt");
    writeFileSync(subtitlePath, "1\n00:00:00,000 --> 00:00:03,000\nThe lighthouse signal begins.\n\n2\n00:00:07,000 --> 00:00:10,000\nThe harbor answers the signal.\n");
    writeFileSync(secondSubtitlePath, "1\n00:00:00,000 --> 00:00:03,000\nLe signal du phare commence.\n\n2\n00:00:07,000 --> 00:00:10,000\nLe port répond au signal.\n");
    execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24", "-f", "lavfi", "-i", "sine=frequency=659:sample_rate=48000", "-i", subtitlePath, "-i", secondSubtitlePath, "-t", "12", "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map", "3:s", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=fra", fixture.path]);
    helper("e2e_admin.py", { action: "create", email: fixture.adminEmail, password: fixture.adminPassword });
    try { await use(fixture); }
    finally {
      helper("e2e_upload.py", { action: "delete", filename: fixture.filename });
      helper("e2e_catalog.py", { action: "delete_prefix", slug_prefix: fixture.slug });
      helper("e2e_user.py", { email: fixture.viewerEmail });
      helper("e2e_admin.py", { action: "delete", email: fixture.adminEmail, password: fixture.adminPassword });
      rmSync(directory, { recursive: true, force: true });
      closeSync(lockHandle);
      unlinkSync(playbackLockPath);
    }
  },
});

test.setTimeout(360_000);

test("viewer seeks, leaves, and resumes an adaptive stream with profile progress", async ({ page, browser, playbackFixture }, testInfo) => {
  const runtime = runtimeFailures(page, testInfo.project.name);
  await page.goto("/studio/login");
  await page.getByLabel("Administrator email").fill(playbackFixture.adminEmail);
  await page.getByLabel("Password").fill(playbackFixture.adminPassword);
  await page.getByRole("button", { name: "Enter Studio" }).click();
  await expect(page).toHaveURL(/\/studio$/);

  await page.goto("/studio/movies/new");
  await page.getByLabel("Title *").fill(playbackFixture.title);
  await page.getByLabel("URL slug *").fill(playbackFixture.slug);
  await page.getByLabel("Runtime (minutes) *").fill("1");
  await page.getByLabel("Short description *").fill("A browser-driven adaptive playback fixture.");
  await page.getByLabel("Full synopsis *").fill("Original test metadata for playback and resume acceptance.");
  await page.getByLabel("Speculative Drama").check();
  await page.getByRole("button", { name: "Create draft movie" }).click();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect.poll(async () => (await page.request.get(`${apiOrigin}/catalog/movies/${playbackFixture.slug}`)).status()).toBe(200);
  const publishedMovieResponse = await page.request.get(`${apiOrigin}/catalog/movies/${playbackFixture.slug}`);
  const movieId = (await publishedMovieResponse.json() as { id: string }).id;
  const fixtureDirectorResponse = await page.request.post(`${apiOrigin}/admin/catalog/named/people`, { data: { name: "Fixture Director", slug: `${playbackFixture.slug}-director` } });
  expect(fixtureDirectorResponse.ok()).toBeTruthy();
  const fixtureCreditResponse = await page.request.post(`${apiOrigin}/admin/catalog/credits`, { data: { movie_id: movieId, person_id: (await fixtureDirectorResponse.json()).id, role: "director", billing_order: 0 } });
  expect(fixtureCreditResponse.ok()).toBeTruthy();
  const theatricalEditionResponse = await page.request.post(`${apiOrigin}/admin/catalog/editions`, { data: { movie_id: movieId, name: "Original theatrical presentation", runtime_minutes: 1, notes: "Verified browser-fixture presentation.", is_default: true, intended_presentation: true, aspect_ratio: "2.39:1", frame_rate: 24, presentation_format: "Original theatrical framing", capture_format: "Generated digital test master", audio_format: "Stereo", original_language_code: "en", restoration_info: "No restoration applied.", source_info: "Original project-owned browser fixture." } });
  const extendedEditionResponse = await page.request.post(`${apiOrigin}/admin/catalog/editions`, { data: { movie_id: movieId, name: "Extended comparison cut", runtime_minutes: 2, notes: "Comparison metadata only." } });
  expect(theatricalEditionResponse.ok()).toBeTruthy(); expect(extendedEditionResponse.ok()).toBeTruthy();
  const editionDifferenceResponse = await page.request.post(`${apiOrigin}/admin/catalog/edition-differences`, { data: { source_edition_id: (await theatricalEditionResponse.json()).id, target_edition_id: (await extendedEditionResponse.json()).id, kind: "editorial", description: "The comparison cut includes a verified alternate ending card.", source_note: "Original browser fixture comparison.", manually_verified: true } });
  expect(editionDifferenceResponse.ok()).toBeTruthy();

  await page.goto("/studio/uploads");
  const fileInput = page.getByLabel(/Choose a permitted source file/);
  await expect(fileInput).toBeEnabled();
  await fileInput.setInputFiles({ name: playbackFixture.filename, mimeType: "video/mp4", buffer: readFileSync(playbackFixture.path) });
  await page.getByRole("button", { name: "Start secure upload" }).click();
  const uploadRow = page.locator(".upload-list li").filter({ hasText: playbackFixture.filename });
  await expect(uploadRow.getByText("completed", { exact: true })).toBeVisible({ timeout: 30_000 });
  await uploadRow.getByRole("button", { name: "Queue processing" }).click();
  await expect(page.getByText("Processing job queued. Track it in Processing.")).toBeVisible();
  await page.goto("/studio/processing");
  const card = page.locator("article").filter({ hasText: playbackFixture.filename });
  await expect(card.locator(".catalog-badge", { hasText: "ready" })).toBeVisible({ timeout: 45_000 });
  await expect(card.getByRole("option", { name: `Movie · ${playbackFixture.title}` })).toBeAttached();
  const assignment = card.locator("form");
  await assignment.getByLabel("Playback title").selectOption({ label: `Movie · ${playbackFixture.title}` });
  await assignment.getByLabel("Intro start").fill("0");
  await assignment.getByLabel("Intro end").fill("2");
  await assignment.getByLabel("Credits start").fill("10");
  await assignment.getByRole("button", { name: "Assign playback" }).click();
  await expect(card.getByText("Assigned for customer playback")).toBeVisible();

  await page.goto("/studio/scenes").catch(async (error: Error) => {
    if (!error.message.includes("ERR_ABORTED")) throw error;
    await page.goto("/studio/scenes");
  });
  const scenePlaybackSelect = page.getByLabel("Playback title");
  const scenePlaybackValue = await scenePlaybackSelect.locator("option").filter({ hasText: playbackFixture.title }).getAttribute("value");
  expect(scenePlaybackValue).not.toBeNull();
  await scenePlaybackSelect.selectOption(scenePlaybackValue!);
  await page.getByLabel("Version notes").fill("Browser-verified manual scene evidence");
  await page.getByRole("button", { name: "Create evidence version" }).click();
  await expect(page.getByText("Version created")).toBeVisible();
  let sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await expect(sceneCard.getByText("At least one provenance source is required.")).toBeVisible();
  let sourceForm = sceneCard.locator("form").filter({ has: page.getByRole("button", { name: "Add provenance" }) });
  const extractedEvidence = await sourceForm.locator("datalist option").first().getAttribute("value");
  expect(extractedEvidence).not.toBeNull();
  await sourceForm.getByLabel("Kind").selectOption("subtitle");
  await sourceForm.getByLabel("Label").fill("Licensed embedded browser captions");
  await sourceForm.getByLabel("Source URI").fill(extractedEvidence!);
  await sourceForm.getByLabel("License basis").fill("Original browser-test captions owned by the project");
  await sourceForm.getByRole("button", { name: "Add provenance" }).click();
  sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await expect(sceneCard.getByRole("option", { name: "Licensed embedded browser captions" })).toBeAttached();
  sourceForm = sceneCard.locator("form").filter({ has: page.getByRole("button", { name: "Add provenance" }) });
  await sourceForm.getByLabel("Label").fill("Original browser fixture evidence");
  await sourceForm.getByLabel("License basis").fill("Original test metadata owned by the project");
  await sourceForm.getByRole("button", { name: "Add provenance" }).click();
  sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await expect(sceneCard.getByRole("option", { name: "Original browser fixture evidence" })).toBeAttached();
  const sceneForm = sceneCard.locator("form").filter({ has: page.getByRole("button", { name: "Add scene" }) });
  await sceneForm.getByLabel("Start seconds").fill("0");
  await sceneForm.getByLabel("End seconds").fill("12");
  await sceneForm.getByLabel("Title").fill("Signal across the harbor");
  await sceneForm.getByLabel("Summary").fill("An original manually verified test scene.");
  await sceneForm.getByLabel("Manually verified").check();
  await sceneForm.getByRole("button", { name: "Add scene" }).click();
  await expect(sceneCard.getByText("#1 · Signal across the harbor")).toBeVisible();
  const versionResponse = await page.request.get(`${apiOrigin}/admin/scenes`);
  expect(versionResponse.ok()).toBeTruthy();
  const versionDetail = (await versionResponse.json() as Array<{ version: { id: string }; playback_label: string; sources: Array<{ id: string; label: string }>; scenes: Array<{ id: string; title: string }> }>).find((item) => item.playback_label === playbackFixture.title)!;
  const manualSourceId = versionDetail.sources.find((source) => source.label === "Original browser fixture evidence")!.id;
  const sceneId = versionDetail.scenes.find((scene) => scene.title === "Signal across the harbor")!.id;
  const beaconResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/entities`, { data: { source_id: manualSourceId, entity_type: "place", name: "Beacon", canonical_key: "beacon", confidence: 1, reveal_seconds: 3 } });
  const signalResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/entities`, { data: { source_id: manualSourceId, entity_type: "object", name: "Signal", canonical_key: "signal", confidence: 1, reveal_seconds: 4 } });
  expect(beaconResponse.ok()).toBeTruthy(); expect(signalResponse.ok()).toBeTruthy();
  const relationshipResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/relationships`, { data: { source_id: manualSourceId, subject_entity_id: (await beaconResponse.json()).id, object_entity_id: (await signalResponse.json()).id, relationship: "emits", confidence: 1, reveal_seconds: 4 } });
  expect(relationshipResponse.ok()).toBeTruthy();
  const musicResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/music-cues`, { data: { source_id: manualSourceId, title: "Browser Signal Score", composer: "Fixture Composer", performer: "Fixture Ensemble", start_seconds: 5, end_seconds: 8 } });
  const filmmakingResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/production-notes`, { data: { source_id: manualSourceId, category: "camera", note: "The permitted test pattern uses a locked-off frame.", reveal_seconds: 6 } });
  expect(musicResponse.ok()).toBeTruthy(); expect(filmmakingResponse.ok()).toBeTruthy();
  const afterCreditsResponse = await page.request.post(`${apiOrigin}/admin/scenes/${versionDetail.version.id}/scenes/${sceneId}/production-notes`, { data: { source_id: manualSourceId, category: "ending_analysis", note: "The generated final frame resolves the fixture's opening visual pattern.", reveal_seconds: 8 } });
  expect(afterCreditsResponse.ok()).toBeTruthy();
  sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await expect(sceneCard.getByText("Structural validation is clean.")).toBeVisible();
  await sceneCard.getByRole("button", { name: "Queue enrichment" }).click();
  await expect.poll(async () => {
    const response = await page.request.get(`${apiOrigin}/admin/scenes`);
    const versions = await response.json() as Array<{ playback_label: string; jobs: Array<{ state: string }> }>;
    return versions.find((item) => item.playback_label === playbackFixture.title)?.jobs.at(-1)?.state;
  }).toBe("completed");
  await page.reload();
  sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await expect(sceneCard.getByText("completed", { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Scene query").fill("harbor");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(`${playbackFixture.title} · Signal across the harbor`)).toBeVisible();
  sceneCard = page.locator("article.scene-version-card").filter({ hasText: playbackFixture.title });
  await sceneCard.getByRole("button", { name: "Validate" }).click();
  await expect(sceneCard.getByText("validated", { exact: true })).toBeVisible();
  await sceneCard.getByRole("button", { name: "Publish version" }).click();
  await expect(sceneCard.getByText("published", { exact: true })).toBeVisible();
  await page.getByLabel("Movie scene").selectOption({ label: `${playbackFixture.title} · #1 Signal across the harbor` });
  await page.getByLabel("Reveal timestamp (seconds)").fill("4");
  await page.getByLabel("Alt text").fill("A permitted still of the generated test pattern");
  await page.getByLabel("Rights / permission basis").fill("Original generated browser fixture owned by the project");
  await page.getByRole("button", { name: "Permit still for protected gallery" }).click();
  await page.screenshot({ path: testInfo.outputPath("studio-scene-data-published.png"), fullPage: true });
  const collectionSlug = `${playbackFixture.slug}-essentials`;
  const journeySlug = `${playbackFixture.slug}-journey`;
  const collectionResponse = await page.request.post(`${apiOrigin}/admin/curation/collections`, { data: { slug: collectionSlug, title: "Fixture essentials", description: "A verified ordered browser collection.", kind: "themed", status: "published", items: [{ movie_id: movieId, note: "Begin with the signal." }] } });
  const journeyResponse = await page.request.post(`${apiOrigin}/admin/curation/journeys`, { data: { slug: journeySlug, title: "Fixture film journey", description: "A guided browser-test journey.", status: "published", chapters: [{ title: "Signals", introduction: "Read the pattern before watching.", items: [{ movie_id: movieId, note: "The opening chapter." }] }] } });
  expect(collectionResponse.ok()).toBeTruthy(); expect(journeyResponse.ok()).toBeTruthy();
  await page.goto("/studio/curation");
  await expect(page.getByRole("heading", { name: "Collections & Film Journeys" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Fixture essentials" }).first()).toBeAttached();
  await expect(page.getByRole("option", { name: "Fixture film journey" }).first()).toBeAttached();
  await page.screenshot({ path: testInfo.outputPath("studio-curation-editor.png"), fullPage: true });

  await page.goto("/register");
  await page.getByLabel("Your profile name").fill("Playback Viewer");
  await page.getByLabel("Email").fill(playbackFixture.viewerEmail);
  await page.getByLabel("Password").fill(playbackFixture.viewerPassword);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  await page.goto("/account");
  await page.getByLabel("Preferred subtitles").selectOption("en");
  await page.getByLabel("Second subtitle").selectOption("fr");
  await page.getByLabel("Caption size").selectOption("large");
  await page.getByLabel("Caption background").selectOption("solid");
  await page.getByLabel("Caption position").selectOption("top");
  await page.getByLabel("Enable subtitles by default").check();
  await page.getByRole("button", { name: "Save language preferences" }).click();
  await page.getByLabel("Share optional usage and playback-quality analytics").check();
  await page.getByRole("button", { name: "Save privacy choices" }).click();
  await expect(page.getByText("Last changed", { exact: false })).toBeVisible();
  await page.goto(`/movies/${playbackFixture.slug}`);
  await expect(page.getByRole("heading", { name: `The universe around ${playbackFixture.title}` })).toBeVisible();
  await page.getByRole("link", { name: /Fixture Director/ }).click();
  await expect(page).toHaveURL(new RegExp(`/people/${playbackFixture.slug}-director$`));
  await expect(page.getByRole("heading", { name: "Fixture Director" })).toBeVisible();
  await expect(page.getByText(playbackFixture.title, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("credits-explorer-person.png"), fullPage: true });
  await page.goBack();
  await page.getByRole("button", { name: "＋ My List" }).click();
  await expect(page.getByRole("button", { name: "✓ In My List" })).toBeVisible();
  await page.goto("/my-list");
  await expect(page.getByRole("heading", { level: 1, name: "My List", exact: true })).toBeVisible();
  await expect(page.getByText(playbackFixture.title, { exact: true })).toBeVisible();
  await page.goto(`/movies/${playbackFixture.slug}`);
  await page.getByRole("link", { name: "Play", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/watch/movies/${playbackFixture.slug}$`));
  const video = page.locator("video");
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => ({ ready: element.readyState, duration: element.duration }))).toMatchObject({ ready: 4 });
  await expect(page.getByLabel("Quality").locator("option")).toHaveCount(4);
  await expect(page.getByLabel("Quality")).toContainText("360p");
  await expect(page.getByLabel("Quality")).toContainText("480p");
  await expect(page.getByLabel("Quality")).toContainText("720p");
  const competingDevice = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL,
    ignoreHTTPSErrors: true,
    userAgent: "Aperture competing playback device",
  });
  const competingPage = await competingDevice.newPage();
  await competingPage.goto("/login");
  await competingPage.getByLabel("Email").fill(playbackFixture.viewerEmail);
  await competingPage.getByLabel("Password").fill(playbackFixture.viewerPassword);
  await competingPage.getByRole("button", { name: "Continue" }).click();
  await expect(competingPage).toHaveURL(/\/profiles$/);
  await competingPage.goto(`/watch/movies/${playbackFixture.slug}`);
  await expect(competingPage.getByRole("heading", { name: "Your account is already streaming." })).toBeVisible();
  await expect(competingPage.getByText(/Inactive device slots expire automatically/)).toBeVisible();
  await competingDevice.close();
  await expect(page.locator(".player-shell")).toHaveClass(/captions-large/);
  await expect(page.locator(".player-shell")).toHaveClass(/captions-solid/);
  await expect(page.locator(".player-shell")).toHaveClass(/captions-top/);
  await expect(page.getByLabel("Subtitles", { exact: true }).locator("option")).toHaveCount(3);
  await expect(page.getByLabel("Second subtitles")).toBeEnabled();
  await page.getByLabel("Second subtitles").selectOption("1");
  await expect(page.getByLabel("Second subtitles")).toHaveValue("1");
  await page.getByLabel("Quality").selectOption({ label: "480p" });
  await expect(page.getByLabel("Quality")).toHaveValue("1");
  await page.getByLabel("Quality").selectOption({ label: "Auto" });
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeGreaterThan(0.2);
  await expect(page.getByRole("button", { name: "Skip intro" })).toBeVisible();
  await page.getByLabel("Seek").fill("6");
  await page.locator(".player-top strong").click();
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  await expect(page.getByText("Progress saved")).toBeVisible();
  await page.getByRole("button", { name: "SceneLens ready" }).click();
  const lens = page.getByLabel("SceneLens");
  await expect(lens.getByRole("heading", { name: "SceneLens" })).toBeVisible();
  await expect(lens.getByRole("button", { name: "Close SceneLens" })).toBeFocused();
  await expect(lens.getByText("#1 · Signal across the harbor")).toBeVisible();
  await expect(lens.getByText("The scene summary remains hidden until its approved reveal boundary.")).toBeVisible();
  const toolkit = lens.locator(".cinephile-toolkit");
  await expect(toolkit.getByRole("img", { name: "A permitted still of the generated test pattern" })).toBeVisible();
  await expect(toolkit.getByText(/Browser Signal Score/)).toBeVisible();
  await expect(toolkit.getByText("The permitted test pattern uses a locked-off frame.")).toBeVisible();
  await expect(toolkit.getByText("2.39:1")).toBeVisible();
  await expect(toolkit.getByText("Verified editorial comparisons unlock after this profile completes the title.")).toBeVisible();
  await toolkit.screenshot({ path: testInfo.outputPath("cinephile-toolkit.png") });
  await expect(lens.getByRole("img", { name: "Spoiler-safe relationship graph" })).toBeVisible();
  await lens.getByRole("button", { name: "Zoom relationship graph in" }).click();
  await expect(lens.getByText("125%")).toBeVisible();
  await lens.locator(".relationship-graph").screenshot({ path: testInfo.outputPath("relationship-graph.png") });
  await lens.getByText("Accessible relationship list").click();
  await expect(lens.getByText(/Beacon emits Signal · known at 0:04/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("scene-lens-context.png"), fullPage: true });
  await lens.getByRole("button", { name: "Who Was That?" }).click();
  await expect(lens.getByText("Not enough approved character evidence")).toBeVisible();
  await lens.getByRole("button", { name: "What Did I Miss? · last 30s" }).click();
  await expect(lens.getByText("No completed-scene recap yet")).toBeVisible();
  await expect(lens.getByText("Only completed scenes with approved summaries can be recapped.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("moment-tools-spoiler-safe.png"), fullPage: true });
  await lens.getByLabel("Your question").fill("What just happened?");
  await lens.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(lens.getByText("Not enough approved evidence")).toBeVisible();
  await expect(lens.getByText("Reliable information is not available from the approved scene evidence at this moment.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("ask-this-movie-grounded.png"), fullPage: true });
  await lens.getByLabel("Bookmark title").fill("Harbor signal");
  await lens.getByRole("button", { name: "Bookmark scene" }).click();
  await expect(lens.getByText(/Harbor signal · 0:0[56]/)).toBeVisible();
  await lens.getByLabel("Personal note").fill("Return to the beacon clue.");
  await lens.getByRole("button", { name: "Save note" }).click();
  await expect(lens.getByText(/Return to the beacon clue/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("scene-lens-spoiler-safe.png"), fullPage: true });
  await lens.getByRole("button", { name: "Close SceneLens" }).click();
  const saved = helper("e2e_playback.py", { email: playbackFixture.viewerEmail, slug: playbackFixture.slug });
  expect(saved.position_seconds).toBeGreaterThanOrEqual(5.5);
  await expect.poll(() => helper("e2e_playback.py", { email: playbackFixture.viewerEmail, slug: playbackFixture.slug }).analytics).toMatchObject({ play_start: 1, progress: 1, pause: 1, seek: 1, playback_startup: 1, quality_change: 2 });

  await page.goto(`/movies/${playbackFixture.slug}`);
  await page.getByRole("link", { name: "Play", exact: true }).click();
  await expect.poll(() => page.locator("video").evaluate((element: HTMLVideoElement) => element.currentTime)).toBeGreaterThanOrEqual(5.5);
  await page.screenshot({ path: testInfo.outputPath("adaptive-player-resumed.png"), fullPage: true });
  const completionPosition = await page.locator("video").evaluate((element: HTMLVideoElement) => Math.floor(element.duration * 0.95));
  await page.getByLabel("Seek").fill(String(completionPosition));
  await page.locator(".player-top strong").click();
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.keyboard.press("Space");
  await expect(page.getByText("Progress saved")).toBeVisible();
  await page.locator("video").evaluate((element: HTMLVideoElement) => {
    element.currentTime = element.duration;
    element.dispatchEvent(new Event("ended"));
  });
  await expect(page.getByRole("heading", { name: "After-Credits Room" })).toBeVisible();
  await expect(page.getByText("The generated final frame resolves the fixture's opening visual pattern.")).toBeVisible();
  await expect(page.getByText("Ratings and community discussion remain unavailable until moderation and abuse controls are enabled.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("after-credits-room.png"), fullPage: true });
  await page.getByRole("button", { name: "Close After-Credits Room" }).click();
  await page.goto(`/collections/${collectionSlug}`);
  await expect(page.getByRole("heading", { name: "Fixture essentials" })).toBeVisible();
  await expect(page.getByText("Begin with the signal.")).toBeVisible();
  await page.goto(`/journeys/${journeySlug}`);
  await expect(page.getByRole("heading", { name: "Fixture film journey" })).toBeVisible();
  await expect(page.getByText("Progress is private to this profile.")).toBeVisible();
  await page.getByRole("button", { name: "Mark complete" }).click();
  await expect(page.getByText("Journey complete")).toBeVisible();
  await expect(page.getByRole("button", { name: "Completed ✓" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("film-journey-complete.png"), fullPage: true });
  await page.goto("/passport");
  await expect(page.getByRole("heading", { name: "Cinema Passport" })).toBeVisible();
  await expect(page.getByText("Films watched").locator("..").getByText("1", { exact: true })).toBeVisible();
  await expect(page.getByText("First watch · Completed")).toBeVisible();
  await expect(page.getByText(playbackFixture.title, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("cinema-passport-completed.png"), fullPage: true });
  await page.goto("/studio/analytics");
  await expect(page.getByRole("heading", { name: "Analytics", exact: true })).toBeVisible();
  await expect(page.getByText(playbackFixture.title, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("play start", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Average startup", { exact: true })).toBeVisible();
  await expect(page.getByText("Fatal error rate", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("studio-analytics-playback.png"), fullPage: true });
  expect(runtime).toEqual([]);
});
