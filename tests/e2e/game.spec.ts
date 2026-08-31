import {
  expect,
  test,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";

const BALL_BEST_KEY = "signal-run-ball-best-v2";

const requestedBrowserExecutable = process.env.E2E_BROWSER_EXECUTABLE;
if (requestedBrowserExecutable) {
  test.use({ launchOptions: { executablePath: requestedBrowserExecutable } });
}

interface RuntimeMonitor {
  consoleErrors: string[];
  pageErrors: string[];
  requestFailures: string[];
  badResponses: string[];
}

function gameRoot(page: Page): Locator {
  return page.locator(
    '[data-mode][data-pace][data-assist][data-comfort]',
  );
}

function ballCanvas(page: Page): Locator {
  return page.getByRole("application", {
    name: "Signal Run luminous ball tunnel",
  });
}

function monitorRuntime(page: Page): RuntimeMonitor {
  const monitor: RuntimeMonitor = {
    consoleErrors: [],
    pageErrors: [],
    requestFailures: [],
    badResponses: [],
  };

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Chromium's generic resource line omits the URL. Request/response
    // listeners below retain the actionable URL and status and avoid falsely
    // attributing a late homepage image response to a recreated /game route.
    if (/^Failed to load resource:/i.test(message.text())) return;
    monitor.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => monitor.pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    const detail = request.failure()?.errorText ?? "unknown request failure";
    // Expected when a soft navigation replaces an in-flight route prefetch.
    if (/ERR_ABORTED|NS_BINDING_ABORTED|cancelled/i.test(detail)) return;
    monitor.requestFailures.push(`${request.method()} ${request.url()}: ${detail}`);
  });
  page.on("response", (response) => {
    if (response.status() < 400) return;
    try {
      if (new URL(response.url()).origin !== new URL(page.url()).origin) return;
    } catch {
      return;
    }
    monitor.badResponses.push(`${response.status()} ${response.url()}`);
  });

  return monitor;
}

function expectRuntimeClean(monitor: RuntimeMonitor): void {
  expect(monitor.consoleErrors, "console errors").toEqual([]);
  expect(monitor.pageErrors, "uncaught page errors").toEqual([]);
  expect(monitor.requestFailures, "failed requests").toEqual([]);
  expect(monitor.badResponses, "HTTP error responses").toEqual([]);
}

function projectIsTouch(testInfo: TestInfo): boolean {
  return testInfo.project.name === "mobile-chromium" ||
    testInfo.project.name === "tablet-chromium";
}

async function waitForBallGame(page: Page): Promise<Locator> {
  const play = page.getByRole("button", {
    name: "Play Signal Run",
    exact: true,
  });
  await expect(play).toBeEnabled({ timeout: 30_000 });

  const canvas = ballCanvas(page);
  await expect(canvas).toHaveCount(1);
  await expect(canvas).toHaveAttribute(
    "data-render-backend",
    /^(webgl|webgpu)$/,
  );
  await expect(canvas).toHaveAttribute(
    "data-physics-backend",
    /^(rapier|none)$/,
  );
  await expect(canvas).toHaveAttribute("data-player-avatar", "ball");
  await expect(canvas).toHaveAttribute(
    "data-quality-tier",
    /^(cinematic|balanced|performance)$/,
  );
  await expect.poll(
    async () => Number(await canvas.getAttribute("data-pixel-ratio")),
  ).toBeGreaterThan(0);
  return canvas;
}

async function openBallGame(page: Page): Promise<Locator> {
  const response = await page.goto("/game");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(/\/game\/?$/);
  return waitForBallGame(page);
}

async function startRun(page: Page): Promise<Locator> {
  const root = gameRoot(page);
  await page.getByRole("button", {
    name: "Play Signal Run",
    exact: true,
  }).click();
  await expect(root).toHaveAttribute("data-mode", "countdown");
  await expect(page.getByRole("region", { name: "Run starting" })).toBeVisible();
  await expect(ballCanvas(page)).toHaveAttribute("data-game-state", "countdown");
  await expect(root).toHaveAttribute("data-mode", "running", {
    timeout: 8_000,
  });
  await expect(ballCanvas(page)).toHaveAttribute("data-game-state", "running");
  return root;
}

async function expectPageFitsViewport(
  page: Page,
  viewport: { width: number; height: number },
): Promise<void> {
  await page.setViewportSize(viewport);
  const metrics = await page.evaluate(() => {
    const root = document.querySelector<HTMLElement>(
      '[data-mode][data-pace][data-assist][data-comfort]',
    );
    const bounds = root?.getBoundingClientRect();
    return {
      clientHeight: document.documentElement.clientHeight,
      clientWidth: document.documentElement.clientWidth,
      scrollHeight: document.documentElement.scrollHeight,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollHeight: document.body.scrollHeight,
      bodyScrollWidth: document.body.scrollWidth,
      root: bounds
        ? {
            left: bounds.left,
            top: bounds.top,
            right: bounds.right,
            bottom: bounds.bottom,
          }
        : null,
    };
  });

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.scrollHeight).toBeLessThanOrEqual(metrics.clientHeight + 1);
  expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.bodyScrollHeight).toBeLessThanOrEqual(metrics.clientHeight + 1);
  expect(metrics.root).not.toBeNull();
  expect(metrics.root?.left ?? -2).toBeGreaterThanOrEqual(-1);
  expect(metrics.root?.top ?? -2).toBeGreaterThanOrEqual(-1);
  expect(metrics.root?.right ?? viewport.width + 2).toBeLessThanOrEqual(
    viewport.width + 1,
  );
  expect(metrics.root?.bottom ?? viewport.height + 2).toBeLessThanOrEqual(
    viewport.height + 1,
  );
}

async function expectInsideViewport(page: Page, locator: Locator): Promise<void> {
  const box = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box?.x ?? -2).toBeGreaterThanOrEqual(-1);
  expect(box?.y ?? -2).toBeGreaterThanOrEqual(-1);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(
    (viewport?.width ?? 0) + 1,
  );
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(
    (viewport?.height ?? 0) + 1,
  );
}

async function expectUsableTargets(container: Locator): Promise<void> {
  const targets = await container.getByRole("button").evaluateAll((buttons) =>
    buttons.flatMap((button) => {
      const style = getComputedStyle(button);
      const bounds = button.getBoundingClientRect();
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        bounds.width <= 0 ||
        bounds.height <= 0
      ) {
        return [];
      }
      const center = document.elementFromPoint(
        bounds.left + bounds.width / 2,
        bounds.top + bounds.height / 2,
      );
      return [{
        name: button.getAttribute("aria-label") ?? button.textContent?.trim(),
        width: bounds.width,
        height: bounds.height,
        inViewport:
          bounds.left >= -1 &&
          bounds.top >= -1 &&
          bounds.right <= window.innerWidth + 1 &&
          bounds.bottom <= window.innerHeight + 1,
        receivesInput: button === center || button.contains(center),
      }];
    }),
  );

  expect(targets.length).toBeGreaterThan(0);
  for (const target of targets) {
    expect(target.width, `${target.name} width`).toBeGreaterThanOrEqual(48);
    expect(target.height, `${target.name} height`).toBeGreaterThanOrEqual(48);
    expect(target.inViewport, `${target.name} is inside the viewport`).toBe(true);
    expect(target.receivesInput, `${target.name} receives input`).toBe(true);
  }
}

async function installControllableAnimationTimeline(
  page: Page,
  initialStepMilliseconds = 16,
): Promise<void> {
  await page.addInitScript((initialStep) => {
    const state = window as unknown as { __ballRafStepMilliseconds: number };
    const nativeRequestAnimationFrame = window.requestAnimationFrame.bind(window);
    let syntheticTimestamp: number | null = null;
    state.__ballRafStepMilliseconds = initialStep;
    window.requestAnimationFrame = (callback: FrameRequestCallback) =>
      nativeRequestAnimationFrame((actualTimestamp) => {
        syntheticTimestamp = syntheticTimestamp === null
          ? actualTimestamp
          : syntheticTimestamp + state.__ballRafStepMilliseconds;
        callback(syntheticTimestamp);
      });
  }, initialStepMilliseconds);
}

async function setAnimationTimelineStep(
  page: Page,
  stepMilliseconds: number,
): Promise<void> {
  await page.evaluate((step) => {
    (window as unknown as { __ballRafStepMilliseconds: number })
      .__ballRafStepMilliseconds = step;
  }, stepMilliseconds);
}

async function trustedTouchGesture(
  page: Page,
  points: readonly { x: number; y: number }[],
  cancelled = false,
): Promise<void> {
  expect(points.length).toBeGreaterThan(0);
  const session = await page.context().newCDPSession(page);
  const touchPoint = (point: { x: number; y: number }) => ({
    id: 73,
    x: point.x,
    y: point.y,
    radiusX: 1,
    radiusY: 1,
    force: 1,
  });
  try {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [touchPoint(points[0])],
    });
    for (const point of points.slice(1)) {
      await session.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [touchPoint(point)],
      });
    }
    await session.send("Input.dispatchTouchEvent", {
      type: cancelled ? "touchCancel" : "touchEnd",
      touchPoints: [],
    });
  } finally {
    await session.detach();
  }
}

async function canvasClearPoint(canvas: Locator): Promise<{ x: number; y: number }> {
  const point = await canvas.evaluate((surface) => {
    const bounds = surface.getBoundingClientRect();
    const candidates = [0.68, 0.58, 0.78, 0.48];
    for (const vertical of candidates) {
      const x = bounds.left + bounds.width * 0.5;
      const y = bounds.top + bounds.height * vertical;
      if (document.elementFromPoint(x, y) === surface) return { x, y };
    }
    return null;
  });
  expect(point, "an unobstructed canvas touch point").not.toBeNull();
  return point!;
}

async function installDeterministicRunSeed(page: Page): Promise<void> {
  await page.evaluate(() => {
    Math.random = () => 0;
    Date.now = () => 1_700_000_000_000;
    Object.defineProperty(globalThis.crypto, "getRandomValues", {
      configurable: true,
      value: <T extends ArrayBufferView | null>(array: T): T => {
        if (array) {
          new Uint8Array(
            array.buffer,
            array.byteOffset,
            array.byteLength,
          ).fill(0);
        }
        return array;
      },
    });
  });
}

async function installTelegraphAutopilot(page: Page): Promise<void> {
  await page.evaluate(() => {
    const state = window as unknown as {
      __ballAutopilotInterval?: number;
    };
    if (state.__ballAutopilotInterval !== undefined) {
      window.clearInterval(state.__ballAutopilotInterval);
    }

    let lastObstacle = "";
    let pointerId = 200;
    state.__ballAutopilotInterval = window.setInterval(() => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        'canvas[data-player-avatar="ball"]',
      );
      if (!canvas) return;
      const gameState = canvas.dataset.gameState;
      if (gameState === "crashed" || gameState === "extracted") {
        if (state.__ballAutopilotInterval !== undefined) {
          window.clearInterval(state.__ballAutopilotInterval);
          state.__ballAutopilotInterval = undefined;
        }
        return;
      }
      if (gameState !== "running") return;

      const obstacle = canvas.dataset.telegraphObstacle ?? "";
      if (!obstacle || obstacle === lastObstacle) return;
      const ballX = Number(canvas.dataset.ballX);
      const ballY = Number(canvas.dataset.ballY);
      const safeX = Number(canvas.dataset.telegraphSafeX);
      const safeY = Number(canvas.dataset.telegraphSafeY);
      if (![ballX, ballY, safeX, safeY].every(Number.isFinite)) return;

      lastObstacle = obstacle;
      pointerId += 1;
      const bounds = canvas.getBoundingClientRect();
      const originX = bounds.left + bounds.width * 0.5;
      const originY = bounds.top + bounds.height * 0.62;
      const common = {
        pointerId,
        pointerType: "touch",
        isPrimary: true,
        button: 0,
      };
      canvas.dispatchEvent(new PointerEvent("pointerdown", {
        ...common,
        buttons: 1,
        clientX: originX,
        clientY: originY,
        bubbles: true,
      }));
      canvas.dispatchEvent(new PointerEvent("pointermove", {
        ...common,
        buttons: 1,
        clientX: originX + (safeX - ballX) * 30,
        clientY: originY - (safeY - ballY) * 30,
        bubbles: true,
      }));
      canvas.dispatchEvent(new PointerEvent("pointerup", {
        ...common,
        buttons: 0,
        clientX: originX + (safeX - ballX) * 30,
        clientY: originY - (safeY - ballY) * 30,
        bubbles: true,
      }));
    }, 12);
  });
}

test.describe("Signal Run ball game", () => {
  test("loads publicly with one Babylon ball canvas and no Loom UI", async ({
    page,
  }) => {
    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    const root = gameRoot(page);

    await expect(root).toHaveAttribute("data-mode", "idle");
    await expect(canvas).toHaveAttribute("aria-disabled", "true");
    await expect(canvas).toHaveAttribute("data-ball-radius", /^0\.9/);
    await expect(canvas).toHaveAttribute("data-render-profile", /^(desktop|touch)$/);
    await expect(page.locator("canvas")).toHaveCount(1);
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(1);
    await expect(page.locator("canvas.signal-loom__canvas")).toHaveCount(0);
    await expect(page.locator("html")).toHaveClass(/signal-run-ball-open/);
    await expect(page.locator("body")).toHaveClass(/signal-run-ball-open/);

    const visibleText = (await root.innerText()).replace(/\s+/g, " ");
    expect(visibleText).toContain("Signal Run");
    expect(visibleText).toContain("Move the ball");
    expect(visibleText).not.toMatch(
      /Signal Loom|Needle|Echo|Thread|Reel|Ember|Cobalt|Resonance|Iris|six-minute contract/i,
    );
    await expect(page.getByRole("button", { name: /phase|reel|resonance/i }))
      .toHaveCount(0);
    expectRuntimeClean(runtime);
  });

  test("keeps the intro, controls, and primary action inside every viewport", async ({
    page,
  }, testInfo) => {
    const runtime = monitorRuntime(page);
    await openBallGame(page);

    const viewports = projectIsTouch(testInfo)
      ? [
          { width: 320, height: 568 },
          { width: 568, height: 320 },
          { width: 915, height: 412 },
        ]
      : [{ width: 1280, height: 720 }];

    for (const viewport of viewports) {
      await expectPageFitsViewport(page, viewport);
      const intro = page.getByRole("main");
      const play = page.getByRole("button", { name: "Play Signal Run" });
      const exit = page.getByRole("button", { name: "Exit game" });
      const options = page.getByLabel("Game options");
      await expect(intro).toBeVisible();
      await expect(play).toBeVisible();
      await expectInsideViewport(page, play);
      await expectInsideViewport(page, exit);
      await expectInsideViewport(page, options);
      await expectUsableTargets(gameRoot(page));
    }

    if (projectIsTouch(testInfo)) {
      await expect(page.getByText("Drag anywhere to move")).toBeVisible();
      await expect(page.getByText("WASD or arrow keys to move")).toBeHidden();
    } else {
      await expect(page.getByText("WASD or arrow keys to move")).toBeVisible();
    }
    expectRuntimeClean(runtime);
  });

  test("stages keyboard steering, pauses without drifting, resumes, and restarts", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-chromium",
      "Authoritative keyboard lifecycle coverage runs once in Chromium.",
    );

    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    const root = gameRoot(page);

    await page.getByRole("button", { name: "Play Signal Run" }).click();
    await expect(root).toHaveAttribute("data-mode", "countdown");
    await page.keyboard.down("ArrowRight");
    await expect(page.getByRole("region", { name: "Run starting" }))
      .toContainText("Right ready");
    await expect(root).toHaveAttribute("data-mode", "running", {
      timeout: 8_000,
    });
    await expect.poll(
      async () => Number(await canvas.getAttribute("data-ball-x")),
      { timeout: 5_000 },
    ).toBeGreaterThan(0.3);
    await page.keyboard.up("ArrowRight");

    const overdriveCharge = page.getByLabel(/Overdrive charge \d of 4/);
    await expect(overdriveCharge).toBeVisible();
    await expect(overdriveCharge.locator("i")).toHaveCount(4);

    await expect.poll(async () => {
      const label = await page.getByLabel(/^Score /).getAttribute("aria-label");
      return Number(label?.replace(/\D/g, "") ?? 0);
    }).toBeGreaterThan(0);

    await page.getByRole("button", { name: "Pause game" }).click();
    await expect(root).toHaveAttribute("data-mode", "paused");
    const dialog = page.getByRole("dialog", { name: "Take a breath." });
    await expect(dialog).toBeVisible();
    await expect(canvas).toHaveAttribute("data-game-state", "paused");
    const frozen = await canvas.evaluate((surface) => ({
      x: surface.dataset.ballX,
      y: surface.dataset.ballY,
    }));
    const pausedReadout = (await page.getByLabel("Current run").innerText())
      .replace(/\s+/g, " ");
    await page.waitForTimeout(550);
    expect(await canvas.evaluate((surface) => ({
      x: surface.dataset.ballX,
      y: surface.dataset.ballY,
    }))).toEqual(frozen);
    expect((await page.getByLabel("Current run").innerText()).replace(/\s+/g, " "))
      .toBe(pausedReadout);

    await page.getByRole("button", { name: "Resume game" }).click();
    await expect(root).toHaveAttribute("data-mode", "resuming");
    await page.keyboard.down("ArrowLeft");
    await expect(page.getByRole("region", { name: "Run starting" }))
      .toContainText("Left ready");
    await expect(root).toHaveAttribute("data-mode", "running", {
      timeout: 5_000,
    });
    await page.keyboard.up("ArrowLeft");

    await page.getByRole("button", { name: "Pause game" }).click();
    await page.getByRole("button", { name: "Restart run" }).click();
    await expect(root).toHaveAttribute("data-mode", "countdown");
    await expect(page.getByLabel("Score 0")).toBeVisible();
    await expect(canvas).toHaveAttribute("data-ball-x", "0.000");
    await expect(canvas).toHaveAttribute("data-ball-y", "0.000");
    await expect(root).toHaveAttribute("data-mode", "running", {
      timeout: 8_000,
    });
    expectRuntimeClean(runtime);
  });

  test("persists a completed crash score as the personal best", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-chromium",
      "The accelerated crash and storage seam only needs one browser engine.",
    );
    test.setTimeout(60_000);

    await installControllableAnimationTimeline(page);
    const runtime = monitorRuntime(page);
    await openBallGame(page);
    await page.evaluate((key) => localStorage.removeItem(key), BALL_BEST_KEY);
    await setAnimationTimelineStep(page, 250);
    await startRun(page);

    const result = page.getByRole("dialog");
    await expect(result).toBeVisible({ timeout: 30_000 });
    await expect(result).toContainText(/Run complete|New personal best/i);
    await expect(result).toContainText(/Score/);
    await expect(result).toContainText(/Best/);
    const stored = await page.evaluate(
      (key) => Number(localStorage.getItem(key) ?? 0),
      BALL_BEST_KEY,
    );
    expect(stored).toBeGreaterThan(0);
    const bestText = await result.locator("dt", { hasText: "Best" })
      .locator("xpath=following-sibling::dd").innerText();
    expect(Number(bestText.replace(/\D/g, ""))).toBe(stored);

    await page.reload();
    await waitForBallGame(page);
    expect(await page.evaluate(
      (key) => Number(localStorage.getItem(key) ?? 0),
      BALL_BEST_KEY,
    )).toBe(stored);
    expectRuntimeClean(runtime);
  });

  test("shows the final rush, extracts exactly, persists the win, and resets replay", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-chromium",
      "The deterministic 105-second extraction contract only needs one browser engine.",
    );
    test.setTimeout(90_000);

    await installControllableAnimationTimeline(page);
    // Keep the real Babylon render surface tiny while fast-forwarding. The
    // simulation still receives every authoritative fixed step, but the E2E
    // does not spend most of its wall time shading a large software canvas.
    await page.setViewportSize({ width: 400, height: 240 });
    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    const root = gameRoot(page);
    await page.evaluate((key) => localStorage.removeItem(key), BALL_BEST_KEY);
    await page.getByRole("button", { name: "Assist mode off" }).click();
    await expect(root).toHaveAttribute("data-assist", "true");
    await installDeterministicRunSeed(page);
    await installTelegraphAutopilot(page);

    await startRun(page);
    const finishClock = page.locator(
      'time[aria-label$="seconds to finish"]',
    );
    await expect(finishClock).toHaveAttribute(
      "aria-label",
      "105 seconds to finish",
    );
    await expect(finishClock).toContainText("Finish");
    const overdriveCharge = page.getByLabel(/Overdrive charge \d of 4/);
    await expect(overdriveCharge.locator("i")).toHaveCount(4);
    await expect(canvas).toHaveAttribute("data-telegraph-kind", "none");

    await setAnimationTimelineStep(page, 250);
    await expect(canvas).toHaveAttribute("data-telegraph-kind", /^(gate|block)$/, {
      timeout: 10_000,
    });
    const firstTelegraph = await canvas.getAttribute("data-telegraph-obstacle");
    expect(firstTelegraph).toBeTruthy();
    await expect.poll(
      async () => Number(await canvas.getAttribute("data-telegraph-tti")),
    ).toBeGreaterThan(0);
    await expect.poll(
      async () => Number(await canvas.getAttribute("data-telegraph-strength")),
    ).toBeGreaterThan(0);
    for (const attribute of [
      "data-telegraph-safe-x",
      "data-telegraph-safe-y",
    ]) {
      expect(Number.isFinite(Number(await canvas.getAttribute(attribute))), attribute)
        .toBe(true);
    }
    await expect.poll(
      async () => await canvas.getAttribute("data-telegraph-obstacle"),
      { timeout: 10_000 },
    ).not.toBe(firstTelegraph);

    await expect.poll(async () => {
      const label = await finishClock.getAttribute("aria-label");
      return Number(label?.match(/^([0-9]+) seconds? to finish$/)?.[1] ?? 999);
    }, { timeout: 60_000 }).toBeLessThanOrEqual(15);
    await expect(finishClock).toBeVisible();
    await expect(finishClock).toHaveAttribute("data-urgent", "true");

    await expect(root).toHaveAttribute("data-mode", "extracted", {
      timeout: 30_000,
    });
    await expect(canvas).toHaveAttribute("data-game-state", "extracted");
    await expect(canvas).toHaveAttribute("data-simulation-status", "extracted");
    await expect(canvas).toHaveAttribute("aria-disabled", "true");
    const result = page.getByRole("dialog", { name: "You made it through." });
    await expect(result).toBeVisible();
    await expect(result.locator('[data-result="extracted"]')).toHaveCount(1);
    await expect(result).toContainText("Run cleared / New personal best");
    await expect(result).toContainText(
      "You held the line from calm launch to the final rush.",
    );
    await expect(page.getByRole("status")).toHaveText(/^Run cleared\. Score [\d,]+\.$/);

    const stored = await page.evaluate(
      (key) => Number(localStorage.getItem(key) ?? 0),
      BALL_BEST_KEY,
    );
    expect(stored).toBeGreaterThan(0);
    const bestText = await result.locator("dt", { hasText: "Best" })
      .locator("xpath=following-sibling::dd").innerText();
    expect(Number(bestText.replace(/\D/g, ""))).toBe(stored);
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(1);

    await setAnimationTimelineStep(page, 16);
    await page.getByRole("button", { name: "Run it again" }).click();
    await expect(root).toHaveAttribute("data-mode", "countdown");
    await expect(page.getByLabel("Score 0")).toBeVisible();
    await expect(finishClock).toHaveAttribute(
      "aria-label",
      "105 seconds to finish",
    );
    await expect(canvas).toHaveAttribute("data-game-state", "countdown");
    await expect(canvas).toHaveAttribute("data-simulation-status", "running");
    await expect(canvas).toHaveAttribute("data-ball-x", "0.000");
    await expect(canvas).toHaveAttribute("data-ball-y", "0.000");
    await expect(canvas).toHaveAttribute("data-telegraph-kind", "none");
    await expect(canvas).toHaveAttribute("data-telegraph-obstacle", "");
    await expect(canvas).toHaveAttribute("data-telegraph-strength", "0.000");
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(1);
    await expect(root).toHaveAttribute("data-mode", "running", {
      timeout: 8_000,
    });
    expect(await page.evaluate(
      (key) => Number(localStorage.getItem(key) ?? 0),
      BALL_BEST_KEY,
    )).toBe(stored);
    expectRuntimeClean(runtime);
  });

  test("disposes the canvas and page lock across soft navigation", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-chromium",
      "The client-navigation disposal seam only needs one browser engine.",
    );

    const runtime = monitorRuntime(page);
    await openBallGame(page);
    await expect(page.locator("canvas")).toHaveCount(1);
    expectRuntimeClean(runtime);

    await page.getByRole("button", { name: "Exit game" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(0);
    await expect(page.locator("html")).not.toHaveClass(/signal-run-ball-open/);
    await expect(page.locator("body")).not.toHaveClass(/signal-run-ball-open/);

    // Homepage requests are outside this route's runtime contract. Start a
    // fresh failure window before recreating the game engine via history.
    runtime.consoleErrors.length = 0;
    runtime.pageErrors.length = 0;
    runtime.requestFailures.length = 0;
    runtime.badResponses.length = 0;

    await page.goBack();
    await expect(page).toHaveURL(/\/game\/?$/);
    await waitForBallGame(page);
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(1);
    expectRuntimeClean(runtime);

    await page.getByRole("button", { name: "Exit game" }).click();
    await expect(page.locator("canvas.signal-run__canvas")).toHaveCount(0);
  });

  test("uses target-relative touch drag without inventing a tap action", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "mobile-chromium",
      "Trusted touch input is covered by mobile Chromium.",
    );

    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    const root = await startRun(page);
    const start = await canvasClearPoint(canvas);
    const initialX = Number(await canvas.getAttribute("data-ball-x"));

    await trustedTouchGesture(page, [
      start,
      { x: start.x + 42, y: start.y },
      { x: start.x + 104, y: start.y },
    ]);
    await expect.poll(
      async () => Number(await canvas.getAttribute("data-ball-x")),
      { timeout: 5_000 },
    ).toBeGreaterThan(initialX + 0.45);

    const stableMode = await root.getAttribute("data-mode");
    const stableAssist = await root.getAttribute("data-assist");
    const stableComfort = await root.getAttribute("data-comfort");
    const beforeMicroDrag = Number(await canvas.getAttribute("data-ball-x"));
    const secondStart = await canvasClearPoint(canvas);
    await trustedTouchGesture(page, [
      secondStart,
      { x: secondStart.x + 3, y: secondStart.y + 2 },
    ]);
    await page.waitForTimeout(350);
    expect(await root.getAttribute("data-mode")).toBe(stableMode);
    expect(await root.getAttribute("data-assist")).toBe(stableAssist);
    expect(await root.getAttribute("data-comfort")).toBe(stableComfort);
    expect(Math.abs(
      Number(await canvas.getAttribute("data-ball-x")) - beforeMicroDrag,
    )).toBeLessThan(1);
    await expect(page.getByRole("button", { name: /phase|reel|resonance/i }))
      .toHaveCount(0);
    expectRuntimeClean(runtime);
  });

  test("releases a cancelled pointer and ignores its later movement", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "mobile-chromium",
      "Pointer cancellation is covered by mobile Chromium.",
    );

    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    await startRun(page);
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    const x = (bounds?.x ?? 0) + (bounds?.width ?? 0) * 0.5;
    const y = (bounds?.y ?? 0) + (bounds?.height ?? 0) * 0.68;
    const initialX = Number(await canvas.getAttribute("data-ball-x"));

    // Dispatch the interrupted gesture in one browser task. This proves that
    // pointercancel drops its target before a simulation step can consume it;
    // the later move with the same id must also be ignored.
    await canvas.evaluate((surface, point) => {
      const common = {
        pointerId: 91,
        pointerType: "touch",
        isPrimary: true,
        button: 0,
        bubbles: true,
      };
      surface.dispatchEvent(new PointerEvent("pointerdown", {
        ...common,
        buttons: 1,
        clientX: point.x,
        clientY: point.y,
      }));
      surface.dispatchEvent(new PointerEvent("pointermove", {
        ...common,
        buttons: 1,
        clientX: point.x + 90,
        clientY: point.y,
      }));
      surface.dispatchEvent(new PointerEvent("pointercancel", {
        ...common,
        buttons: 0,
        clientX: point.x + 90,
        clientY: point.y,
      }));
      surface.dispatchEvent(new PointerEvent("pointermove", {
        ...common,
        buttons: 1,
        clientX: point.x + 240,
        clientY: point.y,
      }));
    }, { x, y });
    await page.waitForTimeout(1_000);
    const resultingX = Number(await canvas.getAttribute("data-ball-x"));
    expect(Math.abs(resultingX - initialX)).toBeLessThan(0.08);
    expectRuntimeClean(runtime);
  });

  test("keeps mobile play and pause controls usable through reflow", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "mobile-chromium",
      "Phone portrait and landscape reflow is covered by mobile Chromium.",
    );

    const runtime = monitorRuntime(page);
    await openBallGame(page);
    const root = await startRun(page);

    for (const viewport of [
      { width: 320, height: 568 },
      { width: 568, height: 320 },
      { width: 915, height: 412 },
    ]) {
      await expectPageFitsViewport(page, viewport);
      const pause = page.getByRole("button", { name: "Pause game" });
      await expect(pause).toBeVisible();
      await expectInsideViewport(page, pause);
      const pauseBox = await pause.boundingBox();
      expect(pauseBox?.width ?? 0).toBeGreaterThanOrEqual(48);
      expect(pauseBox?.height ?? 0).toBeGreaterThanOrEqual(48);
    }

    await page.getByRole("button", { name: "Pause game" }).click();
    await expect(root).toHaveAttribute("data-mode", "paused");
    const dialog = page.getByRole("dialog", { name: "Take a breath." });
    await expect(dialog).toBeVisible();
    await expectInsideViewport(page, dialog);
    await expectUsableTargets(dialog);
    await expect(page.getByLabel("Game options")).toBeVisible();
    expectRuntimeClean(runtime);
  });

  test("demotes sustained slow frames and truly scales the backing buffer", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "mobile-chromium",
      "The balanced-to-performance renderer fallback is covered on mobile Chromium.",
    );

    await page.addInitScript(() => {
      for (const prototype of [
        WebGLRenderingContext.prototype,
        WebGL2RenderingContext.prototype,
      ]) {
        const nativeGetParameter = prototype.getParameter;
        prototype.getParameter = function getParameter(parameter: number) {
          if (parameter === 0x9246 || parameter === 0x1f01) {
            return "ANGLE test hardware renderer";
          }
          return nativeGetParameter.call(this, parameter);
        };
      }
    });
    await installControllableAnimationTimeline(page);
    const runtime = monitorRuntime(page);
    const canvas = await openBallGame(page);
    await expect(canvas).toHaveAttribute("data-software-renderer", "false");
    await expect(canvas).toHaveAttribute("data-quality-tier", "balanced");
    await expect(canvas).toHaveAttribute("data-active-ribs", "12");
    const balancedRatio = Number(await canvas.getAttribute("data-pixel-ratio"));

    await setAnimationTimelineStep(page, 50);
    await startRun(page);
    await expect(canvas).toHaveAttribute("data-quality-tier", "performance", {
      timeout: 10_000,
    });
    await expect(canvas).toHaveAttribute("data-active-ribs", "6");
    const performanceRatio = Number(await canvas.getAttribute("data-pixel-ratio"));
    expect(performanceRatio).toBeLessThan(balancedRatio);

    const backing = await canvas.evaluate((surface) => ({
      backingWidth: surface.width,
      backingHeight: surface.height,
      cssWidth: surface.clientWidth,
      cssHeight: surface.clientHeight,
      reportedWidth: Number(surface.dataset.renderWidth),
      reportedHeight: Number(surface.dataset.renderHeight),
    }));
    expect(backing.backingWidth).toBe(backing.reportedWidth);
    expect(backing.backingHeight).toBe(backing.reportedHeight);
    expect(Math.abs(
      backing.backingWidth - backing.cssWidth * performanceRatio,
    )).toBeLessThanOrEqual(3);
    expect(Math.abs(
      backing.backingHeight - backing.cssHeight * performanceRatio,
    )).toBeLessThanOrEqual(3);
    await expect(canvas).toHaveAttribute("data-material-mode", "standard");
    await expect(canvas).toBeVisible();
    await expect(page.getByRole("button", { name: "Pause game" })).toBeVisible();
    expectRuntimeClean(runtime);
  });
});
