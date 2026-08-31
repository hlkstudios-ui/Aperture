import { describe, expect, it } from "vitest";
import {
  FIXED_STEP_SECONDS,
  HIT_INVULNERABILITY_SECONDS,
  INITIAL_SPEED,
  MAX_PHRASES_WITHOUT_MOVEMENT_CHECK,
  MAX_SPEED,
  MINIMUM_OBSTACLE_REACTION_SECONDS,
  MOVEMENT_CHECK_BAFFLE_CENTER_X,
  MOVEMENT_CHECK_BAFFLE_HEIGHT,
  MOVEMENT_CHECK_BAFFLE_WIDTH,
  PHASE_TOGGLE_COOLDOWN_SECONDS,
  PLAYER_BOUNDARY_RADIUS,
  PLAYER_VERTICAL_BOUNDARY_RADIUS,
  RESONANCE_DURATION_SECONDS,
  RESONANCE_PIPS_REQUIRED,
  RESONANCE_SCORE_MULTIPLIER,
  clampPlayerToTunnel,
  commitPrimedInput,
  createSimulation,
  eligiblePhraseKindsForSector,
  minimumObstacleSpacingForSpeed,
  obstacleCadenceJitter,
  obstacleCollidesWithPlayer,
  playerIntersectsBlock,
  resetSimulation,
  scoreMultiplierForSimulation,
  sectorForElapsed,
  sphereIntersectsAabb,
  speedForElapsed,
  stepSimulation,
  type BlockObstacle,
  type GamePhase,
  type GameSimulation,
  type MembraneObstacle,
  type PlayerState,
  type SignalPhraseKind,
} from "./simulation";

const idleInput = { x: 0, y: 0, phaseToggle: false };

function membrane(id: string, z: number, phase: GamePhase): MembraneObstacle {
  return {
    id,
    poolSlot: Number(id.replace(/\D/g, "")) || 0,
    phraseId: "test-" + id,
    phraseKind: "solo-membrane",
    phraseBeat: 1,
    phraseLength: 1,
    kind: "membrane",
    x: 0,
    y: 0,
    z,
    radius: 9,
    depth: 0.4,
    phase,
    passed: false,
    hit: false,
  };
}

function movementBaffle(
  id: string,
  x: number,
  z: number,
  beat: number,
): BlockObstacle {
  return {
    id,
    poolSlot: beat - 1,
    phraseId: "movement-check",
    phraseKind: "slalom",
    phraseBeat: beat,
    phraseLength: 3,
    kind: "block",
    x,
    y: 0,
    z,
    width: MOVEMENT_CHECK_BAFFLE_WIDTH,
    height: MOVEMENT_CHECK_BAFFLE_HEIGHT,
    depth: 2.4,
    passed: false,
    hit: false,
  };
}

function quietSimulation(seed: string): GameSimulation {
  const simulation = createSimulation(seed);
  simulation.obstacles = simulation.obstacles.map((obstacle, index) => ({
    ...obstacle,
    z: -1_000 - index * 32,
  }));
  return simulation;
}

function makeHazardsSafe(simulation: GameSimulation): void {
  for (const obstacle of simulation.obstacles) {
    if (obstacle.kind === "block") {
      obstacle.x = PLAYER_BOUNDARY_RADIUS;
      obstacle.y = 0;
    } else {
      obstacle.phase = simulation.phase;
    }
  }
}

function forceHazardCollision(simulation: GameSimulation, phraseId: string): void {
  const obstacle = simulation.obstacles.find(
    (candidate) => candidate.phraseId === phraseId && !candidate.passed,
  );
  if (!obstacle) return;
  if (obstacle.kind === "block") {
    obstacle.x = simulation.player.position.x;
    obstacle.y = simulation.player.position.y;
  } else {
    obstacle.phase = simulation.phase === "ember" ? "cobalt" : "ember";
  }
}

function advanceSafely(
  startingSimulation: GameSimulation,
  seconds: number,
  frameRate = 60,
): GameSimulation {
  let simulation = startingSimulation;
  const frameCount = Math.round(seconds * frameRate);
  for (let frame = 0; frame < frameCount; frame += 1) {
    makeHazardsSafe(simulation);
    simulation = stepSimulation(simulation, idleInput, 1 / frameRate);
  }
  return simulation;
}

function advanceToNextPhraseEvent(
  startingSimulation: GameSimulation,
  damagePhraseId?: string,
): GameSimulation {
  let simulation = startingSimulation;
  const startingSequence = simulation.phraseEventSequence;
  let collisionForced = false;

  for (let frame = 0; frame < 1_800; frame += 1) {
    makeHazardsSafe(simulation);
    if (damagePhraseId && !collisionForced) {
      const obstacle = simulation.obstacles.find(
        (candidate) => candidate.phraseId === damagePhraseId && !candidate.passed,
      );
      if (obstacle && obstacle.z > -1) {
        forceHazardCollision(simulation, damagePhraseId);
      }
    }
    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    if (damagePhraseId) {
      collisionForced = Boolean(
        simulation.phraseProgress.find(({ id }) => id === damagePhraseId)?.damaged,
      );
    }
    if (simulation.phraseEventSequence > startingSequence) return simulation;
  }

  throw new Error("Phrase did not resolve within the deterministic test window.");
}

function controlledPhraseState(
  seed: string,
  phraseLengths: number[],
  options: {
    cleanStreak?: number;
    peakCleanStreak?: number;
    resonancePips?: number;
    resonanceRemaining?: number;
    damaged?: boolean;
  } = {},
): GameSimulation {
  const simulation = createSimulation(seed);
  simulation.obstacles = [];
  simulation.pendingPhrase = null;
  simulation.phraseProgress = [];
  simulation.activePhrase = null;
  simulation.nextObstacleId = 100;
  simulation.cleanPhraseStreak = options.damaged ? 0 : options.cleanStreak ?? 0;
  simulation.peakCleanPhraseStreak =
    options.peakCleanStreak ?? options.cleanStreak ?? simulation.cleanPhraseStreak;
  simulation.resonancePips = options.damaged ? 0 : options.resonancePips ?? 0;
  simulation.resonanceRemaining = options.resonanceRemaining ?? 0;

  let obstacleIndex = 0;
  for (const [phraseIndex, length] of phraseLengths.entries()) {
    const phraseId = `controlled-${phraseIndex}`;
    const phraseKind: SignalPhraseKind = length === 1 ? "solo-block" : "slalom";
    simulation.phraseProgress.push({
      id: phraseId,
      kind: phraseKind,
      length,
      passedBeats: 0,
      damaged: options.damaged ?? false,
      scoreBonus: 0,
    });

    for (let beat = 1; beat <= length; beat += 1) {
      simulation.obstacles.push({
        id: `controlled-obstacle-${obstacleIndex}`,
        poolSlot: obstacleIndex,
        phraseId,
        phraseKind,
        phraseBeat: beat,
        phraseLength: length,
        kind: "block",
        x: PLAYER_BOUNDARY_RADIUS,
        y: 0,
        z: 3,
        width: 0.2,
        height: 0.2,
        depth: 2.4,
        passed: false,
        hit: options.damaged ?? false,
      });
      obstacleIndex += 1;
    }
  }

  return simulation;
}

describe("phase tunnel simulation", () => {
  it("reuses immutable state between fixed ticks to avoid high-refresh garbage", () => {
    const initial = createSimulation("high-refresh");
    const partial = stepSimulation(initial, idleInput, FIXED_STEP_SECONDS / 2);

    expect(partial.player).toBe(initial.player);
    expect(partial.obstacles).toBe(initial.obstacles);
    expect(partial.distance).toBe(0);

    const completed = stepSimulation(partial, idleInput, FIXED_STEP_SECONDS / 2);
    expect(completed.player).not.toBe(initial.player);
    expect(completed.obstacles).not.toBe(initial.obstacles);
    expect(completed.distance).toBeGreaterThan(0);
  });

  it("starts gently, ramps smoothly through four sectors, and caps at redline", () => {
    expect(INITIAL_SPEED).toBeGreaterThanOrEqual(9);
    expect(INITIAL_SPEED).toBeLessThanOrEqual(10);
    expect(speedForElapsed(0)).toBe(INITIAL_SPEED);
    expect(speedForElapsed(6)).toBeGreaterThan(INITIAL_SPEED);
    expect(speedForElapsed(6)).toBeLessThan(12);

    const samples = Array.from({ length: 121 }, (_, second) =>
      speedForElapsed(second),
    );
    for (let index = 1; index < samples.length; index += 1) {
      expect(samples[index]).toBeGreaterThanOrEqual(samples[index - 1]);
    }

    expect(sectorForElapsed(0)).toBe(1);
    expect(sectorForElapsed(12)).toBe(2);
    expect(sectorForElapsed(32)).toBe(3);
    expect(sectorForElapsed(58)).toBe(4);
    expect(speedForElapsed(12)).toBe(13);
    expect(speedForElapsed(32)).toBe(22);
    expect(speedForElapsed(58)).toBe(31);
    expect(speedForElapsed(88)).toBe(MAX_SPEED);
    expect(speedForElapsed(10_000)).toBe(MAX_SPEED);
  });

  it("keeps encounter cadence fair while content still varies by seed", () => {
    const baseline = createSimulation("cadence-baseline");
    const encounterPositions = baseline.obstacles.map(({ z }) => z);
    const contentSignatures = new Set<string>();

    for (let seed = 1; seed <= 100; seed += 1) {
      const simulation = createSimulation(`cadence-${seed}`);
      expect(simulation.obstacles.map(({ z }) => z)).toEqual(encounterPositions);
      contentSignatures.add(simulation.obstacles.map((obstacle) => [
        obstacle.kind,
        obstacle.phraseKind,
        obstacle.x,
        obstacle.y,
        obstacle.kind === "membrane" ? obstacle.phase : null,
      ]).join("|"));
    }

    expect(contentSignatures.size).toBeGreaterThan(20);
    expect(obstacleCadenceJitter(1)).not.toBe(obstacleCadenceJitter(2));
  });

  it("provides more than four seconds before the opening obstacle can touch the player", () => {
    let simulation = createSimulation("opening-window");
    const firstObstacle = simulation.obstacles.reduce((closest, obstacle) =>
      obstacle.z > closest.z ? obstacle : closest,
    );
    const contactZ = -firstObstacle.depth / 2 - simulation.player.radius;

    for (let frame = 0; frame < 600; frame += 1) {
      const current = simulation.obstacles.find(({ id }) => id === firstObstacle.id);
      if (!current || current.z >= contactZ) {
        break;
      }
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    }

    expect(simulation.obstacles.find(({ id }) => id === firstObstacle.id)).toBeDefined();
    expect(simulation.elapsed).toBeGreaterThanOrEqual(4.25);
  });

  it("recycles hazards with a phone-friendly reaction window at redline", () => {
    let simulation = createSimulation("redline-spacing");
    simulation.elapsed = 100;
    simulation.speed = speedForElapsed(simulation.elapsed);
    simulation.obstacles = simulation.obstacles.slice(0, 7).map((obstacle, index) => ({
      ...obstacle,
      z: -80 - index * 75,
    }));
    const existingIds = new Set(simulation.obstacles.map(({ id }) => id));

    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);

    const recycled = simulation.obstacles.find(({ id }) => !existingIds.has(id));
    const farthestExistingZ = Math.min(
      ...simulation.obstacles
        .filter(({ id }) => existingIds.has(id))
        .map(({ z }) => z),
    );
    expect(recycled).toBeDefined();
    const gap = farthestExistingZ - (recycled?.z ?? farthestExistingZ);
    expect(gap).toBeGreaterThanOrEqual(minimumObstacleSpacingForSpeed(MAX_SPEED));
    expect(gap / simulation.speed).toBeGreaterThanOrEqual(
      MINIMUM_OBSTACLE_REACTION_SECONDS,
    );
  });

  it("expands the phrase vocabulary by sector while preserving teaching singles", () => {
    expect(eligiblePhraseKindsForSector(1)).toEqual([
      "solo-block",
      "solo-membrane",
    ]);
    expect(eligiblePhraseKindsForSector(2)).toEqual([
      "solo-block",
      "solo-membrane",
      "slalom",
      "phase-pulse",
    ]);
    expect(eligiblePhraseKindsForSector(3)).toContain("cross-weave");
    expect(eligiblePhraseKindsForSector(3)).not.toContain("redline-cascade");
    expect(eligiblePhraseKindsForSector(4)).toContain("redline-cascade");

    const opening = createSimulation("phrase-tutorial");
    const firstPhraseId = opening.activePhrase?.id;
    const openingPhrase = opening.obstacles.filter(
      ({ phraseId }) => phraseId === firstPhraseId,
    );
    expect(openingPhrase).toHaveLength(1);
    expect(openingPhrase[0]?.phraseKind).toMatch(/^solo-/);
  });

  it("selects seeded phrases deterministically without immediate repetition", () => {
    const collectKinds = (seed: string): SignalPhraseKind[] => {
      let simulation = createSimulation(seed);
      const kinds: SignalPhraseKind[] = [];
      let observedSequence = 0;
      for (let frame = 0; frame < 60 * 150 && kinds.length < 18; frame += 1) {
        makeHazardsSafe(simulation);
        simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
        const event = simulation.lastPhraseEvent;
        if (event && event.sequence > observedSequence) {
          observedSequence = event.sequence;
          expect(
            eligiblePhraseKindsForSector(sectorForElapsed(simulation.elapsed)),
          ).toContain(event.phraseKind);
          kinds.push(event.phraseKind);
        }
      }
      return kinds;
    };

    const first = collectKinds("phrase-order");
    const replay = collectKinds("phrase-order");
    const alternate = collectKinds("phrase-order-alternate");
    expect(first.length).toBeGreaterThanOrEqual(12);
    expect(replay).toEqual(first);
    expect(alternate).not.toEqual(first);
    for (let index = 1; index < first.length; index += 1) {
      expect(first[index]).not.toBe(first[index - 1]);
    }
  });

  it("guarantees a movement check within three Sector 2+ phrases", () => {
    let simulation = createSimulation("movement-check-cadence");
    let observedSequence = 0;
    let phrasesWithoutMovement = 0;
    let movementChecks = 0;

    for (let frame = 0; frame < 60 * 150; frame += 1) {
      makeHazardsSafe(simulation);
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
      expect(simulation.phrasesSinceMovementCheck).toBeLessThanOrEqual(
        MAX_PHRASES_WITHOUT_MOVEMENT_CHECK,
      );

      const event = simulation.lastPhraseEvent;
      if (!event || event.sequence <= observedSequence) continue;
      observedSequence = event.sequence;
      if (sectorForElapsed(simulation.elapsed) < 2) continue;
      if (event.phraseKind === "slalom") {
        movementChecks += 1;
        phrasesWithoutMovement = 0;
      } else {
        phrasesWithoutMovement += 1;
        expect(phrasesWithoutMovement).toBeLessThanOrEqual(
          MAX_PHRASES_WITHOUT_MOVEMENT_CHECK,
        );
      }
    }

    expect(movementChecks).toBeGreaterThan(4);
  });

  it("covers every static perimeter position while leaving fair baffle corridors", () => {
    const left = movementBaffle(
      "left-baffle",
      -MOVEMENT_CHECK_BAFFLE_CENTER_X,
      0,
      1,
    );
    const right = movementBaffle(
      "right-baffle",
      MOVEMENT_CHECK_BAFFLE_CENTER_X,
      0,
      2,
    );
    const playerAt = (x: number, y: number): PlayerState => ({
      position: { x, y },
      velocity: { x: 0, y: 0 },
      radius: 1.7,
    });

    for (let sample = 0; sample < 144; sample += 1) {
      const angle = (sample / 144) * Math.PI * 2;
      const perimeterPlayer = playerAt(
        Math.cos(angle) * PLAYER_BOUNDARY_RADIUS,
        Math.sin(angle) * PLAYER_VERTICAL_BOUNDARY_RADIUS,
      );
      expect(
        playerIntersectsBlock(perimeterPlayer, left) ||
          playerIntersectsBlock(perimeterPlayer, right),
      ).toBe(true);
    }

    expect(playerIntersectsBlock(playerAt(1, 0), left)).toBe(false);
    expect(playerIntersectsBlock(playerAt(-1, 0), right)).toBe(false);
  });

  it("allows a full opposite-side baffle transition at the redline reaction floor", () => {
    const runBaffles = (frameRate: number) => {
      let simulation = createSimulation("redline-baffle-reachability");
      simulation.elapsed = 100;
      simulation.speed = MAX_SPEED;
      simulation.player.position = { x: PLAYER_BOUNDARY_RADIUS, y: 0 };
      simulation.player.velocity = { x: 0, y: 0 };
      simulation.phraseProgress = [];
      simulation.pendingPhrase = null;

      const spacing = minimumObstacleSpacingForSpeed(MAX_SPEED);
      const baffles = [
        movementBaffle("baffle-1", -MOVEMENT_CHECK_BAFFLE_CENTER_X, -0.25, 1),
        movementBaffle(
          "baffle-2",
          MOVEMENT_CHECK_BAFFLE_CENTER_X,
          -0.25 - spacing,
          2,
        ),
        movementBaffle(
          "baffle-3",
          -MOVEMENT_CHECK_BAFFLE_CENTER_X,
          -0.25 - spacing * 2,
          3,
        ),
      ];
      simulation.obstacles = [
        ...baffles,
        ...simulation.obstacles.slice(3).map((obstacle, index) => ({
          ...obstacle,
          z: -1_000 - index * 100,
        })),
      ];

      const passPositions: number[] = [];
      const observedPasses = new Set<string>();
      for (let frame = 0; frame < frameRate * 6; frame += 1) {
        const nextBaffle = simulation.obstacles
          .filter(({ phraseId, passed }) => phraseId === "movement-check" && !passed)
          .sort((first, second) => second.z - first.z)[0];
        const inputX = nextBaffle ? (nextBaffle.x < 0 ? 1 : -1) : 0;
        simulation = stepSimulation(
          simulation,
          { x: inputX, y: 0, phaseToggle: false },
          1 / frameRate,
        );
        for (const obstacle of simulation.obstacles) {
          if (
            obstacle.phraseId === "movement-check" &&
            obstacle.passed &&
            !observedPasses.has(obstacle.id)
          ) {
            observedPasses.add(obstacle.id);
            passPositions.push(simulation.player.position.x);
          }
        }
      }
      return { simulation, passPositions };
    };

    const sixty = runBaffles(60);
    const oneTwenty = runBaffles(120);
    expect(sixty.simulation.integrity).toBe(3);
    expect(sixty.passPositions).toHaveLength(3);
    expect(sixty.passPositions[0]).toBeGreaterThan(0.7);
    expect(sixty.passPositions[1]).toBeLessThan(-0.7);
    expect(sixty.passPositions[2]).toBeGreaterThan(0.7);
    expect(oneTwenty).toEqual(sixty);
    expect(
      minimumObstacleSpacingForSpeed(MAX_SPEED) / MAX_SPEED,
    ).toBe(MINIMUM_OBSTACLE_REACTION_SECONDS);
  });

  it("defeats perimeter camping across 100 deterministic seeds", () => {
    for (let seed = 0; seed < 100; seed += 1) {
      let simulation = createSimulation("perimeter-camp-" + seed);
      for (
        let frame = 0;
        frame < 60 * 45 && simulation.status === "running";
        frame += 1
      ) {
        const nextMembrane = simulation.obstacles
          .filter((obstacle): obstacle is MembraneObstacle =>
            obstacle.kind === "membrane" && !obstacle.passed,
          )
          .sort((first, second) => second.z - first.z)[0];
        const phaseToggle = Boolean(
          nextMembrane &&
            nextMembrane.z > -9 &&
            nextMembrane.phase !== simulation.phase &&
            simulation.phaseCooldown === 0,
        );
        simulation = stepSimulation(
          simulation,
          { x: 0, y: 1, phaseToggle },
          FIXED_STEP_SECONDS,
        );
      }

      expect(simulation.status, "seed " + seed).toBe("crashed");
      expect(
        simulation.obstacles.some(
          (obstacle) => obstacle.hit && obstacle.phraseKind === "slalom",
        ),
        "seed " + seed,
      ).toBe(true);
    }
  });

  it("awards clean phrases and breaks damaged phrases without duplicate events", () => {
    const cleanStart = createSimulation("clean-phrase");
    const cleanPhraseId = cleanStart.activePhrase?.id;
    expect(cleanPhraseId).toBeTruthy();
    const clean = advanceToNextPhraseEvent(cleanStart);

    expect(clean.phrasesCompleted).toBe(1);
    expect(clean.cleanPhrases).toBe(1);
    expect(clean.cleanPhraseStreak).toBe(1);
    expect(clean.peakCleanPhraseStreak).toBe(1);
    expect(clean.resonancePips).toBe(1);
    expect(clean.lastPhraseEvent).toMatchObject({
      sequence: 1,
      phraseId: cleanPhraseId,
      result: "clean",
      cleanStreak: 1,
      scoreBonus: 240,
      resonanceStarted: false,
    });
    const cleanAfterOneTick = stepSimulation(clean, idleInput, FIXED_STEP_SECONDS);
    expect(cleanAfterOneTick.phraseEventSequence).toBe(1);

    const brokenStart = createSimulation("broken-phrase");
    const brokenPhraseId = brokenStart.activePhrase?.id;
    expect(brokenPhraseId).toBeTruthy();
    const broken = advanceToNextPhraseEvent(brokenStart, brokenPhraseId);
    expect(broken.phrasesCompleted).toBe(1);
    expect(broken.cleanPhrases).toBe(0);
    expect(broken.cleanPhraseStreak).toBe(0);
    expect(broken.peakCleanPhraseStreak).toBe(0);
    expect(broken.resonancePips).toBe(0);
    expect(broken.lastPhraseEvent).toMatchObject({
      sequence: 1,
      phraseId: brokenPhraseId,
      result: "broken",
      cleanStreak: 0,
      scoreBonus: 0,
      resonanceStarted: false,
    });
  });

  it("rewards one clean three-beat phrase like three one-beat phrases at equal depth", () => {
    const commonState = {
      cleanStreak: 1,
      peakCleanStreak: 1,
      resonancePips: 0,
    };
    const threeBeat = stepSimulation(
      controlledPhraseState("equal-risk-reward", [3], commonState),
      idleInput,
      FIXED_STEP_SECONDS,
    );
    const threeSingles = stepSimulation(
      controlledPhraseState("equal-risk-reward", [1, 1, 1], commonState),
      idleInput,
      FIXED_STEP_SECONDS,
    );

    expect(threeBeat.distance).toBe(threeSingles.distance);
    expect(threeBeat.score).toBe(threeSingles.score);
    expect(threeBeat.cleanPhraseStreak).toBe(4);
    expect(threeBeat.cleanPhraseStreak).toBe(threeSingles.cleanPhraseStreak);
    expect(threeBeat.peakCleanPhraseStreak).toBe(
      threeSingles.peakCleanPhraseStreak,
    );
    expect(threeBeat.resonancePips).toBe(0);
    expect(threeBeat.resonancePips).toBe(threeSingles.resonancePips);
    expect(threeBeat.resonanceActivations).toBe(1);
    expect(threeBeat.resonanceActivations).toBe(
      threeSingles.resonanceActivations,
    );
    expect(threeBeat.lastPhraseEvent).toMatchObject({
      result: "clean",
      cleanStreak: 4,
      scoreBonus: 2_160,
      resonanceStarted: true,
    });

    // Run statistics remain literal phrase counts even though reward uses risk units.
    expect(threeBeat.cleanPhrases).toBe(1);
    expect(threeBeat.phrasesCompleted).toBe(1);
    expect(threeSingles.cleanPhrases).toBe(3);
    expect(threeSingles.phrasesCompleted).toBe(3);
  });

  it("banks clean beats before a later beat breaks the phrase", () => {
    let grouped = controlledPhraseState("clean-clean-hit", [3]);
    let singles = controlledPhraseState("clean-clean-hit", [1, 1, 1]);

    for (const simulation of [grouped, singles]) {
      simulation.obstacles.forEach((obstacle, index) => {
        obstacle.z = [1, -10, -25][index] ?? -25;
        if (index === 2 && obstacle.kind === "block") {
          obstacle.x = 0;
          obstacle.y = 0;
          obstacle.width = 0.2;
          obstacle.height = 0.2;
        }
      });
    }

    for (let frame = 0; frame < 300; frame += 1) {
      grouped = stepSimulation(grouped, idleInput, FIXED_STEP_SECONDS);
      singles = stepSimulation(singles, idleInput, FIXED_STEP_SECONDS);
      const groupedProgress = grouped.phraseProgress.find(
        ({ id }) => id === "controlled-0",
      );
      if (groupedProgress?.passedBeats === 2) break;
    }

    const interimProgress = grouped.phraseProgress.find(
      ({ id }) => id === "controlled-0",
    );
    expect(interimProgress).toMatchObject({
      passedBeats: 2,
      damaged: false,
      scoreBonus: 720,
    });
    expect(grouped.score).toBeCloseTo(singles.score, 10);
    expect(grouped.cleanPhraseStreak).toBe(2);
    expect(grouped.resonancePips).toBe(2);
    const bankedScore = grouped.score;

    for (let frame = 0; frame < 300; frame += 1) {
      grouped = stepSimulation(grouped, idleInput, FIXED_STEP_SECONDS);
      singles = stepSimulation(singles, idleInput, FIXED_STEP_SECONDS);
      if (grouped.phrasesCompleted >= 1 && singles.phrasesCompleted >= 3) break;
    }

    expect(grouped.distance).toBeCloseTo(singles.distance, 10);
    expect(grouped.score).toBeCloseTo(singles.score, 10);
    expect(grouped.score).toBeGreaterThanOrEqual(bankedScore);
    expect(grouped.integrity).toBe(2);
    expect(grouped.combo).toBe(1);
    expect(grouped.cleanPhraseStreak).toBe(0);
    expect(grouped.resonancePips).toBe(0);
    expect(grouped.lastPhraseEvent).toMatchObject({
      result: "broken",
      cleanStreak: 0,
      scoreBonus: 720,
      resonanceStarted: false,
    });
  });

  it("starts resonance on the earning beat before a long phrase resolves", () => {
    let simulation = controlledPhraseState("mid-phrase-resonance", [3], {
      resonancePips: 2,
    });
    simulation.obstacles.forEach((obstacle, index) => {
      obstacle.z = [1, -40, -80][index] ?? -80;
    });

    for (let frame = 0; frame < 120; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
      const progress = simulation.phraseProgress.find(
        ({ id }) => id === "controlled-0",
      );
      if (progress?.passedBeats === 1) break;
    }

    expect(simulation.phraseEventSequence).toBe(0);
    expect(simulation.phrasesCompleted).toBe(0);
    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.resonanceRemaining).toBe(RESONANCE_DURATION_SECONDS);
    expect(simulation.resonancePips).toBe(0);
    expect(simulation.cleanPhraseStreak).toBe(1);
    expect(
      simulation.phraseProgress.find(({ id }) => id === "controlled-0"),
    ).toMatchObject({
      passedBeats: 1,
      scoreBonus: 240,
    });
  });

  it("keeps a delayed phrase reward visible after resonance starts on an earlier beat", () => {
    let simulation = controlledPhraseState("early-resonance-feedback", [3], {
      resonancePips: 2,
    });
    simulation.obstacles.forEach((obstacle, index) => {
      obstacle.z = [1, -40, -80][index] ?? -80;
    });

    for (let frame = 0; frame < 120; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
      const progress = simulation.phraseProgress.find(
        ({ id }) => id === "controlled-0",
      );
      if (progress?.passedBeats === 1) break;
    }
    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.phraseEventSequence).toBe(0);

    for (const obstacle of simulation.obstacles) {
      if (obstacle.phraseId === "controlled-0" && !obstacle.passed) obstacle.z = 3;
    }
    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);

    expect(simulation.lastPhraseEvent).toMatchObject({
      result: "clean",
      cleanStreak: 3,
      resonanceStarted: false,
    });
    expect(simulation.lastPhraseEvent?.scoreBonus).toBeGreaterThan(0);
  });

  it("marks resonance only when it starts on the resolving beat", () => {
    const simulation = stepSimulation(
      controlledPhraseState("final-beat-resonance-feedback", [3]),
      idleInput,
      FIXED_STEP_SECONDS,
    );

    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.lastPhraseEvent).toMatchObject({
      result: "clean",
      resonanceStarted: true,
    });
  });

  it("reports recovery after a phrase breaks following an early resonance", () => {
    let simulation = controlledPhraseState("broken-after-resonance", [3], {
      resonancePips: 2,
    });
    simulation.obstacles.forEach((obstacle, index) => {
      obstacle.z = [1, -40, -80][index] ?? -80;
    });
    for (let frame = 0; frame < 120; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
      const progress = simulation.phraseProgress.find(
        ({ id }) => id === "controlled-0",
      );
      if (progress?.passedBeats === 1) break;
    }
    const progress = simulation.phraseProgress.find(
      ({ id }) => id === "controlled-0",
    );
    expect(progress).toBeTruthy();
    if (progress) progress.damaged = true;
    simulation.cleanPhraseStreak = 0;
    simulation.resonancePips = 0;

    for (const obstacle of simulation.obstacles) {
      if (obstacle.phraseId === "controlled-0" && !obstacle.passed) obstacle.z = 3;
    }
    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);

    expect(simulation.lastPhraseEvent).toMatchObject({
      result: "broken",
      resonanceStarted: false,
    });
    expect(simulation.lastPhraseEvent?.scoreBonus).toBeGreaterThan(0);
  });

  it("gives equally clean content seeds the same score opportunities", () => {
    const first = advanceSafely(createSimulation("fairness-272"), 58);
    const second = advanceSafely(createSimulation("fairness-371"), 58);

    expect(first.distance).toBeCloseTo(second.distance, 10);
    expect(first.cleanPhraseStreak).toBe(second.cleanPhraseStreak);
    expect(first.integrity).toBe(3);
    expect(second.integrity).toBe(3);
    expect(first.resonanceActivations).toBe(second.resonanceActivations);
    expect(first.score).toBeCloseTo(second.score, 10);
  });

  it("removes the known random-cadence personal-best advantage", () => {
    const first = advanceSafely(createSimulation("audit-165"), 32);
    const second = advanceSafely(createSimulation("audit-606"), 32);

    expect(first.distance).toBeCloseTo(second.distance, 10);
    expect(first.cleanPhraseStreak).toBe(second.cleanPhraseStreak);
    expect(first.resonanceActivations).toBe(second.resonanceActivations);
    expect(first.score).toBeCloseTo(second.score, 10);
  });

  it("keeps perfect-play scoring identical across a content-seed sweep", () => {
    const runs = Array.from({ length: 24 }, (_, index) =>
      advanceSafely(createSimulation(`score-cadence-${index}`), 32),
    );
    const baseline = runs[0];

    for (const run of runs.slice(1)) {
      expect(run.distance).toBeCloseTo(baseline.distance, 10);
      expect(run.cleanPhraseStreak).toBe(baseline.cleanPhraseStreak);
      expect(run.resonanceActivations).toBe(baseline.resonanceActivations);
      expect(run.score).toBeCloseTo(baseline.score, 10);
    }
  });

  it("preserves modulo-three charge and gives broken multi-beat phrases no credit", () => {
    const charged = stepSimulation(
      controlledPhraseState("risk-charge-remainder", [3], {
        cleanStreak: 2,
        resonancePips: 2,
      }),
      idleInput,
      FIXED_STEP_SECONDS,
    );

    expect(charged.cleanPhraseStreak).toBe(5);
    expect(charged.resonancePips).toBe(2);
    expect(charged.resonanceActivations).toBe(1);
    expect(charged.resonanceRemaining).toBe(RESONANCE_DURATION_SECONDS);

    const brokenStart = controlledPhraseState("broken-risk-credit", [3], {
      cleanStreak: 5,
      peakCleanStreak: 5,
      resonancePips: 2,
      damaged: true,
    });
    brokenStart.score = 1_000;
    const broken = stepSimulation(
      brokenStart,
      idleInput,
      FIXED_STEP_SECONDS,
    );

    expect(broken.lastPhraseEvent).toMatchObject({
      result: "broken",
      cleanStreak: 0,
      scoreBonus: 0,
      resonanceStarted: false,
    });
    expect(broken.score - brokenStart.score).toBeCloseTo(
      broken.distance - brokenStart.distance,
      10,
    );
    expect(broken.cleanPhrases).toBe(0);
    expect(broken.resonancePips).toBe(0);
    expect(broken.resonanceActivations).toBe(0);
  });

  it("keeps normalized phrase rewards deterministic at 60 and 120 Hz", () => {
    const sixtyStart = controlledPhraseState("risk-frame-rate", [3], {
      cleanStreak: 1,
      resonancePips: 2,
    });
    const oneTwentyStart = controlledPhraseState("risk-frame-rate", [3], {
      cleanStreak: 1,
      resonancePips: 2,
    });
    const sixty = stepSimulation(
      sixtyStart,
      idleInput,
      FIXED_STEP_SECONDS,
    );
    const oneTwentyPartial = stepSimulation(
      oneTwentyStart,
      idleInput,
      FIXED_STEP_SECONDS / 2,
    );
    const oneTwenty = stepSimulation(
      oneTwentyPartial,
      idleInput,
      FIXED_STEP_SECONDS / 2,
    );

    expect(oneTwenty).toEqual(sixty);
  });

  it("activates resonance after three clean risk units and expires after six seconds", () => {
    let simulation = createSimulation("resonance-activation");
    while (simulation.resonanceActivations === 0) {
      simulation = advanceToNextPhraseEvent(simulation);
    }

    expect(simulation.cleanPhraseStreak).toBeGreaterThanOrEqual(
      RESONANCE_PIPS_REQUIRED,
    );
    expect(simulation.resonancePips).toBe(
      simulation.cleanPhraseStreak % RESONANCE_PIPS_REQUIRED,
    );
    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.resonanceRemaining).toBe(RESONANCE_DURATION_SECONDS);
    expect(simulation.lastPhraseEvent?.resonanceStarted).toBe(true);
    const activationEventSequence = simulation.phraseEventSequence;

    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    expect(simulation.resonanceActivations).toBe(1);
    expect(simulation.phraseEventSequence).toBe(activationEventSequence);
    expect(simulation.resonanceRemaining).toBeCloseTo(
      RESONANCE_DURATION_SECONDS - FIXED_STEP_SECONDS,
      10,
    );

    simulation = quietSimulation("resonance-expiry");
    simulation.resonanceRemaining = RESONANCE_DURATION_SECONDS;
    simulation = advanceSafely(
      simulation,
      RESONANCE_DURATION_SECONDS - FIXED_STEP_SECONDS,
    );
    expect(simulation.resonanceRemaining).toBeGreaterThan(0);
    simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    expect(simulation.resonanceRemaining).toBe(0);
  });

  it("banks clean risk units during resonance and refreshes every third unit", () => {
    let simulation = controlledPhraseState("res-truth-3", [1, 1, 1], {
      cleanStreak: 3,
      peakCleanStreak: 3,
      resonanceRemaining: 3,
    });
    simulation.resonanceActivations = 1;
    for (const [index, obstacle] of simulation.obstacles.entries()) {
      obstacle.z = -100 - index * 10;
    }

    const resolveControlledPhrase = (index: number): void => {
      const obstacle = simulation.obstacles.find(
        ({ id }) => id === `controlled-obstacle-${index}`,
      );
      expect(obstacle).toBeTruthy();
      if (obstacle) obstacle.z = 3;
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    };

    resolveControlledPhrase(0);
    expect(simulation.cleanPhrases).toBe(1);
    expect(simulation.resonanceRemaining).toBeGreaterThan(0);
    expect(simulation.resonancePips).toBe(1);

    resolveControlledPhrase(1);
    expect(simulation.cleanPhrases).toBe(2);
    expect(simulation.resonancePips).toBe(2);

    resolveControlledPhrase(2);
    expect(simulation.cleanPhrases).toBe(3);
    expect(simulation.resonancePips).toBe(0);
    expect(simulation.resonanceActivations).toBe(2);
    expect(simulation.resonanceRemaining).toBe(RESONANCE_DURATION_SECONDS);
    expect(simulation.lastPhraseEvent?.resonanceStarted).toBe(true);

    const expiring = quietSimulation("banked-charge-expiry");
    expiring.resonancePips = 1;
    expiring.resonanceRemaining = FIXED_STEP_SECONDS;
    const expired = stepSimulation(expiring, idleInput, FIXED_STEP_SECONDS);
    expect(expired.resonanceRemaining).toBe(0);
    expect(expired.resonancePips).toBe(1);
  });

  it("resets a banked resonance charge when its phrase is broken", () => {
    let simulation = createSimulation("broken-banked-charge");
    simulation.resonancePips = 2;
    simulation.resonanceRemaining = 3;
    const phraseId = simulation.activePhrase?.id;
    expect(phraseId).toBeTruthy();

    simulation = advanceToNextPhraseEvent(simulation, phraseId);
    expect(simulation.lastPhraseEvent?.result).toBe("broken");
    expect(simulation.resonancePips).toBe(0);
  });

  it("doubles only scoring during resonance and remains deterministic at 60 and 120 Hz", () => {
    const normalStart = quietSimulation("score-only-resonance");
    const boostedStart = quietSimulation("score-only-resonance");
    boostedStart.resonanceRemaining = RESONANCE_DURATION_SECONDS;
    expect(scoreMultiplierForSimulation(normalStart)).toBe(1);
    expect(scoreMultiplierForSimulation(boostedStart)).toBe(
      RESONANCE_SCORE_MULTIPLIER,
    );

    const normal = advanceSafely(normalStart, 1);
    const boosted = advanceSafely(boostedStart, 1);
    expect(boosted.score).toBeCloseTo(normal.score * RESONANCE_SCORE_MULTIPLIER, 8);
    expect(boosted.speed).toBe(normal.speed);
    expect(boosted.distance).toBe(normal.distance);
    expect(boosted.player).toEqual(normal.player);
    expect(boosted.obstacles).toEqual(normal.obstacles);

    const sixtyStart = createSimulation("resonance-frame-rate");
    const oneTwentyStart = createSimulation("resonance-frame-rate");
    sixtyStart.resonanceRemaining = RESONANCE_DURATION_SECONDS;
    oneTwentyStart.resonanceRemaining = RESONANCE_DURATION_SECONDS;
    const sixty = advanceSafely(sixtyStart, 8, 60);
    const oneTwenty = advanceSafely(oneTwentyStart, 8, 120);
    expect(oneTwenty).toEqual(sixty);
  });

  it("is deterministic for a seed and stable across common render frame rates", () => {
    let sixtyFps = createSimulation("signal-run");
    let oneTwentyFps = createSimulation("signal-run");
    const original = createSimulation("signal-run");

    for (let frame = 0; frame < 120; frame += 1) {
      sixtyFps = stepSimulation(
        sixtyFps,
        { x: 0.4, y: -0.25, phaseToggle: frame === 18 },
        1 / 60,
      );
    }
    for (let frame = 0; frame < 240; frame += 1) {
      oneTwentyFps = stepSimulation(
        oneTwentyFps,
        { x: 0.4, y: -0.25, phaseToggle: frame === 36 },
        1 / 120,
      );
    }

    expect(oneTwentyFps).toEqual(sixtyFps);
    expect(createSimulation("signal-run")).toEqual(original);
    expect(createSimulation("another-run").obstacles).not.toEqual(original.obstacles);
    expect(resetSimulation("signal-run")).toEqual(original);
  });

  it("keeps the player inside the elliptical tunnel and removes outward velocity", () => {
    let simulation = quietSimulation("boundary");
    for (let frame = 0; frame < 120; frame += 1) {
      simulation = stepSimulation(
        simulation,
        { x: 1, y: 1, phaseToggle: false },
        FIXED_STEP_SECONDS,
      );
    }

    const { position, velocity } = simulation.player;
    const ellipticalDistance = Math.hypot(
      position.x / PLAYER_BOUNDARY_RADIUS,
      position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS,
    );
    const normalX = position.x / PLAYER_BOUNDARY_RADIUS ** 2;
    const normalY = position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS ** 2;
    const outwardVelocity = normalX * velocity.x + normalY * velocity.y;
    expect(ellipticalDistance).toBeLessThanOrEqual(1 + 1e-9);
    expect(outwardVelocity).toBeLessThanOrEqual(1e-9);
  });

  it("clamps horizontal, vertical, and diagonal movement against the craft ellipse", () => {
    const player = (x: number, y: number, velocityX = x, velocityY = y): PlayerState => ({
      position: { x, y },
      velocity: { x: velocityX, y: velocityY },
      radius: 1.7,
    });

    const horizontal = clampPlayerToTunnel(player(20, 0));
    const vertical = clampPlayerToTunnel(player(0, 20));
    const diagonal = clampPlayerToTunnel(
      player(PLAYER_BOUNDARY_RADIUS, PLAYER_VERTICAL_BOUNDARY_RADIUS),
    );

    expect(horizontal.position.x).toBeCloseTo(PLAYER_BOUNDARY_RADIUS, 10);
    expect(horizontal.position.y).toBe(0);
    expect(vertical.position.x).toBe(0);
    expect(vertical.position.y).toBeCloseTo(PLAYER_VERTICAL_BOUNDARY_RADIUS, 10);
    expect(
      (diagonal.position.x / PLAYER_BOUNDARY_RADIUS) ** 2 +
        (diagonal.position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS) ** 2,
    ).toBeCloseTo(1, 10);

    for (const clamped of [horizontal, vertical, diagonal]) {
      const normalX = clamped.position.x / PLAYER_BOUNDARY_RADIUS ** 2;
      const normalY = clamped.position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS ** 2;
      expect(
        clamped.velocity.x * normalX + clamped.velocity.y * normalY,
      ).toBeLessThanOrEqual(1e-10);
    }
  });

  it("allows a matching membrane and damages on a mismatched crossing", () => {
    const matching = createSimulation("matching");
    matching.obstacles = [membrane("membrane-1", -0.25, "ember")];
    const matched = stepSimulation(matching, idleInput, FIXED_STEP_SECONDS);

    const mismatching = createSimulation("mismatching");
    mismatching.obstacles = [membrane("membrane-1", -0.25, "cobalt")];
    const mismatched = stepSimulation(mismatching, idleInput, FIXED_STEP_SECONDS);

    expect(matched.integrity).toBe(3);
    expect(matched.obstacles.find(({ id }) => id === "membrane-1")?.hit).toBe(false);
    expect(mismatched.integrity).toBe(2);
    expect(mismatched.invulnerability).toBe(HIT_INVULNERABILITY_SECONDS);
    expect(mismatched.obstacles.find(({ id }) => id === "membrane-1")?.hit).toBe(true);
  });

  it("commits an armed re-entry phase before the first resumed collision", () => {
    const paused = createSimulation("resume-phase-ordering");
    paused.phase = "ember";
    paused.phaseCooldown = PHASE_TOGGLE_COOLDOWN_SECONDS;
    paused.obstacles = [membrane("membrane-1", -0.25, "cobalt")];

    const resumed = commitPrimedInput(paused, true);
    expect(paused.phase).toBe("ember");
    expect(paused.phaseCooldown).toBe(PHASE_TOGGLE_COOLDOWN_SECONDS);
    expect(resumed.phase).toBe("cobalt");
    expect(resumed.phaseCooldown).toBe(PHASE_TOGGLE_COOLDOWN_SECONDS);
    expect(resumed.pendingPhaseToggle).toBe(false);

    const afterFirstWorldTick = stepSimulation(
      resumed,
      idleInput,
      FIXED_STEP_SECONDS,
    );
    expect(afterFirstWorldTick.integrity).toBe(3);
    expect(
      afterFirstWorldTick.obstacles.find(({ id }) => id === "membrane-1")?.hit,
    ).toBe(false);
  });

  it("lets the frozen re-entry buffer recover cooldown without changing phase", () => {
    const paused = createSimulation("resume-cooldown-recovery");
    paused.phase = "ember";
    paused.phaseCooldown = PHASE_TOGGLE_COOLDOWN_SECONDS;

    const resumed = commitPrimedInput(paused, false);

    expect(paused.phaseCooldown).toBe(PHASE_TOGGLE_COOLDOWN_SECONDS);
    expect(resumed.phase).toBe("ember");
    expect(resumed.phaseCooldown).toBe(0);
    expect(resumed.pendingPhaseToggle).toBe(false);
  });

  it("enforces the phase-toggle cooldown", () => {
    let simulation = quietSimulation("toggle");
    simulation = stepSimulation(
      simulation,
      { ...idleInput, phaseToggle: true },
      FIXED_STEP_SECONDS,
    );
    expect(simulation.phase).toBe("cobalt");

    simulation = stepSimulation(
      simulation,
      { ...idleInput, phaseToggle: true },
      FIXED_STEP_SECONDS,
    );
    expect(simulation.phase).toBe("cobalt");
    expect(simulation.pendingPhaseToggle).toBe(true);

    const cooldownFrames = Math.ceil(
      PHASE_TOGGLE_COOLDOWN_SECONDS / FIXED_STEP_SECONDS,
    );
    for (let frame = 0; frame < cooldownFrames; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    }
    expect(simulation.phase).toBe("ember");
    expect(simulation.pendingPhaseToggle).toBe(false);
  });

  it("crashes after three spaced hits rather than repeated overlap damage", () => {
    let simulation = createSimulation("three-hits");
    simulation.obstacles = [
      membrane("membrane-101", -0.25, "cobalt"),
      membrane("membrane-102", -22, "cobalt"),
      membrane("membrane-103", -44, "cobalt"),
    ];
    let registeredHits = 0;
    let previousIntegrity = simulation.integrity;

    for (let frame = 0; frame < 360 && simulation.status === "running"; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
      if (simulation.integrity < previousIntegrity) {
        registeredHits += previousIntegrity - simulation.integrity;
        previousIntegrity = simulation.integrity;
      }
    }

    expect(registeredHits).toBe(3);
    expect(simulation.integrity).toBe(0);
    expect(simulation.status).toBe("crashed");
  });

  it("awards distance, score, and combo for a clean pass", () => {
    let simulation = createSimulation("scoring");
    simulation.obstacles = [membrane("membrane-1", -0.25, "ember")];
    for (let frame = 0; frame < 24; frame += 1) {
      simulation = stepSimulation(simulation, idleInput, FIXED_STEP_SECONDS);
    }

    expect(simulation.distance).toBeGreaterThan(0);
    expect(simulation.combo).toBe(1.25);
    expect(simulation.score).toBeGreaterThan(simulation.distance);
    expect(simulation.obstacles.find(({ id }) => id === "membrane-1")?.passed).toBe(true);
  });

  it("exposes block and membrane collision helpers for the renderer", () => {
    const simulation = createSimulation("collisions");
    const block: BlockObstacle = {
      id: "block-test",
      poolSlot: 0,
      phraseId: "test-block",
      phraseKind: "solo-block",
      phraseBeat: 1,
      phraseLength: 1,
      kind: "block",
      x: 0,
      y: 0,
      z: 0,
      width: 2,
      height: 2,
      depth: 2,
      passed: false,
      hit: false,
    };
    expect(
      sphereIntersectsAabb({ x: 0, y: 0, z: 0, radius: 0.5 }, block),
    ).toBe(true);
    expect(
      sphereIntersectsAabb({ x: 4, y: 0, z: 0, radius: 0.5 }, block),
    ).toBe(false);

    const visuallyClearAbove: BlockObstacle = { ...block, y: 2.1 };
    expect(
      sphereIntersectsAabb({ x: 0, y: 0, z: 0, radius: simulation.player.radius }, visuallyClearAbove),
    ).toBe(true);
    expect(playerIntersectsBlock(simulation.player, visuallyClearAbove)).toBe(false);

    const gate = membrane("membrane-test", 0.1, "ember");
    expect(obstacleCollidesWithPlayer(simulation.player, gate, "ember", -0.1)).toBe(false);
    expect(obstacleCollidesWithPlayer(simulation.player, gate, "cobalt", -0.1)).toBe(true);
  });
});
