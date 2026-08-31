import { afterEach, describe, expect, it } from 'vitest';
import {
  createSimulation,
  type BlockObstacle,
  type GameObstacle,
  type GameSimulation,
  type MembraneObstacle,
} from '../simulation';
import { loadRapier } from './rapier-loader';
import {
  RAPIER_DESKTOP_DEBRIS_CAP,
  RAPIER_HAZARD_POOL_SIZE,
  RAPIER_TOUCH_DEBRIS_CAP,
  SignalRunRapierPhysics,
} from './rapier-physics';

const livePhysics: SignalRunRapierPhysics[] = [];

afterEach(() => {
  livePhysics.splice(0).forEach((physics) => physics.dispose());
});

async function createPhysics(touchFirst = true) {
  const physics = await SignalRunRapierPhysics.create({ touchFirst });
  livePhysics.push(physics);
  return physics;
}

function blockObstacle(
  overrides: Partial<BlockObstacle> = {},
): BlockObstacle {
  return {
    id: 'test-block',
    poolSlot: 0,
    phraseId: 'test-phrase',
    phraseKind: 'solo-block',
    phraseBeat: 1,
    phraseLength: 1,
    kind: 'block',
    x: 0,
    y: 0,
    z: 0,
    width: 3,
    height: 3,
    depth: 2.4,
    passed: false,
    hit: false,
    ...overrides,
  };
}

function membraneObstacle(
  overrides: Partial<MembraneObstacle> = {},
): MembraneObstacle {
  return {
    id: 'test-membrane',
    poolSlot: 0,
    phraseId: 'test-phrase',
    phraseKind: 'solo-membrane',
    phraseBeat: 1,
    phraseLength: 1,
    kind: 'membrane',
    x: 0,
    y: 0,
    z: 0,
    radius: 9,
    depth: 0.4,
    phase: 'ember',
    passed: false,
    hit: false,
    ...overrides,
  };
}

function simulationWithFirstObstacle(obstacle: GameObstacle): GameSimulation {
  const simulation = createSimulation(0x1a2b3c4d);
  simulation.obstacles = simulation.obstacles.map((candidate) => {
    if (candidate.poolSlot === obstacle.poolSlot) return obstacle;
    return {
      ...candidate,
      z: -120 - candidate.poolSlot * 12,
    };
  });
  return simulation;
}

describe('Rapier loader', () => {
  it('shares one real-WASM initialization across concurrent callers', async () => {
    const [first, second] = await Promise.all([loadRapier(), loadRapier()]);

    expect(first).toBe(second);
    expect(typeof first.World).toBe('function');
    expect(typeof first.version()).toBe('string');
  });
});

describe('SignalRunRapierPhysics', () => {
  it('builds a bounded zero-gravity shadow world without mutating gameplay state', async () => {
    const physics = await createPhysics(true);
    const simulation = createSimulation(42);
    const before = structuredClone(simulation);

    physics.reset(simulation);
    physics.fixedStep(simulation);

    expect(simulation).toEqual(before);
    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: 1 + RAPIER_HAZARD_POOL_SIZE + RAPIER_TOUCH_DEBRIS_CAP,
      colliderCount: 3 + RAPIER_HAZARD_POOL_SIZE * 2 + RAPIER_TOUCH_DEBRIS_CAP,
      hazardCapacity: RAPIER_HAZARD_POOL_SIZE,
      debrisCapacity: RAPIER_TOUCH_DEBRIS_CAP,
      physicsSteps: 1,
      timestep: 1 / 60,
      disposed: false,
    });
  });

  it('reports and deduplicates a real kinematic block contact', async () => {
    const physics = await createPhysics();
    const simulation = simulationWithFirstObstacle(
      blockObstacle({ hit: true }),
    );

    physics.reset(simulation);
    const result = physics.fixedStep(simulation);

    expect(result.contacts).toHaveLength(1);
    expect(result.contacts[0]).toMatchObject({
      obstacleId: 'test-block',
      poolSlot: 0,
      kind: 'block',
      authoritativeHit: true,
    });
    expect(Math.hypot(
      result.contacts[0]!.normal.x,
      result.contacts[0]!.normal.y,
      result.contacts[0]!.normal.z,
    )).toBeCloseTo(1, 6);
  });

  it('filters a matching membrane and reports it after the player shifts phase', async () => {
    const physics = await createPhysics();
    const simulation = simulationWithFirstObstacle(membraneObstacle());
    simulation.phase = 'ember';

    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);

    simulation.phase = 'cobalt';
    const shifted = physics.fixedStep(simulation);
    expect(shifted.contacts).toHaveLength(1);
    expect(shifted.contacts[0]).toMatchObject({
      obstacleId: 'test-membrane',
      kind: 'membrane',
      authoritativeHit: false,
    });
  });

  it('teleports a recycled slot without sweeping the replacement through the player', async () => {
    const physics = await createPhysics();
    const simulation = simulationWithFirstObstacle(blockObstacle());
    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toHaveLength(1);

    simulation.obstacles[0] = blockObstacle({
      id: 'recycled-block',
      z: -90,
    });
    const recycled = physics.fixedStep(simulation);

    expect(recycled.contacts).toEqual([]);
  });

  it('reuses a constant body and collider budget across repeated slot identities', async () => {
    const physics = await createPhysics(false);
    const simulation = simulationWithFirstObstacle(
      blockObstacle({ z: -80 }),
    );
    physics.reset(simulation);
    const initial = physics.getDiagnostics();

    for (let index = 0; index < 250; index += 1) {
      simulation.obstacles[0] = index % 2 === 0
        ? blockObstacle({ id: `block-${index}`, z: -80 })
        : membraneObstacle({ id: `membrane-${index}`, z: -80 });
      physics.fixedStep(simulation);
    }

    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: initial.bodyCount,
      colliderCount: initial.colliderCount,
      debrisCapacity: RAPIER_DESKTOP_DEBRIS_CAP,
      physicsSteps: 250,
    });
  });

  it('caps dynamic debris by device class and exposes active poses', async () => {
    const physics = await createPhysics(true);
    const simulation = createSimulation(77);
    physics.reset(simulation);

    for (let index = 0; index < 8; index += 1) {
      physics.emitImpact(
        { x: index * 0.05, y: 0, z: 0 },
        { x: 1, y: 0.2, z: 0.1 },
        1.2,
      );
    }
    physics.fixedStep(simulation);

    const poses: Array<{ id: number; finite: boolean }> = [];
    physics.forEachActiveDebrisPose((pose) => {
      poses.push({
        id: pose.id,
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
    expect(poses).toHaveLength(RAPIER_TOUCH_DEBRIS_CAP);
    expect(new Set(poses.map(({ id }) => id)).size).toBe(poses.length);
    expect(poses.every(({ finite }) => finite)).toBe(true);
    expect(physics.getDiagnostics().activeDebris).toBe(RAPIER_TOUCH_DEBRIS_CAP);
  });

  it('creates a bounded resonance burst when no fragments are active', async () => {
    const physics = await createPhysics(true);
    const simulation = createSimulation(91);
    physics.reset(simulation);

    physics.emitResonance({ x: 0, y: 0, z: 0 });
    physics.fixedStep(simulation);

    expect(physics.getDiagnostics().activeDebris).toBe(6);
  });

  it('freezes while paused and reset clears effects and stale events', async () => {
    const physics = await createPhysics();
    const simulation = simulationWithFirstObstacle(blockObstacle());
    physics.reset(simulation);
    physics.emitImpact({ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 });
    physics.fixedStep(simulation);
    expect(physics.getDiagnostics().activeDebris).toBeGreaterThan(0);

    physics.pause();
    const beforePause = physics.getDiagnostics().physicsSteps;
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
    expect(physics.getDiagnostics()).toMatchObject({
      paused: true,
      physicsSteps: beforePause,
    });

    physics.reset(createSimulation(92));
    expect(physics.getDiagnostics()).toMatchObject({
      activeDebris: 0,
      paused: false,
      physicsSteps: 0,
    });
  });

  it('resumes by teleporting shadow bodies and disposes idempotently', async () => {
    const physics = await createPhysics();
    const simulation = simulationWithFirstObstacle(blockObstacle({ z: -90 }));
    physics.reset(simulation);
    physics.pause();
    simulation.obstacles[0] = blockObstacle({ id: 'after-pause', z: -75 });

    physics.resume(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
    physics.dispose();
    physics.dispose();

    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: 0,
      colliderCount: 0,
      activeDebris: 0,
      disposed: true,
      paused: true,
    });
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
  });
});
