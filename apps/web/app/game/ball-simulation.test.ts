import { describe, expect, it } from "vitest";
import {
  BALL_CONTRACT_DURATION_SECONDS,
  BALL_CONTRACT_TICKS,
  BALL_FIXED_STEP_SECONDS,
  BALL_INITIAL_SHIELDS,
  BALL_MAX_SPEED,
  BALL_MINIMUM_REACTION_SECONDS,
  BALL_OBSTACLE_POOL_SIZE,
  BALL_OVERDRIVE_DURATION_SECONDS,
  BALL_OVERDRIVE_GATES_REQUIRED,
  BALL_PLAY_RADIUS,
  BALL_RADIUS,
  BALL_TUTORIAL_BLUEPRINTS,
  ballFitsGate,
  ballImpactNormalForBlock,
  ballPaceForElapsed,
  ballSpeedForElapsed,
  ballSphereIntersectsBlock,
  clampBallToTunnel,
  createBallSimulation,
  resetBallSimulation,
  stepBallSimulation,
  type BallBlockObstacle,
  type BallGateObstacle,
  type BallInput,
  type BallObstacle,
  type BallSimulation,
} from "./ball-simulation";

const idleInput: BallInput = { x: 0, y: 0 };

function advance(
  simulation: BallSimulation,
  seconds: number,
  frameRate = 60,
  policy: (state: BallSimulation) => BallInput = () => idleInput,
): BallSimulation {
  const frames = Math.round(seconds * frameRate);
  for (let frame = 0; frame < frames; frame += 1) {
    stepBallSimulation(simulation, policy(simulation), 1 / frameRate);
  }
  return simulation;
}

function parkObstacles(simulation: BallSimulation): void {
  simulation.obstacles.forEach((obstacle, index) => {
    obstacle.active = true;
    obstacle.passed = false;
    obstacle.hit = false;
    obstacle.z = -10_000 - index * 100;
  });
}

function tutorialManifest(simulation: BallSimulation) {
  return simulation.obstacles
    .filter((obstacle) => obstacle.tutorialStep !== null)
    .sort((left, right) => (left.tutorialStep ?? 0) - (right.tutorialStep ?? 0))
    .map((obstacle) => ({
      kind: obstacle.kind,
      patternId: obstacle.patternId,
      tutorialStep: obstacle.tutorialStep,
      x: obstacle.x,
      y: obstacle.y,
      z: obstacle.z,
      safePoint: { ...obstacle.safePoint },
      ...(obstacle.kind === "gate"
        ? { openingRadius: obstacle.openingRadius }
        : { width: obstacle.width, height: obstacle.height }),
    }));
}

function approachingObstacle(simulation: BallSimulation): BallObstacle | null {
  let selected: BallObstacle | null = null;
  for (const obstacle of simulation.obstacles) {
    if (!obstacle.active || obstacle.passed || obstacle.hit) continue;
    if (!selected || obstacle.z > selected.z) selected = obstacle;
  }
  return selected;
}

function guidedInput(simulation: BallSimulation): BallInput {
  const target = approachingObstacle(simulation);
  if (!target) return idleInput;
  return {
    x: Math.max(-1, Math.min(1, (target.safePoint.x - simulation.ball.position.x) * 0.85)),
    y: Math.max(-1, Math.min(1, (target.safePoint.y - simulation.ball.position.y) * 0.85)),
  };
}

function makeGate(
  slot: number,
  id: string,
  openingRadius = 5,
): BallGateObstacle {
  return {
    id,
    poolSlot: slot,
    active: true,
    kind: "gate",
    patternId: "test-gate",
    tutorialStep: null,
    x: 0,
    y: 0,
    z: -0.05,
    depth: 0.5,
    passed: false,
    hit: false,
    telegraphSeconds: 3,
    safePoint: { x: 0, y: 0 },
    openingRadius,
  };
}

function makeBlock(
  slot: number,
  id: string,
): BallBlockObstacle {
  return {
    id,
    poolSlot: slot,
    active: true,
    kind: "block",
    patternId: "test-block",
    tutorialStep: null,
    x: 0,
    y: 0,
    z: -0.5,
    depth: 2.4,
    passed: false,
    hit: false,
    telegraphSeconds: 3,
    safePoint: { x: 3, y: 0 },
    width: 3,
    height: 3,
  };
}

describe("single-ball deterministic tunnel rules", () => {
  it("keeps one stable mutable state and one bounded obstacle pool", () => {
    const simulation = createBallSimulation("stable-pool");
    const obstacles = simulation.obstacles;
    const returned = stepBallSimulation(simulation, { x: Number.NaN, y: 4 }, 0);

    expect(returned).toBe(simulation);
    expect(returned.obstacles).toBe(obstacles);
    expect(returned.obstacles).toHaveLength(BALL_OBSTACLE_POOL_SIZE);
    expect(new Set(returned.obstacles.map(({ poolSlot }) => poolSlot)).size).toBe(
      BALL_OBSTACLE_POOL_SIZE,
    );
  });

  it("uses rotationally symmetric sphere collisions and full-sphere gate clearance", () => {
    const simulation = createBallSimulation("collision-symmetry");
    const block = makeBlock(0, "symmetry");
    block.width = 2;
    block.height = 2;
    block.z = 0;

    simulation.ball.position = { x: 1 + BALL_RADIUS - 0.01, y: 0 };
    const horizontal = ballSphereIntersectsBlock(simulation.ball, block);
    const horizontalNormal = ballImpactNormalForBlock(simulation.ball, block);
    simulation.ball.position = { x: 0, y: 1 + BALL_RADIUS - 0.01 };
    const vertical = ballSphereIntersectsBlock(simulation.ball, block);
    const verticalNormal = ballImpactNormalForBlock(simulation.ball, block);

    expect(horizontal).toBe(true);
    expect(vertical).toBe(horizontal);
    expect(horizontalNormal).toMatchObject({ x: 1, y: 0, z: 0 });
    expect(verticalNormal).toMatchObject({ x: 0, y: 1, z: 0 });

    const gate = makeGate(0, "clearance", 2.4);
    simulation.ball.position = { x: 1.5, y: 0 };
    expect(ballFitsGate(simulation.ball, gate)).toBe(true);
    simulation.ball.position.x += 0.001;
    expect(ballFitsGate(simulation.ball, gate)).toBe(false);
  });

  it("responds in under 400ms and releases below ten percent within 500ms", () => {
    const simulation = createBallSimulation("movement-response");
    parkObstacles(simulation);

    advance(simulation, 0.4, 60, () => ({ x: 1, y: 0 }));
    const drivenSpeed = simulation.ball.velocity.x;
    expect(drivenSpeed).toBeGreaterThan(9.5);
    expect(simulation.ball.velocity.y).toBe(0);

    advance(simulation, 0.5);
    expect(Math.abs(simulation.ball.velocity.x)).toBeLessThan(drivenSpeed * 0.1);
  });

  it("clamps the complete ball to a circular flight boundary without sticky tangential loss", () => {
    const diagonal = clampBallToTunnel({
      position: { x: 20, y: 20 },
      velocity: { x: 8, y: -3 },
      radius: BALL_RADIUS,
    });
    expect(Math.hypot(diagonal.position.x, diagonal.position.y)).toBeCloseTo(
      BALL_PLAY_RADIUS,
      10,
    );
    expect(Number.isFinite(diagonal.velocity.x)).toBe(true);
    expect(Number.isFinite(diagonal.velocity.y)).toBe(true);

    const simulation = createBallSimulation("boundary-long-run");
    parkObstacles(simulation);
    advance(simulation, 20, 120, (state) => ({
      x: Math.cos(state.elapsed * 2.1),
      y: Math.sin(state.elapsed * 1.7),
    }));
    expect(Math.hypot(
      simulation.ball.position.x,
      simulation.ball.position.y,
    )).toBeLessThanOrEqual(BALL_PLAY_RADIUS + 1e-9);
  });

  it("authors the complete opening lesson independently of seed and assist mode", () => {
    const first = createBallSimulation("lesson-a");
    const repeat = createBallSimulation("lesson-b", { assistMode: true });

    expect(tutorialManifest(first)).toEqual(tutorialManifest(repeat));
    expect(tutorialManifest(first)).toHaveLength(BALL_TUTORIAL_BLUEPRINTS.length);
    expect(tutorialManifest(first).map(({ patternId }) => patternId)).toEqual([
      "tutorial-centered-gate",
      "tutorial-offset-gate",
      "tutorial-telegraphed-block",
      "tutorial-slalom-right",
      "tutorial-slalom-left",
      "tutorial-slalom-finish",
    ]);
    expect(first.obstacles.filter(({ tutorialStep }) => tutorialStep === null))
      .not.toEqual(repeat.obstacles.filter(({ tutorialStep }) => tutorialStep === null));
  });

  it("delivers the generous centered opening gate at roughly four seconds", () => {
    const simulation = createBallSimulation("opening-timing");
    while (simulation.gateEventSequence === 0 && simulation.elapsed < 6) {
      stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);
    }

    expect(simulation.gateEventSequence).toBe(1);
    expect(simulation.lastGateEvent).toMatchObject({
      obstacleId: "tutorial-1",
      result: "clean",
      overdriveCharge: 1,
    });
    expect(simulation.elapsed).toBeGreaterThanOrEqual(3.7);
    expect(simulation.elapsed).toBeLessThanOrEqual(4.2);
  });

  it("ramps smoothly through four early pace bands and caps at redline", () => {
    expect(ballPaceForElapsed(0)).toBe(1);
    expect(ballPaceForElapsed(12)).toBe(2);
    expect(ballPaceForElapsed(32)).toBe(3);
    expect(ballPaceForElapsed(58)).toBe(4);

    let previous = ballSpeedForElapsed(0);
    for (let elapsed = 0.1; elapsed <= 100; elapsed += 0.1) {
      const speed = ballSpeedForElapsed(elapsed);
      expect(speed).toBeGreaterThanOrEqual(previous - 1e-10);
      expect(speed - previous).toBeLessThan(0.16);
      previous = speed;
    }
    expect(ballSpeedForElapsed(88)).toBe(BALL_MAX_SPEED);
    expect(ballSpeedForElapsed(1_000)).toBe(BALL_MAX_SPEED);
  });

  it("keeps every generated redline encounter beyond the reaction floor", () => {
    const simulation = createBallSimulation("redline-spacing");
    simulation.tick = 100 * 60;
    simulation.elapsed = 100;
    simulation.speed = BALL_MAX_SPEED;
    simulation.pace = 4;
    simulation.obstacles.forEach((obstacle) => {
      obstacle.active = false;
    });
    stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);

    const generated = [...simulation.obstacles]
      .sort((left, right) => right.z - left.z);
    for (let index = 1; index < generated.length; index += 1) {
      const spacing = generated[index - 1].z - generated[index].z;
      expect(spacing / BALL_MAX_SPEED).toBeGreaterThanOrEqual(
        BALL_MINIMUM_REACTION_SECONDS + BALL_FIXED_STEP_SECONDS - 1e-9,
      );
    }
  });

  it("deals exact 4-gate/3-block shuffle bags without three repeated kinds", () => {
    const simulation = createBallSimulation("seven-beat-bags");
    const generated = simulation.obstacles
      .filter(({ tutorialStep }) => tutorialStep === null)
      .sort((left, right) => {
        const leftSequence = Number(left.patternId.split("-")[1]);
        const rightSequence = Number(right.patternId.split("-")[1]);
        return leftSequence - rightSequence;
      })
      .map(({ kind }) => kind);

    while (generated.length < 28) {
      simulation.obstacles[6].active = false;
      stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);
      generated.push(simulation.obstacles[6].kind);
    }

    for (let index = 0; index < generated.length; index += 7) {
      const bag = generated.slice(index, index + 7);
      expect(bag.filter((kind) => kind === "gate")).toHaveLength(4);
      expect(bag.filter((kind) => kind === "block")).toHaveLength(3);
    }
    for (let index = 2; index < generated.length; index += 1) {
      expect(new Set(generated.slice(index - 2, index + 1)).size).toBeGreaterThan(1);
    }
  });

  it("applies one shield hit per invulnerability window and crashes on the third", () => {
    const simulation = createBallSimulation("three-hits");
    parkObstacles(simulation);
    simulation.combo = 3;
    simulation.overdriveCharge = 2;

    for (let hit = 1; hit <= BALL_INITIAL_SHIELDS; hit += 1) {
      simulation.obstacles[0] = makeBlock(0, `impact-${hit}`);
      stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);
      expect(simulation.shields).toBe(BALL_INITIAL_SHIELDS - hit);
      expect(simulation.impactEventSequence).toBe(hit);
      expect(simulation.lastImpactEvent?.normal).toSatisfy(
        (normal: { x: number; y: number; z: number }) =>
          Math.abs(Math.hypot(normal.x, normal.y, normal.z) - 1) < 1e-9,
      );
      expect(simulation.combo).toBe(1);
      expect(simulation.overdriveCharge).toBe(0);

      if (hit === 1) {
        simulation.obstacles[0] = makeBlock(0, "immune-overlap");
        stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);
        expect(simulation.shields).toBe(2);
        expect(simulation.impactEventSequence).toBe(1);
      }
      if (hit < BALL_INITIAL_SHIELDS) {
        parkObstacles(simulation);
        advance(simulation, 0.92);
      }
    }

    expect(simulation.status).toBe("crashed");
    expect(simulation.lastImpactEvent).toMatchObject({
      shieldsRemaining: 0,
      crashed: true,
    });
    expect(simulation.ball.velocity).toEqual({ x: 0, y: 0 });
  });

  it("does not award a later pool slot after a terminal impact in the same tick", () => {
    const simulation = createBallSimulation("terminal-ordering");
    parkObstacles(simulation);
    simulation.shields = 1;
    simulation.obstacles[0] = makeBlock(0, "terminal-block");
    simulation.obstacles[1] = makeGate(1, "too-late-gate");

    stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);

    expect(simulation.status).toBe("crashed");
    expect(simulation.impactEventSequence).toBe(1);
    expect(simulation.gateEventSequence).toBe(0);
    expect(simulation.cleanGates).toBe(0);
    expect(simulation.overdriveCharge).toBe(0);
  });

  it("automatically starts five seconds of double-score Overdrive after four clean gates", () => {
    expect(BALL_OVERDRIVE_GATES_REQUIRED).toBe(4);
    const simulation = createBallSimulation("automatic-overdrive");
    parkObstacles(simulation);
    const awards: number[] = [];

    for (let gate = 1; gate <= BALL_OVERDRIVE_GATES_REQUIRED; gate += 1) {
      simulation.obstacles[0] = makeGate(0, `clean-${gate}`);
      stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);
      awards.push(simulation.lastGateEvent?.scoreAwarded ?? 0);
    }

    expect(simulation.cleanGates).toBe(BALL_OVERDRIVE_GATES_REQUIRED);
    expect(simulation.overdriveActivations).toBe(1);
    expect(simulation.overdriveCharge).toBe(0);
    expect(simulation.overdriveRemaining).toBeCloseTo(
      BALL_OVERDRIVE_DURATION_SECONDS,
      8,
    );
    expect(simulation.lastGateEvent).toMatchObject({
      result: "clean",
      overdriveStarted: true,
      overdriveActive: true,
    });
    expect(awards[3]).toBeGreaterThan(awards[2] * 1.9);
  });

  it("makes the opening Overdrive reachable through readable cues within 35 seconds", () => {
    for (let seed = 1; seed <= 16; seed += 1) {
      const simulation = createBallSimulation(seed);
      advance(simulation, 35, 60, guidedInput);
      expect(simulation.overdriveActivations, `seed ${seed}`).toBeGreaterThanOrEqual(1);
      expect(simulation.status, `seed ${seed}`).toBe("running");
    }
  });

  it("recognizes a fully clear edge skim as a rewarded near miss", () => {
    const simulation = createBallSimulation("gate-near-miss");
    parkObstacles(simulation);
    simulation.ball.position.x = 0.45;
    simulation.obstacles[0] = makeGate(0, "edge-skim", 1.8);

    stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);

    expect(simulation.shields).toBe(BALL_INITIAL_SHIELDS);
    expect(simulation.nearMisses).toBe(1);
    expect(simulation.lastGateEvent).toMatchObject({
      result: "clean",
      nearMiss: true,
    });
    expect(simulation.lastGateEvent?.scoreAwarded).toBeGreaterThan(300);
  });

  it("is deterministic for a seed and identical at 60 and 120 render Hz", () => {
    const sixty = createBallSimulation("refresh-determinism");
    const oneTwenty = createBallSimulation("refresh-determinism");
    parkObstacles(sixty);
    parkObstacles(oneTwenty);

    advance(sixty, 24, 60, () => ({ x: 0.37, y: -0.22 }));
    advance(oneTwenty, 24, 120, () => ({ x: 0.37, y: -0.22 }));

    expect(oneTwenty).toEqual(sixty);
  });

  it("extracts on fixed tick 6300, stops motion, and remains immutable", () => {
    expect(BALL_CONTRACT_DURATION_SECONDS).toBe(105);
    expect(BALL_CONTRACT_TICKS).toBe(6_300);
    const simulation = createBallSimulation("exact-finish");
    parkObstacles(simulation);

    for (let tick = 0; tick < BALL_CONTRACT_TICKS - 1; tick += 1) {
      stepBallSimulation(simulation, { x: 1, y: 0 }, BALL_FIXED_STEP_SECONDS);
    }
    expect(simulation.status).toBe("running");
    expect(simulation.tick).toBe(6_299);

    stepBallSimulation(simulation, { x: 1, y: 0 }, BALL_FIXED_STEP_SECONDS);
    expect(simulation.status).toBe("extracted");
    expect(simulation.tick).toBe(6_300);
    expect(simulation.elapsed).toBe(BALL_CONTRACT_DURATION_SECONDS);
    expect(simulation.ball.velocity).toEqual({ x: 0, y: 0 });
    expect(simulation.accumulator).toBe(0);

    const terminal = structuredClone(simulation);
    stepBallSimulation(simulation, { x: -1, y: 1 }, 10);
    expect(simulation).toEqual(terminal);
  });

  it("lets a same-tick terminal impact beat extraction", () => {
    const simulation = createBallSimulation("finish-impact-priority");
    parkObstacles(simulation);
    simulation.tick = BALL_CONTRACT_TICKS - 1;
    simulation.elapsed = simulation.tick * BALL_FIXED_STEP_SECONDS;
    simulation.speed = BALL_MAX_SPEED;
    simulation.pace = 4;
    simulation.shields = 1;
    simulation.obstacles[0] = makeBlock(0, "finish-line-block");

    stepBallSimulation(simulation, idleInput, BALL_FIXED_STEP_SECONDS);

    expect(simulation.tick).toBe(BALL_CONTRACT_TICKS);
    expect(simulation.status).toBe("crashed");
    expect(simulation.lastImpactEvent).toMatchObject({ crashed: true });
    expect(simulation.accumulator).toBe(0);
  });

  it("restarts an extracted run as a fresh mutable contract", () => {
    const finished = createBallSimulation("restart-finished");
    parkObstacles(finished);
    finished.tick = BALL_CONTRACT_TICKS - 1;
    finished.elapsed = finished.tick * BALL_FIXED_STEP_SECONDS;
    stepBallSimulation(finished, idleInput, BALL_FIXED_STEP_SECONDS);
    expect(finished.status).toBe("extracted");

    const restarted = resetBallSimulation("restart-fresh");
    expect(restarted).not.toBe(finished);
    expect(restarted).toMatchObject({ status: "running", tick: 0, elapsed: 0 });
    stepBallSimulation(restarted, idleInput, BALL_FIXED_STEP_SECONDS);
    expect(restarted.tick).toBe(1);
  });

  it("recycles a finite pool through a long redline run without invalid state", () => {
    const simulation = resetBallSimulation("long-pool");
    simulation.shields = 10_000;
    let maximumObservedPool = simulation.obstacles.length;
    let previousGateSequence = 0;

    advance(simulation, 104, 60, (state) => {
      maximumObservedPool = Math.max(maximumObservedPool, state.obstacles.length);
      expect(new Set(state.obstacles.map(({ poolSlot }) => poolSlot)).size).toBe(
        BALL_OBSTACLE_POOL_SIZE,
      );
      expect(state.gateEventSequence).toBeGreaterThanOrEqual(previousGateSequence);
      previousGateSequence = state.gateEventSequence;
      return {
        x: Math.sin(state.elapsed * 0.73) * 0.65,
        y: Math.cos(state.elapsed * 0.51) * 0.45,
      };
    });

    expect(maximumObservedPool).toBe(BALL_OBSTACLE_POOL_SIZE);
    expect(simulation.status).toBe("running");
    expect(simulation.obstacles).toHaveLength(BALL_OBSTACLE_POOL_SIZE);
    expect(simulation.obstacles.every((obstacle: BallObstacle) =>
      Number.isFinite(obstacle.x) &&
      Number.isFinite(obstacle.y) &&
      Number.isFinite(obstacle.z),
    )).toBe(true);
    expect(Number.isFinite(simulation.score)).toBe(true);
    expect(simulation.tick).toBe(104 * 60);
  });
});
