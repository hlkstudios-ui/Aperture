import { afterEach, describe, expect, it } from 'vitest';
import {
  createLoomSimulation,
  LOOM_ANCHOR_POOL_SIZE,
  type LoomAnchor,
  type LoomIrisOutcome,
  type LoomSimulation,
} from '../loom-simulation';
import {
  LOOM_RAPIER_DESKTOP_DEBRIS_CAP,
  LOOM_RAPIER_IRIS_BLADE_COUNT,
  LOOM_RAPIER_TOUCH_DEBRIS_CAP,
  LoomRapierPhysics,
} from './loom-rapier-physics';

const livePhysics: LoomRapierPhysics[] = [];

afterEach(() => {
  livePhysics.splice(0).forEach((physics) => physics.dispose());
});

async function createPhysics(touchFirst = true): Promise<LoomRapierPhysics> {
  const physics = await LoomRapierPhysics.create({ touchFirst });
  livePhysics.push(physics);
  return physics;
}

function isolateAnchor(
  simulation: LoomSimulation,
  overrides: Partial<LoomAnchor> = {},
): LoomAnchor {
  simulation.anchors.forEach((anchor) => {
    anchor.active = false;
  });
  const anchor = simulation.anchors[0]!;
  Object.assign(anchor, {
    active: true,
    id: 'test-anchor',
    chunkId: 'test-chunk',
    encounterKind: 'opening-thread',
    beat: 1,
    route: 'safe',
    phase: 'ember',
    x: 0,
    y: 0,
    z: 0,
    latched: false,
    resolved: false,
    hit: false,
    closestEndpointDistance: Number.POSITIVE_INFINITY,
    ...overrides,
  });
  return anchor;
}

function setIrisContact(
  simulation: LoomSimulation,
  outcome: LoomIrisOutcome,
  cycle = 3,
): void {
  simulation.iris = {
    active: true,
    cycle,
    stage: 'contact',
    z: 0,
    gapCenter: { x: 0, y: 0 },
    gapRadius: 3.35,
    intensity: 1,
    resolved: outcome !== null,
    outcome,
    chargeAwarded: false,
  };
}

describe('LoomRapierPhysics', () => {
  it('mirrors Loom into a bounded zero-gravity world without mutating it', async () => {
    const physics = await createPhysics(true);
    const simulation = createLoomSimulation(42);
    const before = structuredClone(simulation);

    physics.reset(simulation);
    physics.fixedStep(simulation);

    expect(simulation).toEqual(before);
    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount:
        3 +
        LOOM_ANCHOR_POOL_SIZE +
        LOOM_RAPIER_IRIS_BLADE_COUNT +
        LOOM_RAPIER_TOUCH_DEBRIS_CAP,
      colliderCount:
        5 +
        LOOM_ANCHOR_POOL_SIZE +
        LOOM_RAPIER_IRIS_BLADE_COUNT +
        LOOM_RAPIER_TOUCH_DEBRIS_CAP,
      anchorCapacity: LOOM_ANCHOR_POOL_SIZE,
      irisSensorCapacity: LOOM_RAPIER_IRIS_BLADE_COUNT,
      activeIrisSensors: 0,
      debrisCapacity: LOOM_RAPIER_TOUCH_DEBRIS_CAP,
      physicsSteps: 1,
      timestep: 1 / 60,
      disposed: false,
    });
  });

  it('observes a real Needle contact without making it authoritative', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(7);
    const anchor = isolateAnchor(simulation, {
      phase: 'cobalt',
      hit: true,
    });
    simulation.phase = 'ember';

    physics.reset(simulation);
    const contact = physics
      .fixedStep(simulation)
      .contacts.find((candidate) => candidate.actor === 'needle');

    expect(contact).toMatchObject({
      anchorId: anchor.id,
      poolSlot: anchor.poolSlot,
      actor: 'needle',
      anchorPhase: 'cobalt',
      phaseMatches: false,
      authoritativeHit: true,
      authoritativeLatched: false,
    });
  });

  it('observes matching-phase Thread contact between the endpoints', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(8);
    isolateAnchor(simulation, {
      x: -2.3,
      phase: 'ember',
      latched: true,
      route: 'expressive',
    });
    simulation.phase = 'ember';

    physics.reset(simulation);
    const contacts = physics.fixedStep(simulation).contacts;

    expect(contacts).toEqual([
      expect.objectContaining({
        actor: 'thread',
        anchorId: 'test-anchor',
        route: 'expressive',
        phaseMatches: true,
        authoritativeLatched: true,
      }),
    ]);
  });

  it('phase-filters Thread contact and emits it when the phase changes', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(9);
    isolateAnchor(simulation, { x: -2.3, phase: 'ember' });
    simulation.phase = 'cobalt';

    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);

    simulation.phase = 'ember';
    expect(physics.fixedStep(simulation).contacts).toEqual([
      expect.objectContaining({
        actor: 'thread',
        anchorId: 'test-anchor',
        phaseMatches: true,
      }),
    ]);
  });

  it('mirrors Iris blades as sensors while leaving authoritative outcome untouched', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(90);
    simulation.anchors.forEach((anchor) => {
      anchor.active = false;
    });
    setIrisContact(simulation, 'hit', 4);
    const bladeAngle = simulation.iris.cycle * 0.071;
    simulation.needle.position = {
      x: Math.cos(bladeAngle) * (simulation.iris.gapRadius + 0.35),
      y: Math.sin(bladeAngle) * (simulation.iris.gapRadius + 0.35),
    };
    simulation.echo.position = { x: 0, y: 0 };
    const before = structuredClone(simulation);

    physics.reset(simulation);
    const result = physics.fixedStep(simulation);

    expect(simulation).toEqual(before);
    expect(result.irisContacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          cycle: 4,
          actor: 'needle',
          authoritativeStage: 'contact',
          authoritativeResolved: true,
          authoritativeOutcome: 'hit',
        }),
      ]),
    );
    expect(physics.getDiagnostics()).toMatchObject({
      activeIrisSensors: LOOM_RAPIER_IRIS_BLADE_COUNT,
      irisCycle: 4,
    });
  });

  it('keeps an aligned Iris aperture free of blade contacts', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(91);
    simulation.anchors.forEach((anchor) => {
      anchor.active = false;
    });
    setIrisContact(simulation, 'clear', 5);
    simulation.needle.position = { x: 0.8, y: 0 };
    simulation.echo.position = { x: -0.8, y: 0 };

    physics.reset(simulation);
    const result = physics.fixedStep(simulation);

    expect(result.irisContacts).toEqual([]);
    expect(simulation.iris.outcome).toBe('clear');
  });

  it('recycles an anchor slot without sweeping its replacement through the Loom', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(10);
    const anchor = isolateAnchor(simulation, { x: -2.3, z: 0 });

    physics.reset(simulation);
    expect(physics.fixedStep(simulation).contacts).toHaveLength(1);

    anchor.id = 'recycled-anchor';
    anchor.x = 6;
    anchor.y = 6;
    anchor.z = -90;
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
  });

  it('keeps a constant body and collider budget across many identities', async () => {
    const physics = await createPhysics(false);
    const simulation = createLoomSimulation(11);
    const anchor = isolateAnchor(simulation, { z: -80 });
    physics.reset(simulation);
    const initial = physics.getDiagnostics();

    for (let index = 0; index < 250; index += 1) {
      anchor.id = `anchor-${index}`;
      anchor.phase = index % 2 === 0 ? 'ember' : 'cobalt';
      anchor.x = (index % 7) - 3;
      setIrisContact(
        simulation,
        index % 2 === 0 ? 'clear' : 'hit',
        index + 1,
      );
      physics.fixedStep(simulation);
    }

    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: initial.bodyCount,
      colliderCount: initial.colliderCount,
      debrisCapacity: LOOM_RAPIER_DESKTOP_DEBRIS_CAP,
      irisSensorCapacity: LOOM_RAPIER_IRIS_BLADE_COUNT,
      physicsSteps: 250,
    });
  });

  it('caps thread-break debris by device class and exposes finite poses', async () => {
    const physics = await createPhysics(true);
    const simulation = createLoomSimulation(12);
    physics.reset(simulation);

    for (let index = 0; index < 8; index += 1) {
      physics.emitThreadBreak(
        { x: index * 0.05, y: 0, z: 0 },
        { x: 1, y: 0.2, z: 0.1 },
        1.2,
      );
    }
    physics.fixedStep(simulation);

    const poses: Array<{ id: number; finite: boolean; kind: string }> = [];
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
    expect(poses).toHaveLength(LOOM_RAPIER_TOUCH_DEBRIS_CAP);
    expect(new Set(poses.map(({ id }) => id)).size).toBe(poses.length);
    expect(poses.every(({ finite }) => finite)).toBe(true);
    expect(poses.every(({ kind }) => kind === 'thread-break')).toBe(true);
  });

  it('emits distinct stitch debris and promotes it through a pressure wave', async () => {
    const physics = await createPhysics(true);
    const simulation = createLoomSimulation(13);
    physics.reset(simulation);

    physics.emitStitch({ x: 0, y: 0, z: 0 });
    expect(physics.getDiagnostics().activeDebris).toBe(3);
    const beforeKinds: string[] = [];
    physics.forEachActiveDebrisPose((pose) => beforeKinds.push(pose.kind));
    expect(beforeKinds).toEqual(['stitch', 'stitch', 'stitch']);

    physics.emitResonance({ x: 0, y: 0, z: 0 });
    physics.fixedStep(simulation);
    const afterKinds: string[] = [];
    physics.forEachActiveDebrisPose((pose) => afterKinds.push(pose.kind));
    expect(afterKinds).toEqual(['resonance', 'resonance', 'resonance']);
  });

  it('creates a bounded resonance burst when no debris is active', async () => {
    const physics = await createPhysics(true);
    const simulation = createLoomSimulation(14);
    physics.reset(simulation);

    physics.emitResonance({ x: 0, y: 0, z: 0 });
    physics.fixedStep(simulation);

    expect(physics.getDiagnostics().activeDebris).toBe(6);
  });

  it('freezes while paused and reset removes particles and stale events', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(15);
    isolateAnchor(simulation, { x: -2.3 });
    physics.reset(simulation);
    setIrisContact(simulation, 'hit');
    physics.reset(simulation);
    physics.emitThreadBreak({ x: 0, y: 0, z: 0 });
    physics.fixedStep(simulation);

    physics.pause();
    const beforePause = physics.getDiagnostics().physicsSteps;
    expect(physics.fixedStep(simulation)).toEqual({
      contacts: [],
      irisContacts: [],
    });
    expect(physics.getDiagnostics()).toMatchObject({
      paused: true,
      physicsSteps: beforePause,
      activeIrisSensors: LOOM_RAPIER_IRIS_BLADE_COUNT,
    });

    physics.reset(createLoomSimulation(16));
    expect(physics.getDiagnostics()).toMatchObject({
      activeDebris: 0,
      activeIrisSensors: 0,
      irisCycle: 0,
      paused: false,
      physicsSteps: 0,
    });
  });

  it('resume teleports proxies and dispose is idempotent', async () => {
    const physics = await createPhysics();
    const simulation = createLoomSimulation(17);
    const anchor = isolateAnchor(simulation, { z: -90 });
    physics.reset(simulation);
    physics.pause();
    anchor.id = 'after-pause';
    anchor.z = -75;

    physics.resume(simulation);
    expect(physics.fixedStep(simulation).contacts).toEqual([]);
    physics.dispose();
    physics.dispose();

    expect(physics.getDiagnostics()).toMatchObject({
      bodyCount: 0,
      colliderCount: 0,
      activeAnchors: 0,
      activeIrisSensors: 0,
      irisCycle: 0,
      activeDebris: 0,
      disposed: true,
      paused: true,
    });
    expect(physics.fixedStep(simulation)).toEqual({
      contacts: [],
      irisContacts: [],
    });
  });
});
