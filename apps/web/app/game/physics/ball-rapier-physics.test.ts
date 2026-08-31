import { afterEach, describe, expect, it } from 'vitest';
import {
  BALL_FIXED_STEP_SECONDS,
  BALL_OBSTACLE_POOL_SIZE,
  BALL_RADIUS,
  createBallSimulation,
  type BallBlockObstacle,
  type BallGateEvent,
  type BallGateObstacle,
  type BallImpactEvent,
  type BallSimulation,
} from '../ball-simulation';
import {
  BALL_RAPIER_DESKTOP_DEBRIS_CAP,
  BALL_RAPIER_GATE_SEGMENTS,
  BALL_RAPIER_TOUCH_DEBRIS_CAP,
  BallRapierPhysics,
} from './ball-rapier-physics';

const livePhysics: BallRapierPhysics[] = [];

afterEach(() => {
  livePhysics.splice(0).forEach((physics) => physics.dispose());
});

async function createPhysics(touchFirst = true): Promise<BallRapierPhysics> {
  const physics = await BallRapierPhysics.create({ touchFirst });
  livePhysics.push(physics);
  return physics;
}

function isolateBlock(
  simulation: BallSimulation,
  overrides: Partial<BallBlockObstacle> = {},
): BallBlockObstacle {
  simulation.obstacles.forEach((obstacle) => {
    obstacle.active = false;
  });
  const block: BallBlockObstacle = {
    id: 'test-block',
    poolSlot: 0,
    active: true,
    kind: 'block',
    patternId: 'test-block',
    tutorialStep: null,
    x: 0,
    y: 0,
    z: 0,
    depth: 2.4,
    passed: false,
    hit: false,
    telegraphSeconds: 3,
    safePoint: { x: 3, y: 0 },
    width: 3,
    height: 3,
    ...overrides,
  };
  simulation.obstacles[0] = block;
  return block;
}

function isolateGate(
  simulation: BallSimulation,
  overrides: Partial<BallGateObstacle> = {},
): BallGateObstacle {
  simulation.obstacles.forEach((obstacle) => {
    obstacle.active = false;
  });
  const gate: BallGateObstacle = {
    id: 'test-gate',
    poolSlot: 0,
    active: true,
    kind: 'gate',
    patternId: 'test-gate',
    tutorialStep: null,
    x: 0,
    y: 0,
    z: 0,
    depth: 0.5,
    passed: false,
    hit: false,
    telegraphSeconds: 3,
    safePoint: { x: 0, y: 0 },
    openingRadius: 3,
    ...overrides,
  };
  simulation.obstacles[0] = gate;
  return gate;
}

function impactEvent(): BallImpactEvent {
  return {
    sequence: 1,
    obstacleId: 'test-block',
    obstacleKind: 'block',
    position: { x: 0.4, y: -0.2, z: 0 },
    normal: { x: 1, y: 0.2, z: 0.1 },
    shieldsRemaining: 2,
    crashed: false,
  };
}

function gateEvent(nearMiss = false): BallGateEvent {
  return {
    sequence: 1,
    obstacleId: 'test-gate',
    result: 'clean',
    position: { x: 0, y: 0, z: 0 },
    scoreAwarded: 450,
    combo: 1.25,
    cleanGateStreak: 1,
    overdriveCharge: 1,
    overdriveStarted: false,
    overdriveActive: false,
    nearMiss,
  };
}

describe('BallRapierPhysics', () => {
  it('builds one spherical player and a bounded zero-gravity mirror without mutation', async () => {
    const physics = await createPhysics(true);
    const simulation = createBallSimulation(42);
    const before = structuredClone(simulation);

    physics.reset(simulation);
    physics.fixedStep(simulation);

    expect(simulation).toEqual(before);
    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: 1 + BALL_OBSTACLE_POOL_SIZE + BALL_RAPIER_TOUCH_DEBRIS_CAP,
      colliderCount:
        1 +
        BALL_OBSTACLE_POOL_SIZE * (BALL_RAPIER_GATE_SEGMENTS + 1) +
        BALL_RAPIER_TOUCH_DEBRIS_CAP,
      playerColliderRadius: BALL_RADIUS,
      hazardCapacity: BALL_OBSTACLE_POOL_SIZE,
      gateSensorCapacity: BALL_OBSTACLE_POOL_SIZE * BALL_RAPIER_GATE_SEGMENTS,
      blockColliderCapacity: BALL_OBSTACLE_POOL_SIZE,
      debrisCapacity: BALL_RAPIER_TOUCH_DEBRIS_CAP,
      physicsSteps: 1,
      timestep: BALL_FIXED_STEP_SECONDS,
      disposed: false,
    });
  });

  it('reports and deduplicates a real block contact without making it authoritative', async () => {
    const physics = await createPhysics();
    const simulation = createBallSimulation(7);
    const block = isolateBlock(simulation, { hit: true, passed: true });
    const before = structuredClone(simulation);

    physics.reset(simulation);
    const result = physics.fixedStep(simulation);

    expect(simulation).toEqual(before);
    expect(result.contacts).toEqual([
      expect.objectContaining({
        obstacleId: block.id,
        poolSlot: 0,
        kind: 'block',
        authoritativeHit: true,
        authoritativePassed: true,
      }),
    ]);
    expect(Math.hypot(
      result.contacts[0]!.normal.x,
      result.contacts[0]!.normal.y,
      result.contacts[0]!.normal.z,
    )).toBeCloseTo(1, 9);
  });

  it('leaves a centered gate opening clear and observes a clipped ring edge', async () => {
    const physics = await createPhysics();
    const simulation = createBallSimulation(8);
    isolateGate(simulation, { openingRadius: 3.2 });

    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
    expect(physics.getDiagnostics()).toMatchObject({
      activeHazards: 1,
      activeGateSensors: BALL_RAPIER_GATE_SEGMENTS,
      activeBlockColliders: 0,
    });

    simulation.ball.position.x = 4;
    physics.resume(simulation);
    const contact = physics.fixedStep(simulation).contacts;
    expect(contact).toEqual([
      expect.objectContaining({
        obstacleId: 'test-gate',
        kind: 'gate',
      }),
    ]);
  });

  it('teleports a recycled hazard identity without sweeping it through the ball', async () => {
    const physics = await createPhysics();
    const simulation = createBallSimulation(9);
    const block = isolateBlock(simulation);
    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toHaveLength(1);

    block.id = 'recycled-far-block';
    block.x = 6;
    block.y = 6;
    block.z = -90;
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
  });

  it('keeps a constant body and collider budget across repeated kinds and identities', async () => {
    const physics = await createPhysics(false);
    const simulation = createBallSimulation(10);
    isolateBlock(simulation, { z: -80 });
    physics.reset(simulation);
    const initial = physics.getDiagnostics();

    for (let index = 0; index < 220; index += 1) {
      if (index % 2 === 0) {
        isolateGate(simulation, {
          id: `gate-${index}`,
          openingRadius: 2.6 + (index % 4) * 0.2,
          z: -80,
        });
      } else {
        isolateBlock(simulation, {
          id: `block-${index}`,
          width: 2 + (index % 5),
          z: -80,
        });
      }
      physics.fixedStep(simulation);
    }

    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: initial.bodyCount,
      colliderCount: initial.colliderCount,
      debrisCapacity: BALL_RAPIER_DESKTOP_DEBRIS_CAP,
      physicsSteps: 220,
    });
  });

  it('caps distinct impact and clean-gate debris and exposes finite poses', async () => {
    const physics = await createPhysics(true);
    const simulation = createBallSimulation(11);
    physics.reset(simulation);

    physics.emitImpact(impactEvent(), 1.25);
    expect(physics.getDiagnostics().activeDebris).toBe(5);
    physics.emitGate(gateEvent(true));
    expect(physics.getDiagnostics().activeDebris).toBe(9);
    physics.fixedStep(simulation);

    const poses: Array<{ id: number; kind: string; finite: boolean }> = [];
    physics.forEachActiveDebrisPose((pose) => {
      poses.push({
        id: pose.id,
        kind: pose.kind,
        finite: [
          pose.position.x,
          pose.position.y,
          pose.position.z,
          pose.rotation.x,
          pose.rotation.y,
          pose.rotation.z,
          pose.rotation.w,
        ].every(Number.isFinite),
      });
    });
    expect(poses).toHaveLength(9);
    expect(new Set(poses.map(({ id }) => id)).size).toBe(poses.length);
    expect(poses.every(({ finite }) => finite)).toBe(true);
    expect(new Set(poses.map(({ kind }) => kind))).toEqual(
      new Set(['impact', 'gate']),
    );
  });

  it('creates a bounded Overdrive wave and promotes already-active debris', async () => {
    const physics = await createPhysics(true);
    const simulation = createBallSimulation(12);
    physics.reset(simulation);

    physics.emitOverdrive({ x: 0, y: 0, z: 0 });
    expect(physics.getDiagnostics().activeDebris).toBe(6);
    physics.emitGate(gateEvent());
    physics.emitOverdrive({ x: 0, y: 0, z: 0 });
    physics.fixedStep(simulation);

    const kinds: string[] = [];
    physics.forEachActiveDebrisPose((pose) => kinds.push(pose.kind));
    expect(kinds.length).toBeLessThanOrEqual(BALL_RAPIER_TOUCH_DEBRIS_CAP);
    expect(kinds.every((kind) => kind === 'overdrive')).toBe(true);
  });

  it('freezes while paused, resumes by teleport, resets FX, and disposes idempotently', async () => {
    const physics = await createPhysics();
    const simulation = createBallSimulation(13);
    isolateBlock(simulation);
    physics.reset(simulation);
    physics.emitImpact(impactEvent());
    physics.fixedStep(simulation);

    physics.pause();
    const steps = physics.getDiagnostics().physicsSteps;
    physics.emitOverdrive({ x: 0, y: 0, z: 0 });
    expect(physics.fixedStep(simulation)).toEqual({ contacts: [] });
    expect(physics.getDiagnostics()).toMatchObject({
      paused: true,
      physicsSteps: steps,
      activeDebris: 5,
    });

    simulation.ball.position = { x: 6, y: 6 };
    physics.resume(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
    expect(physics.getDiagnostics().paused).toBe(false);

    physics.reset(createBallSimulation(14));
    expect(physics.getDiagnostics()).toMatchObject({
      activeDebris: 0,
      physicsSteps: 0,
    });

    physics.dispose();
    physics.dispose();
    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: 0,
      colliderCount: 0,
      activeHazards: 0,
      activeDebris: 0,
      paused: true,
      disposed: true,
    });
  });
});
