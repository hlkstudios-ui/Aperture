import { describe, expect, it } from "vitest";
import {
  LOOM_ANCHOR_POOL_SIZE,
  LOOM_CONTRACT_SECONDS,
  LOOM_EXTENDED_LENGTH,
  LOOM_FIXED_STEP_SECONDS,
  LOOM_FLIGHT_BOUNDARY,
  LOOM_IRIS_CLEAR_SCORE,
  LOOM_IRIS_CONTACT_OFFSET_SECONDS,
  LOOM_IRIS_CONTACT_SECONDS,
  LOOM_IRIS_CYCLE_SECONDS,
  LOOM_IRIS_END_SECONDS,
  LOOM_IRIS_HIT_SCORE_PENALTY,
  LOOM_IRIS_GAP_CENTER_MIN_RADIUS,
  LOOM_IRIS_GAP_CENTER_RADIUS_RANGE,
  LOOM_IRIS_START_SECONDS,
  LOOM_MAX_THREAD_LENGTH,
  LOOM_REELED_LENGTH,
  LOOM_RESONANCE_CHARGE_REQUIRED,
  LOOM_RESONANCE_DURATION_SECONDS,
  LOOM_RESONANCE_RECOVERY_SECONDS,
  createLoomSimulation,
  loomArcForElapsed,
  loomForwardSpeedForElapsed,
  loomIrisClearance,
  loomIrisSecondsToContact,
  loomIrisStateForElapsed,
  resetLoomSimulation,
  stepLoomSimulation,
  type LoomAnchor,
  type LoomInput,
  type LoomSimulation,
} from "./loom-simulation";

const idleInput: LoomInput = {
  x: 0,
  y: 0,
  reel: false,
  phaseToggle: false,
  activateResonance: false,
};

function approachingAnchor(simulation: LoomSimulation): LoomAnchor | null {
  let selected: LoomAnchor | null = null;
  for (const anchor of simulation.anchors) {
    if (!anchor.active || anchor.resolved) continue;
    if (!selected || anchor.z > selected.z) selected = anchor;
  }
  return selected;
}

function guidedInput(simulation: LoomSimulation, reel: boolean): LoomInput {
  const target = approachingAnchor(simulation);
  const midpointX =
    (simulation.needle.position.x + simulation.echo.position.x) / 2;
  const midpointY =
    (simulation.needle.position.y + simulation.echo.position.y) / 2;
  const targetX = target?.x ?? 0;
  const targetY = target?.y ?? 0;
  const phaseToggle = Boolean(
    target &&
      target.z > -8 &&
      target.phase !== simulation.phase &&
      simulation.phaseCooldown <= 0 &&
      !simulation.pendingPhaseToggle,
  );
  return {
    x: Math.max(-1, Math.min(1, (targetX - midpointX) * 0.8)),
    y: Math.max(-1, Math.min(1, (targetY - midpointY) * 0.8)),
    reel: reel || target?.encounterKind === "opening-thread",
    phaseToggle,
    activateResonance:
      simulation.resonanceCharge >= LOOM_RESONANCE_CHARGE_REQUIRED &&
      simulation.resonanceRemaining <= 0 &&
      simulation.resonanceCooldownRemaining <= 0,
  };
}

function irisAwareGuidedInput(
  simulation: LoomSimulation,
  reel: boolean,
): LoomInput {
  const base = guidedInput(simulation, reel);
  const secondsToIris = loomIrisSecondsToContact(simulation.elapsed);
  if (
    !simulation.iris.active ||
    secondsToIris === null ||
    secondsToIris <= 0 ||
    secondsToIris > 2.25
  ) {
    return base;
  }

  const midpointX =
    (simulation.needle.position.x + simulation.echo.position.x) / 2;
  const midpointY =
    (simulation.needle.position.y + simulation.echo.position.y) / 2;
  return {
    ...base,
    x: Math.max(
      -1,
      Math.min(1, (simulation.iris.gapCenter.x - midpointX) * 0.9),
    ),
    y: Math.max(
      -1,
      Math.min(1, (simulation.iris.gapCenter.y - midpointY) * 0.9),
    ),
  };
}

function routeAwareGuidedInput(simulation: LoomSimulation): LoomInput {
  const target = approachingAnchor(simulation);
  return irisAwareGuidedInput(
    simulation,
    target?.route !== "expressive",
  );
}

function irisOutcomes(
  seed: number,
  policy: (simulation: LoomSimulation) => LoomInput,
): { clears: number; hits: number; simulation: LoomSimulation } {
  const simulation = createLoomSimulation(seed);
  let clears = 0;
  let hits = 0;
  let resolvedCycle = 0;
  const frames = LOOM_CONTRACT_SECONDS * 60;
  for (let frame = 0; frame < frames; frame += 1) {
    stepLoomSimulation(simulation, policy(simulation), LOOM_FIXED_STEP_SECONDS);
    if (
      simulation.iris.resolved &&
      simulation.iris.cycle > 0 &&
      simulation.iris.cycle !== resolvedCycle
    ) {
      resolvedCycle = simulation.iris.cycle;
      if (simulation.iris.outcome === "clear") clears += 1;
      if (simulation.iris.outcome === "hit") hits += 1;
    }
  }
  return { clears, hits, simulation };
}

function advance(
  simulation: LoomSimulation,
  seconds: number,
  frameRate = 60,
  policy: (state: LoomSimulation) => LoomInput = () => idleInput,
): LoomSimulation {
  const frames = Math.round(seconds * frameRate);
  for (let frame = 0; frame < frames; frame += 1) {
    stepLoomSimulation(simulation, policy(simulation), 1 / frameRate);
  }
  return simulation;
}

function anchorManifest(simulation: LoomSimulation) {
  return simulation.anchors
    .filter((anchor) => anchor.active)
    .map((anchor) => ({
      chunk: anchor.encounterKind,
      beat: anchor.beat,
      route: anchor.route,
      phase: anchor.phase,
      x: anchor.x,
      y: anchor.y,
      z: anchor.z,
    }));
}

function isolateTimers(simulation: LoomSimulation): void {
  simulation.nextSpawnZ = -20_000;
  for (const [index, anchor] of simulation.anchors.entries()) {
    anchor.active = true;
    anchor.resolved = false;
    anchor.latched = false;
    anchor.hit = false;
    anchor.z = -10_000 - index * 10;
  }
}

function primeIrisContact(
  simulation: LoomSimulation,
  cycle = 1,
): ReturnType<typeof loomIrisStateForElapsed> {
  isolateTimers(simulation);
  const contactElapsed =
    LOOM_IRIS_START_SECONDS +
    (cycle - 1) * LOOM_IRIS_CYCLE_SECONDS +
    LOOM_IRIS_CONTACT_OFFSET_SECONDS;
  simulation.tick = Math.round(contactElapsed / LOOM_FIXED_STEP_SECONDS) - 1;
  simulation.elapsed = simulation.tick * LOOM_FIXED_STEP_SECONDS;
  simulation.arc = loomArcForElapsed(simulation.elapsed);
  simulation.forwardSpeed = loomForwardSpeedForElapsed(simulation.elapsed);
  const scheduled = loomIrisStateForElapsed(simulation.seed, contactElapsed);
  simulation.iris = {
    ...scheduled,
    gapCenter: { ...scheduled.gapCenter },
    stage: "close",
    resolved: false,
    outcome: null,
  };
  return scheduled;
}

describe("Signal Loom deterministic greybox", () => {
  it("creates a repeatable seeded authored manifest in a bounded pool", () => {
    const first = createLoomSimulation("archive-seed");
    const repeat = createLoomSimulation("archive-seed");
    const different = createLoomSimulation("another-archive");

    expect(first.anchors).toHaveLength(LOOM_ANCHOR_POOL_SIZE);
    expect(new Set(first.anchors.map(({ poolSlot }) => poolSlot)).size).toBe(
      LOOM_ANCHOR_POOL_SIZE,
    );
    expect(anchorManifest(first)).toEqual(anchorManifest(repeat));
    expect(anchorManifest(first)).not.toEqual(anchorManifest(different));
    expect(first.authoredChunksSeen).toBeGreaterThan(1);
  });

  it("returns the same state and pool on zero-step calls", () => {
    const simulation = createLoomSimulation("zero-step");
    const anchors = simulation.anchors;
    const returned = stepLoomSimulation(
      simulation,
      { ...idleInput, phaseToggle: true },
      0,
    );

    expect(returned).toBe(simulation);
    expect(returned.anchors).toBe(anchors);
    expect(returned.tick).toBe(0);
    expect(returned.pendingPhaseToggle).toBe(true);
  });

  it("is equivalent at 60 and 120 render Hz, including queued one-shot input", () => {
    const sixty = createLoomSimulation("frame-rate");
    const oneTwenty = createLoomSimulation("frame-rate");

    advance(sixty, 75, 60, (state) => guidedInput(state, false));
    advance(oneTwenty, 75, 120, (state) => guidedInput(state, false));

    expect(oneTwenty.tick).toBe(sixty.tick);
    expect(oneTwenty.elapsed).toBe(sixty.elapsed);
    expect(oneTwenty.distance).toBeCloseTo(sixty.distance, 10);
    expect(oneTwenty.score).toBeCloseTo(sixty.score, 9);
    expect(oneTwenty.phase).toBe(sixty.phase);
    expect(oneTwenty.stitches).toBe(sixty.stitches);
    expect(oneTwenty.missedAnchors).toBe(sixty.missedAnchors);
    expect(oneTwenty.resonanceActivations).toBe(sixty.resonanceActivations);
    expect(oneTwenty.needle.position.x).toBeCloseTo(sixty.needle.position.x, 10);
    expect(oneTwenty.needle.position.y).toBeCloseTo(sixty.needle.position.y, 10);
    expect(oneTwenty.echo.position.x).toBeCloseTo(sixty.echo.position.x, 10);
    expect(oneTwenty.echo.position.y).toBeCloseTo(sixty.echo.position.y, 10);
    expect(anchorManifest(oneTwenty)).toEqual(anchorManifest(sixty));
  });

  it("keeps the spring-damper Thread finite and bounded under aggressive input", () => {
    const simulation = createLoomSimulation("spring-stability");
    for (let frame = 0; frame < 120 * 60; frame += 1) {
      const band = Math.floor(frame / 24) % 4;
      stepLoomSimulation(
        simulation,
        {
          x: band === 0 ? 1 : band === 2 ? -1 : 0,
          y: band === 1 ? 1 : band === 3 ? -1 : 0,
          reel: Math.floor(frame / 60) % 2 === 0,
          phaseToggle: frame % 113 === 0,
          activateResonance: frame % 509 === 0,
        },
        LOOM_FIXED_STEP_SECONDS,
      );
    }

    const values = [
      simulation.needle.position.x,
      simulation.needle.position.y,
      simulation.needle.velocity.x,
      simulation.needle.velocity.y,
      simulation.echo.position.x,
      simulation.echo.position.y,
      simulation.echo.velocity.x,
      simulation.echo.velocity.y,
      simulation.thread.length,
      simulation.thread.tension,
    ];
    expect(values.every(Number.isFinite)).toBe(true);
    expect(simulation.thread.length).toBeLessThanOrEqual(
      LOOM_MAX_THREAD_LENGTH + 1e-8,
    );
    expect(
      Math.hypot(simulation.needle.position.x, simulation.needle.position.y),
    ).toBeLessThanOrEqual(LOOM_FLIGHT_BOUNDARY + 1e-8);
    expect(
      Math.hypot(simulation.echo.position.x, simulation.echo.position.y),
    ).toBeLessThanOrEqual(LOOM_FLIGHT_BOUNDARY + 1e-8);
    expect(simulation.thread.peakTension).toBeGreaterThan(0);
  });

  it("reels the Echo inward, stabilizes it, and extends again on release", () => {
    const simulation = createLoomSimulation("reel-contract");
    advance(simulation, 2, 60, () => ({ ...idleInput, reel: true }));

    expect(simulation.thread.targetLength).toBe(LOOM_REELED_LENGTH);
    expect(simulation.thread.restLength).toBeCloseTo(LOOM_REELED_LENGTH, 8);
    expect(simulation.thread.length).toBeLessThan(LOOM_REELED_LENGTH + 0.2);
    expect(simulation.thread.tension).toBeLessThan(0.12);

    advance(simulation, 2, 60, () => idleInput);
    expect(simulation.thread.targetLength).toBe(LOOM_EXTENDED_LENGTH);
    expect(simulation.thread.restLength).toBeCloseTo(LOOM_EXTENDED_LENGTH, 8);
    expect(simulation.thread.length).toBeGreaterThan(LOOM_EXTENDED_LENGTH - 0.25);
  });

  it("makes the guaranteed opening stitch reachable in under thirty seconds", () => {
    for (let seed = 1; seed <= 100; seed += 1) {
      const simulation = createLoomSimulation(seed);
      for (let frame = 0; frame < 30 * 60 && simulation.stitches === 0; frame += 1) {
        stepLoomSimulation(
          simulation,
          { ...idleInput, reel: true },
          LOOM_FIXED_STEP_SECONDS,
        );
      }
      expect(simulation.stitches, `seed ${seed}`).toBeGreaterThan(0);
      expect(simulation.lastStitchEvent?.encounterKind, `seed ${seed}`).toBe(
        "opening-thread",
      );
      expect(simulation.elapsed, `seed ${seed}`).toBeLessThan(30);
    }
  });

  it("never awards stitches, Resonance, or expressive credit without input", () => {
    for (let seed = 1; seed <= 100; seed += 1) {
      const simulation = createLoomSimulation(seed);
      advance(simulation, LOOM_CONTRACT_SECONDS, 60);

      expect(simulation.stitches, `seed ${seed}`).toBe(0);
      expect(simulation.expressiveStitches, `seed ${seed}`).toBe(0);
      expect(simulation.resonanceCharge, `seed ${seed}`).toBe(0);
      expect(simulation.score, `seed ${seed}`).toBeLessThanOrEqual(
        simulation.distance * 0.15,
      );
      expect(simulation.threadBreaks, `seed ${seed}`).toBeGreaterThan(0);
    }
  });

  it("keeps the Iris dormant before Arc III and begins with a telegraph", () => {
    const simulation = createLoomSimulation("iris-boundary");
    advance(
      simulation,
      LOOM_IRIS_START_SECONDS - LOOM_FIXED_STEP_SECONDS,
    );

    expect(simulation.arc).toBe(2);
    expect(simulation.iris).toMatchObject({
      active: false,
      cycle: 0,
      stage: "dormant",
      resolved: false,
      outcome: null,
    });

    stepLoomSimulation(simulation, idleInput, LOOM_FIXED_STEP_SECONDS);
    expect(simulation.arc).toBe(3);
    expect(simulation.iris).toMatchObject({
      active: true,
      cycle: 1,
      stage: "telegraph",
      resolved: false,
      outcome: null,
    });
    expect(simulation.iris.intensity).toBeGreaterThan(0);
  });

  it("places every Iris aperture off the passive center line but within reach", () => {
    for (let seed = 1; seed <= 128; seed += 1) {
      const simulation = createLoomSimulation(seed);
      for (let cycle = 1; cycle <= 8; cycle += 1) {
        const elapsed = LOOM_IRIS_START_SECONDS +
          (cycle - 1) * LOOM_IRIS_CYCLE_SECONDS;
        const iris = loomIrisStateForElapsed(simulation.seed, elapsed);
        const radius = Math.hypot(iris.gapCenter.x, iris.gapCenter.y);
        expect(radius).toBeGreaterThanOrEqual(
          LOOM_IRIS_GAP_CENTER_MIN_RADIUS,
        );
        expect(radius).toBeLessThanOrEqual(
          LOOM_IRIS_GAP_CENTER_MIN_RADIUS +
            LOOM_IRIS_GAP_CENTER_RADIUS_RANGE,
        );

        simulation.iris = {
          ...iris,
          gapCenter: { ...iris.gapCenter },
        };
        simulation.needle.position = { x: 0, y: 0 };
        simulation.echo.position = { x: -LOOM_REELED_LENGTH, y: 0 };
        expect(loomIrisClearance(simulation).minimum).toBeLessThan(0);
      }
    }
  });

  it("rejects passive Reel farming while preserving a two-second guided line", () => {
    for (let seed = 1; seed <= 32; seed += 1) {
      const passive = irisOutcomes(seed, () => ({ ...idleInput, reel: true }));
      const guided = irisOutcomes(seed, (simulation) =>
        irisAwareGuidedInput(simulation, true),
      );

      expect(passive.clears, `passive seed ${seed}`).toBe(0);
      expect(passive.hits, `passive seed ${seed}`).toBe(8);
      expect(guided.clears, `guided seed ${seed}`).toBe(8);
      expect(guided.hits, `guided seed ${seed}`).toBe(0);
      expect(guided.simulation.score, `guided seed ${seed}`).toBeGreaterThan(
        passive.simulation.score,
      );
    }
  });

  it("reports Iris contact time from the authored schedule at every boundary", () => {
    const contactAt = LOOM_IRIS_START_SECONDS + LOOM_IRIS_CONTACT_OFFSET_SECONDS;
    expect(loomIrisSecondsToContact(LOOM_IRIS_START_SECONDS - 0.01)).toBeNull();
    expect(loomIrisSecondsToContact(LOOM_IRIS_START_SECONDS)).toBeCloseTo(
      LOOM_IRIS_CONTACT_OFFSET_SECONDS,
    );
    expect(loomIrisSecondsToContact(LOOM_IRIS_START_SECONDS + 1.167)).toBeCloseTo(
      LOOM_IRIS_CONTACT_OFFSET_SECONDS - 1.167,
      3,
    );
    expect(loomIrisSecondsToContact(LOOM_IRIS_START_SECONDS + 6.167)).toBeCloseTo(
      LOOM_IRIS_CONTACT_OFFSET_SECONDS - 6.167,
      3,
    );
    expect(loomIrisSecondsToContact(contactAt - 0.25)).toBeCloseTo(0.25);
    expect(loomIrisSecondsToContact(contactAt)).toBe(0);
    expect(loomIrisSecondsToContact(contactAt + 0.25)).toBe(0);
    expect(
      loomIrisSecondsToContact(contactAt + LOOM_IRIS_CONTACT_SECONDS),
    ).toBeNull();
    expect(
      loomIrisSecondsToContact(LOOM_IRIS_START_SECONDS + LOOM_IRIS_CYCLE_SECONDS),
    ).toBeCloseTo(LOOM_IRIS_CONTACT_OFFSET_SECONDS);
    expect(loomIrisSecondsToContact(LOOM_IRIS_END_SECONDS)).toBeNull();
  });

  it("finishes recovery without starting an unresolvable extraction cycle", () => {
    const simulation = createLoomSimulation("iris-extraction-boundary");
    const finalRecovery = loomIrisStateForElapsed(
      simulation.seed,
      LOOM_IRIS_END_SECONDS - LOOM_FIXED_STEP_SECONDS,
    );
    const afterCycles = loomIrisStateForElapsed(
      simulation.seed,
      LOOM_IRIS_END_SECONDS,
    );

    expect(finalRecovery).toMatchObject({
      active: true,
      stage: "recovery",
    });
    expect(afterCycles).toMatchObject({
      active: false,
      cycle: 0,
      stage: "dormant",
    });
  });

  it("advances Iris stages identically at 60 and 120 render Hz", () => {
    const sixty = createLoomSimulation("iris-frame-rate");
    const oneTwenty = createLoomSimulation("iris-frame-rate");

    advance(sixty, 230, 60);
    advance(oneTwenty, 230, 120);

    expect(oneTwenty.tick).toBe(sixty.tick);
    expect(oneTwenty.iris).toEqual(sixty.iris);
    expect(oneTwenty.threadBreaks).toBe(sixty.threadBreaks);
    expect(oneTwenty.missedAnchors).toBe(sixty.missedAnchors);
    expect(oneTwenty.score).toBeCloseTo(sixty.score, 9);
  });

  it("rewards one aligned Needle, Echo, and Thread pass", () => {
    const simulation = createLoomSimulation("iris-clear");
    const scheduled = primeIrisContact(simulation);
    simulation.score = 500;
    simulation.needle.position = {
      x: scheduled.gapCenter.x + 0.9,
      y: scheduled.gapCenter.y,
    };
    simulation.echo.position = {
      x: scheduled.gapCenter.x - 0.9,
      y: scheduled.gapCenter.y,
    };
    simulation.needle.velocity = { x: 0, y: 0 };
    simulation.echo.velocity = { x: 0, y: 0 };
    simulation.thread.restLength = 1.8;
    const beforeScore = simulation.score;

    stepLoomSimulation(simulation, idleInput, LOOM_FIXED_STEP_SECONDS);

    expect(simulation.iris).toMatchObject({
      stage: "contact",
      resolved: true,
      outcome: "clear",
      chargeAwarded: true,
    });
    expect(loomIrisClearance(simulation).minimum).toBeGreaterThan(0);
    expect(simulation.score - beforeScore).toBeGreaterThanOrEqual(
      LOOM_IRIS_CLEAR_SCORE,
    );
    expect(simulation.resonanceCharge).toBe(1);
    expect(simulation.threadBreaks).toBe(0);
  });

  it("reports a full Resonance bank without claiming another Iris charge", () => {
    const simulation = createLoomSimulation("iris-full-charge");
    const scheduled = primeIrisContact(simulation);
    simulation.resonanceCharge = LOOM_RESONANCE_CHARGE_REQUIRED;
    simulation.needle.position = { ...scheduled.gapCenter };
    simulation.echo.position = { ...scheduled.gapCenter };
    simulation.needle.velocity = { x: 0, y: 0 };
    simulation.echo.velocity = { x: 0, y: 0 };

    stepLoomSimulation(simulation, idleInput, LOOM_FIXED_STEP_SECONDS);

    expect(simulation.iris).toMatchObject({
      outcome: "clear",
      chargeAwarded: false,
    });
    expect(simulation.resonanceCharge).toBe(LOOM_RESONANCE_CHARGE_REQUIRED);
  });

  it("turns blade contact into a non-terminal break, miss, and chain loss", () => {
    const simulation = createLoomSimulation("iris-hit");
    const scheduled = primeIrisContact(simulation);
    simulation.score = 1_000;
    simulation.stitchChain = 7;
    simulation.needle.position = {
      x: scheduled.gapCenter.x + scheduled.gapRadius + 0.8,
      y: scheduled.gapCenter.y,
    };
    simulation.echo.position = { ...scheduled.gapCenter };
    simulation.needle.velocity = { x: 0, y: 0 };
    simulation.echo.velocity = { x: 0, y: 0 };
    const beforeScore = simulation.score;

    stepLoomSimulation(simulation, idleInput, LOOM_FIXED_STEP_SECONDS);

    expect(simulation.iris).toMatchObject({
      stage: "contact",
      resolved: true,
      outcome: "hit",
    });
    expect(loomIrisClearance(simulation).minimum).toBeLessThan(0);
    expect(simulation.threadBreaks).toBe(1);
    expect(simulation.missedAnchors).toBe(1);
    expect(simulation.stitchChain).toBe(0);
    expect(simulation.score).toBeCloseTo(
      beforeScore - LOOM_IRIS_HIT_SCORE_PENALTY +
        simulation.forwardSpeed * LOOM_FIXED_STEP_SECONDS * 0.15,
      5,
    );
    expect(simulation.status).toBe("running");
  });

  it("resolves each Iris cycle once and preserves its outcome through recovery", () => {
    const simulation = createLoomSimulation("iris-single-resolution");
    const scheduled = primeIrisContact(simulation);
    simulation.needle.position = {
      x: scheduled.gapCenter.x + scheduled.gapRadius + 0.8,
      y: scheduled.gapCenter.y,
    };
    simulation.echo.position = { ...scheduled.gapCenter };
    simulation.needle.velocity = { x: 0, y: 0 };
    simulation.echo.velocity = { x: 0, y: 0 };

    advance(
      simulation,
      LOOM_IRIS_CONTACT_SECONDS + 0.25,
      60,
    );

    expect(simulation.iris.stage).toBe("recovery");
    expect(simulation.iris.outcome).toBe("hit");
    expect(simulation.threadBreaks).toBe(1);
    expect(simulation.missedAnchors).toBe(1);
  });

  it("distributes authored anchors across every flight-plane quadrant", () => {
    const quadrants = new Set<string>();
    for (let seed = 1; seed <= 30; seed += 1) {
      const simulation = createLoomSimulation(seed);
      for (const anchor of simulation.anchors) {
        if (!anchor.active || anchor.encounterKind === "opening-thread") continue;
        quadrants.add(`${anchor.x >= 0 ? "+" : "-"}${anchor.y >= 0 ? "+" : "-"}`);
      }
    }
    expect(quadrants).toEqual(new Set(["++", "+-", "-+", "--"]));
  });

  it("requires a matching phase to latch and resolve a stitch", () => {
    const missed = createLoomSimulation("phase-miss");
    const matched = createLoomSimulation("phase-match");
    const missedAnchor = missed.anchors.find(({ active }) => active);
    const matchedAnchor = matched.anchors.find(({ active }) => active);
    expect(missedAnchor).toBeTruthy();
    expect(matchedAnchor).toBeTruthy();
    if (!missedAnchor || !matchedAnchor) return;

    for (const [simulation, anchor] of [
      [missed, missedAnchor],
      [matched, matchedAnchor],
    ] as const) {
      anchor.x = -1.4;
      anchor.y = 0;
      anchor.z = -0.1;
      anchor.phase = "cobalt";
      anchor.encounterKind = "quiet-splice";
      for (const candidate of simulation.anchors) {
        if (candidate !== anchor) candidate.z -= 1_000;
      }
    }

    advance(missed, 0.3);
    stepLoomSimulation(
      matched,
      { ...idleInput, phaseToggle: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    advance(matched, 0.3 - LOOM_FIXED_STEP_SECONDS);

    expect(missed.stitches).toBe(0);
    expect(missed.missedAnchors).toBe(1);
    expect(matched.stitches).toBe(1);
    expect(matched.lastStitchEvent).toMatchObject({
      phase: "cobalt",
      encounterKind: "quiet-splice",
    });
  });

  it("preserves early per-anchor preparation until identical contact", () => {
    const early = createLoomSimulation("early-authorship");
    const late = createLoomSimulation("late-authorship");
    for (const simulation of [early, late]) {
      const anchor = simulation.anchors.find(({ active }) => active);
      expect(anchor).toBeTruthy();
      if (!anchor) continue;
      anchor.x = -1.4;
      anchor.y = 0;
      anchor.z = -18;
      anchor.phase = "cobalt";
      anchor.encounterKind = "quiet-splice";
      for (const candidate of simulation.anchors) {
        if (candidate !== anchor) candidate.z -= 1_000;
      }
    }

    stepLoomSimulation(
      early,
      { ...idleInput, phaseToggle: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    advance(early, 2.5 - LOOM_FIXED_STEP_SECONDS);

    advance(late, 1.2);
    stepLoomSimulation(
      late,
      { ...idleInput, phaseToggle: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    advance(late, 1.3 - LOOM_FIXED_STEP_SECONDS);

    expect(early.stitches).toBe(1);
    expect(late.stitches).toBe(1);
    expect(early.missedAnchors).toBe(late.missedAnchors);
    expect(early.score).toBeCloseTo(late.score, 8);
  });

  it("does not let one motionless Reel hold author unrelated anchors", () => {
    const simulation = createLoomSimulation("held-reel-authorship");
    advance(simulation, 30, 60, () => ({ ...idleInput, reel: true }));

    expect(simulation.stitches).toBe(1);
    expect(simulation.expressiveStitches).toBe(0);
    expect(simulation.resonanceCharge).toBe(1);
  });

  it("rewards a genuine endpoint skim as a near-miss stitch bonus", () => {
    const simulation = createLoomSimulation("near-miss");
    const anchor = simulation.anchors.find(({ active }) => active);
    expect(anchor).toBeTruthy();
    if (!anchor) return;
    anchor.x = -3.75;
    anchor.y = 0;
    anchor.z = -0.1;
    anchor.phase = simulation.phase;
    anchor.route = "expressive";
    anchor.encounterKind = "wide-exposure";
    anchor.armed = true;
    for (const candidate of simulation.anchors) {
      if (candidate !== anchor) candidate.z -= 1_000;
    }

    advance(simulation, 0.3);
    expect(simulation.stitches).toBe(1);
    expect(simulation.nearMisses).toBe(1);
    expect(simulation.lastStitchEvent).toMatchObject({
      expressive: true,
      nearMiss: true,
    });
  });

  it("pays extension and tension premiums only on authored expressive routes", () => {
    const makeStitch = (route: "safe" | "expressive", extended: boolean) => {
      const simulation = createLoomSimulation(`route-score-${route}-${extended}`);
      const anchor = simulation.anchors.find(({ active }) => active);
      expect(anchor).toBeTruthy();
      if (!anchor) return simulation;
      anchor.x = 0;
      anchor.y = 0;
      anchor.z = -0.1;
      anchor.phase = simulation.phase;
      anchor.route = route;
      anchor.encounterKind = route === "expressive"
        ? "wide-exposure"
        : "quiet-splice";
      anchor.armed = true;
      for (const candidate of simulation.anchors) {
        if (candidate !== anchor) candidate.z -= 1_000;
      }
      const length = extended ? LOOM_EXTENDED_LENGTH : LOOM_REELED_LENGTH;
      simulation.needle.position = { x: length / 2, y: 0 };
      simulation.echo.position = { x: -length / 2, y: 0 };
      simulation.needle.velocity = { x: 0, y: 0 };
      simulation.echo.velocity = { x: 0, y: 0 };
      simulation.thread.restLength = extended
        ? LOOM_EXTENDED_LENGTH
        : LOOM_REELED_LENGTH;
      simulation.thread.targetLength = simulation.thread.restLength;
      advance(simulation, 0.3);
      return simulation;
    };

    const safeReeled = makeStitch("safe", false);
    const safeExtended = makeStitch("safe", true);
    const expressiveReeled = makeStitch("expressive", false);
    const expressiveExtended = makeStitch("expressive", true);

    expect(safeReeled.lastStitchEvent?.scoreAwarded).toBeGreaterThan(0);
    expect(safeExtended.lastStitchEvent?.scoreAwarded).toBeCloseTo(
      safeReeled.lastStitchEvent?.scoreAwarded ?? 0,
      8,
    );
    expect(expressiveExtended.lastStitchEvent?.scoreAwarded).toBeGreaterThan(
      expressiveReeled.lastStitchEvent?.scoreAwarded ?? 0,
    );
  });

  it("applies a stored manual Resonance burst to the stitch reward", () => {
    const normal = createLoomSimulation("resonant-stitch");
    const boosted = createLoomSimulation("resonant-stitch");
    for (const simulation of [normal, boosted]) {
      const anchor = simulation.anchors.find(({ active }) => active);
      expect(anchor).toBeTruthy();
      if (!anchor) continue;
      anchor.x = -1.4;
      anchor.y = 0;
      anchor.z = -0.1;
      anchor.phase = simulation.phase;
      anchor.route = "safe";
      anchor.encounterKind = "quiet-splice";
      anchor.armed = true;
      for (const candidate of simulation.anchors) {
        if (candidate !== anchor) candidate.z -= 1_000;
      }
    }
    boosted.resonanceCharge = LOOM_RESONANCE_CHARGE_REQUIRED;

    advance(normal, 0.3);
    stepLoomSimulation(
      boosted,
      { ...idleInput, activateResonance: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    advance(boosted, 0.3 - LOOM_FIXED_STEP_SECONDS);

    expect(normal.lastStitchEvent?.scoreAwarded).toBeGreaterThan(0);
    expect(boosted.lastStitchEvent?.resonanceActive).toBe(true);
    expect(boosted.lastStitchEvent?.scoreAwarded).toBeCloseTo(
      (normal.lastStitchEvent?.scoreAwarded ?? 0) * 2,
      8,
    );
  });

  it("stores manual Resonance, never refreshes it, and bounds its duty cycle", () => {
    const simulation = createLoomSimulation("manual-resonance");
    isolateTimers(simulation);
    simulation.resonanceCharge = LOOM_RESONANCE_CHARGE_REQUIRED;
    stepLoomSimulation(
      simulation,
      { ...idleInput, activateResonance: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    expect(simulation.resonanceRemaining).toBe(
      LOOM_RESONANCE_DURATION_SECONDS,
    );
    expect(simulation.resonanceActivations).toBe(1);

    simulation.resonanceCharge = LOOM_RESONANCE_CHARGE_REQUIRED;
    advance(simulation, 3);
    const beforeDeniedRefresh = simulation.resonanceRemaining;
    stepLoomSimulation(
      simulation,
      { ...idleInput, activateResonance: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    expect(simulation.resonanceRemaining).toBeLessThan(beforeDeniedRefresh);
    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.resonanceCharge).toBe(LOOM_RESONANCE_CHARGE_REQUIRED);

    advance(simulation, 3.1);
    expect(simulation.resonanceRemaining).toBe(0);
    expect(simulation.resonanceCooldownRemaining).toBeGreaterThan(0);
    stepLoomSimulation(
      simulation,
      { ...idleInput, activateResonance: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    expect(simulation.resonanceActivations).toBe(1);

    advance(simulation, LOOM_RESONANCE_RECOVERY_SECONDS + 0.1);
    stepLoomSimulation(
      simulation,
      { ...idleInput, activateResonance: true },
      LOOM_FIXED_STEP_SECONDS,
    );
    expect(simulation.resonanceActivations).toBe(2);

    const dutyCycle = createLoomSimulation("resonance-duty-cycle");
    isolateTimers(dutyCycle);
    for (let frame = 0; frame < 180 * 60; frame += 1) {
      dutyCycle.resonanceCharge = LOOM_RESONANCE_CHARGE_REQUIRED;
      stepLoomSimulation(
        dutyCycle,
        { ...idleInput, activateResonance: true },
        LOOM_FIXED_STEP_SECONDS,
      );
    }
    expect(dutyCycle.resonanceActivations).toBeGreaterThan(5);
    expect(dutyCycle.resonanceActiveSeconds / dutyCycle.elapsed).toBeGreaterThan(
      0.3,
    );
    expect(dutyCycle.resonanceActiveSeconds / dutyCycle.elapsed).toBeLessThanOrEqual(
      0.35,
    );
  });

  it("makes reading safe and expressive routes beat permanent extension", () => {
    let routeWins = 0;
    let routeTotal = 0;
    let reelTotal = 0;
    for (let seed = 1; seed <= 24; seed += 1) {
      const routeAware = createLoomSimulation(seed);
      const alwaysExtended = createLoomSimulation(seed);
      const alwaysReeled = createLoomSimulation(seed);
      advance(routeAware, LOOM_CONTRACT_SECONDS, 60, routeAwareGuidedInput);
      advance(alwaysExtended, LOOM_CONTRACT_SECONDS, 60, (state) =>
        irisAwareGuidedInput(state, false),
      );
      advance(alwaysReeled, LOOM_CONTRACT_SECONDS, 60, (state) =>
        irisAwareGuidedInput(state, true),
      );
      if (routeAware.score > alwaysExtended.score) routeWins += 1;
      routeTotal += routeAware.score;
      reelTotal += alwaysReeled.score;
    }

    expect(routeWins).toBeGreaterThanOrEqual(21);
    expect(reelTotal / routeTotal).toBeGreaterThanOrEqual(0.85);
    expect(reelTotal / routeTotal).toBeLessThanOrEqual(1.15);
  });

  it("progresses through four arcs and extracts an exact six-minute result", () => {
    const simulation = createLoomSimulation("six-minute-contract");
    expect(loomArcForElapsed(0)).toBe(1);
    expect(loomArcForElapsed(90)).toBe(2);
    expect(loomArcForElapsed(210)).toBe(3);
    expect(loomArcForElapsed(330)).toBe(4);
    expect(loomForwardSpeedForElapsed(330)).toBeGreaterThan(
      loomForwardSpeedForElapsed(0),
    );

    advance(simulation, LOOM_CONTRACT_SECONDS, 60, (state) =>
      guidedInput(state, false),
    );
    expect(simulation.status).toBe("extracted");
    expect(simulation.elapsed).toBe(LOOM_CONTRACT_SECONDS);
    expect(simulation.tick).toBe(LOOM_CONTRACT_SECONDS * 60);
    expect(simulation.arc).toBe(4);
    expect(simulation.result).toMatchObject({
      outcome: "extracted",
      durationSeconds: LOOM_CONTRACT_SECONDS,
      stitches: simulation.stitches,
      authoredChunksSeen: simulation.authoredChunksSeen,
    });
    expect(simulation.result?.finalScore).toBe(Math.floor(simulation.score));
    expect(simulation.result?.distance).toBe(simulation.distance);
    expect(simulation.anchors).toHaveLength(LOOM_ANCHOR_POOL_SIZE);

    const result = simulation.result;
    const tick = simulation.tick;
    stepLoomSimulation(simulation, idleInput, 10);
    expect(simulation.result).toBe(result);
    expect(simulation.tick).toBe(tick);
    expect(resetLoomSimulation("six-minute-contract").elapsed).toBe(0);
  });

  it("keeps authored-seed score variance bounded for the same clean policy", () => {
    const scores: number[] = [];
    for (let seed = 1; seed <= 30; seed += 1) {
      const simulation = createLoomSimulation(seed);
      advance(simulation, LOOM_CONTRACT_SECONDS, 60, (state) =>
        guidedInput(state, false),
      );
      scores.push(simulation.score);
    }
    const mean = scores.reduce((sum, score) => sum + score, 0) / scores.length;
    const standardDeviation = Math.sqrt(
      scores.reduce((sum, score) => sum + (score - mean) ** 2, 0) /
        scores.length,
    );

    expect(standardDeviation / mean).toBeLessThan(0.12);
  });
});
