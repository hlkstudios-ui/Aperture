import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import type { Mesh } from '@babylonjs/core/Meshes/mesh.js';

import {
  BALL_RADIUS,
  type BallObstacle,
  type BallSimulation,
} from '../ball-simulation';
import {
  SIGNAL_RUN_BALL_DIAMETER,
  SIGNAL_RUN_BLOCK_VISUAL_CAPACITY,
  SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY,
  SIGNAL_RUN_GATE_VISUAL_CAPACITY,
  SignalRunBabylonScene,
  sanitizeSignalRunVisualDelta,
  signalRunCameraFovAxis,
  signalRunDebrisPoolSlot,
  signalRunNearestUpcomingObstacleIndex,
  signalRunObstacleTimeToContact,
  signalRunObstacleVisibleAtZ,
  signalRunRailCountForQuality,
  signalRunRendererIsSoftware,
  signalRunRibCountForQuality,
  signalRunTelegraphCueZ,
  signalRunTelegraphStrength,
  signalRunVisualLead,
  signalRunWrappedTunnelZ,
  type SignalRunDebrisPose,
  type SignalRunEngineFactory,
} from './signal-run-babylon-scene';

function sizedHost(width = 640, height = 360) {
  const host = document.createElement('div');
  Object.defineProperties(host, {
    clientWidth: { configurable: true, value: width },
    clientHeight: { configurable: true, value: height },
  });
  host.getBoundingClientRect = () => ({
    bottom: height,
    height,
    left: 0,
    right: width,
    top: 0,
    width,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  document.body.appendChild(host);
  return host;
}

interface EngineCapture {
  hardwareScalingLevel: number;
  resizeCalls: number;
}

function nullEngineFactory(capture?: EngineCapture): SignalRunEngineFactory {
  return async (canvas) => {
    const engine = new NullEngine({
      deterministicLockstep: false,
      lockstepMaxSteps: 4,
      renderHeight: 360,
      renderWidth: 640,
      textureSize: 256,
    });
    if (capture) {
      const nativeSetHardwareScalingLevel =
        engine.setHardwareScalingLevel.bind(engine);
      engine.setHardwareScalingLevel = (level) => {
        capture.hardwareScalingLevel = level;
        nativeSetHardwareScalingLevel(level);
      };
      engine.resize = () => {
        capture.resizeCalls += 1;
        const ratio = 1 / capture.hardwareScalingLevel;
        canvas.width = Math.round(640 * ratio);
        canvas.height = Math.round(360 * ratio);
      };
    }
    return { engine, backend: 'webgl' };
  };
}

function obstacle(
  index: number,
  kind: 'gate' | 'block',
): BallObstacle {
  const common = {
    id: `test-${kind}-${index}`,
    poolSlot: index,
    active: true,
    patternId: 'test-pattern',
    tutorialStep: null,
    x: (index % 5) - 2,
    y: (index % 3) - 1,
    z: -15 - (index % 12) * 5,
    depth: 1,
    passed: false,
    hit: false,
    telegraphSeconds: 1,
    safePoint: { x: 0, y: 0 },
  };
  return (kind === 'gate'
    ? { ...common, kind, openingRadius: 2.4 }
    : { ...common, kind, width: 2.2, height: 2.7 }) as BallObstacle;
}

function simulationWith(
  obstacles: readonly BallObstacle[] = [obstacle(0, 'gate'), obstacle(1, 'block')],
): BallSimulation {
  return {
    seed: 7,
    rngState: 9,
    ball: {
      position: { x: 0.4, y: -0.2 },
      velocity: { x: 2, y: -1 },
      radius: BALL_RADIUS,
    },
    distance: 18,
    score: 0,
    shields: 3,
    combo: 0,
    pace: 1,
    speed: 12,
    elapsed: 2,
    accumulator: 1 / 120,
    status: 'running',
    obstacles: [...obstacles],
    overdriveCharge: 0,
    overdriveRemaining: 0,
    overdriveActivations: 0,
    impactEventSequence: 0,
    lastImpactEvent: null,
    gateEventSequence: 0,
    lastGateEvent: null,
  } as BallSimulation;
}

function debrisPose(id: number): SignalRunDebrisPose {
  return {
    id,
    position: { x: id * 0.1, y: -id * 0.1, z: -10 - id },
    rotation: { x: 0, y: 0, z: 0, w: 1 },
    sleeping: false,
  };
}

describe('Signal Run Babylon presentation helpers', () => {
  it('keeps the visible solid sphere exactly equal to the collision diameter', () => {
    expect(SIGNAL_RUN_BALL_DIAMETER).toBe(BALL_RADIUS * 2);
    expect(SIGNAL_RUN_BALL_DIAMETER).toBeGreaterThan(0);
  });

  it('clamps interpolation and visual hitch recovery without changing cadence', () => {
    expect(sanitizeSignalRunVisualDelta(-1)).toBe(0);
    expect(sanitizeSignalRunVisualDelta(Number.NaN)).toBe(0);
    expect(sanitizeSignalRunVisualDelta(0.2)).toBe(0.05);
    expect(signalRunVisualLead(2, 6, 1 / 120)).toBeCloseTo(2.05);
    expect(signalRunVisualLead(2, 6, 1)).toBe(3.5);
  });

  it('keeps portrait framing horizontal-fixed and bounds structural work', () => {
    expect(signalRunCameraFovAxis(320, 568)).toBe('horizontal');
    expect(signalRunCameraFovAxis(568, 320)).toBe('vertical');
    expect(signalRunRibCountForQuality('cinematic')).toBe(12);
    expect(signalRunRibCountForQuality('balanced')).toBe(12);
    expect(signalRunRibCountForQuality('performance')).toBe(6);
    expect(signalRunRailCountForQuality('performance')).toBe(6);
  });

  it('wraps tunnel motion and culls obstacles outside the actionable volume', () => {
    expect(signalRunWrappedTunnelZ(-24, 288, 288)).toBe(-24);
    expect(signalRunWrappedTunnelZ(-24, 300, 288)).toBe(-12);
    expect(signalRunObstacleVisibleAtZ(-174.9)).toBe(true);
    expect(signalRunObstacleVisibleAtZ(-175.1)).toBe(false);
    expect(signalRunObstacleVisibleAtZ(18)).toBe(true);
    expect(signalRunObstacleVisibleAtZ(18.1)).toBe(false);
  });

  it('recognizes software renderers and maps debris into fixed slots', () => {
    expect(signalRunRendererIsSoftware('Google SwiftShader')).toBe(true);
    expect(signalRunRendererIsSoftware('Mesa llvmpipe')).toBe(true);
    expect(signalRunRendererIsSoftware('ANGLE NVIDIA RTX')).toBe(false);
    expect(signalRunDebrisPoolSlot(33, 32)).toBe(1);
    expect(signalRunDebrisPoolSlot(-1, 32)).toBe(31);
    expect(signalRunDebrisPoolSlot(2, 0)).toBe(-1);
  });

  it('times the true player-facing plane and selects only the nearest unresolved hazard', () => {
    const farGate = {
      ...obstacle(0, 'gate'),
      z: -30,
    } as BallObstacle;
    const nearBlock = {
      ...obstacle(1, 'block'),
      z: -15,
    } as BallObstacle;

    expect(signalRunObstacleTimeToContact(farGate, 10)).toBeCloseTo(2.95);
    expect(signalRunObstacleTimeToContact(nearBlock, 10)).toBeCloseTo(1.36);
    expect(signalRunObstacleTimeToContact(nearBlock, 10, 0.1)).toBeCloseTo(1.26);
    expect(
      signalRunNearestUpcomingObstacleIndex([farGate, nearBlock], 10),
    ).toBe(1);

    nearBlock.passed = true;
    expect(
      signalRunNearestUpcomingObstacleIndex([farGate, nearBlock], 10),
    ).toBe(0);
    farGate.hit = true;
    expect(
      signalRunNearestUpcomingObstacleIndex([farGate, nearBlock], 10),
    ).toBe(-1);
  });

  it('builds telegraph strength only inside the authored warning window', () => {
    expect(signalRunTelegraphStrength(3.01, 3)).toBe(0);
    expect(signalRunTelegraphStrength(3, 3)).toBeCloseTo(0.12);
    expect(signalRunTelegraphStrength(1.5, 3)).toBeGreaterThan(0.12);
    expect(signalRunTelegraphStrength(1.5, 3)).toBeLessThan(1);
    expect(signalRunTelegraphStrength(0, 3)).toBe(1);
    expect(signalRunTelegraphStrength(Number.POSITIVE_INFINITY, 3)).toBe(0);
    expect(signalRunTelegraphStrength(1, 0)).toBe(0);
  });

  it('keeps early solid-route cues on a readable guide plane without moving their safe point', () => {
    expect(signalRunTelegraphCueZ('block', -30, 2.4)).toBe(4.5);
    expect(signalRunTelegraphCueZ('block', -8, 2.4)).toBe(4.5);
    expect(signalRunTelegraphCueZ('gate', -30, 0.5)).toBeCloseTo(-29.03);
  });
});

describe('SignalRunBabylonScene lifecycle', () => {
  it('owns one touch-safe canvas, bounded visuals, pause state, and disposal', async () => {
    const host = sizedHost();
    const observe = vi.fn();
    const disconnect = vi.fn();
    const scene = await SignalRunBabylonScene.create(host, {
      engineFactory: nullEngineFactory(),
      physicsBackend: 'rapier',
      resizeObserverFactory: () => ({ observe, disconnect }),
      touchFirst: true,
    });
    const canvas = scene.getCanvas();
    const babylonScene = (scene as unknown as {
      scene: import('@babylonjs/core/scene.js').Scene;
    }).scene;
    const gateRim = babylonScene.getMeshByName('signal-run-gate-pool');
    const gateCore = babylonScene.getMeshByName(
      'signal-run-gate-core-pool',
    ) as Mesh | null;

    expect(host.querySelectorAll('canvas')).toHaveLength(1);
    expect(gateRim).not.toBeNull();
    expect(gateCore).not.toBeNull();
    expect(gateCore?.material).not.toBe(gateRim?.material);
    expect(canvas.style.touchAction).toBe('none');
    expect(canvas.dataset).toMatchObject({
      playerAvatar: 'ball',
      ballRadius: BALL_RADIUS.toFixed(3),
      ballDiameter: SIGNAL_RUN_BALL_DIAMETER.toFixed(3),
      physicsBackend: 'rapier',
      renderBackend: 'webgl',
      qualityTier: 'balanced',
      telegraphKind: 'none',
      telegraphTti: '-1.000',
      telegraphStrength: '0.000',
      telegraphGuideZ: '0.000',
      telegraphScale: '0.000',
    });
    expect(observe).toHaveBeenCalledWith(host);

    const crowded = Array.from({ length: 80 }, (_, index) =>
      obstacle(index, index % 2 === 0 ? 'gate' : 'block'),
    );
    scene.render(simulationWith(crowded), 1 / 60);
    expect(Number(canvas.dataset.activeGates)).toBeLessThanOrEqual(
      SIGNAL_RUN_GATE_VISUAL_CAPACITY,
    );
    expect(Number(canvas.dataset.activeBlocks)).toBeLessThanOrEqual(
      SIGNAL_RUN_BLOCK_VISUAL_CAPACITY,
    );
    expect(gateCore?.thinInstanceCount).toBe(
      Number(canvas.dataset.activeGates),
    );
    expect(Number(canvas.dataset.ballX)).toBeGreaterThan(0.4);
    expect(Number(canvas.dataset.ballY)).toBeLessThan(-0.2);

    scene.syncDebris(
      Array.from(
        { length: SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY + 20 },
        (_, index) => debrisPose(index),
      ),
    );
    expect(scene.getDiagnostics()).toMatchObject({
      ballDiameter: SIGNAL_RUN_BALL_DIAMETER,
      gateCapacity: SIGNAL_RUN_GATE_VISUAL_CAPACITY,
      blockCapacity: SIGNAL_RUN_BLOCK_VISUAL_CAPACITY,
      debrisCapacity: SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY,
      paused: false,
      disposed: false,
    });
    expect(scene.getDiagnostics().activeDebris).toBeLessThanOrEqual(16);

    scene.impact(1.5);
    scene.gate(1.2);
    scene.overdrive(true);
    scene.setComfortMode(true);
    scene.pause();
    expect(scene.getDiagnostics().paused).toBe(true);
    scene.resume();
    expect(scene.getDiagnostics().paused).toBe(false);

    scene.dispose();
    scene.dispose();
    expect(scene.getDiagnostics().disposed).toBe(true);
    expect(host.querySelectorAll('canvas')).toHaveLength(0);
    expect(disconnect).toHaveBeenCalledTimes(1);
    host.remove();
  });

  it('renders one safe-route cue, distinguishes hazard kinds, and hides it after pass', async () => {
    const host = sizedHost();
    const scene = await SignalRunBabylonScene.create(host, {
      engineFactory: nullEngineFactory(),
      resizeObserverFactory: () => ({ observe: vi.fn(), disconnect: vi.fn() }),
    });
    const canvas = scene.getCanvas();
    const gate = {
      ...obstacle(0, 'gate'),
      z: -10,
      telegraphSeconds: 2,
      safePoint: { x: 2.25, y: -1.1 },
    } as BallObstacle;
    const block = {
      ...obstacle(1, 'block'),
      z: -18,
      telegraphSeconds: 3,
      safePoint: { x: -2.6, y: 1.35 },
    } as BallObstacle;
    const simulation = simulationWith([block, gate]);

    scene.render(simulation, 1 / 60);
    expect(canvas.dataset.telegraphKind).toBe('gate');
    expect(Number(canvas.dataset.telegraphTti)).toBeGreaterThan(0);
    expect(Number(canvas.dataset.telegraphTti)).toBeLessThanOrEqual(2);
    expect(Number(canvas.dataset.telegraphStrength)).toBeGreaterThan(0);
    expect(canvas.dataset.telegraphSafeX).toBe('2.250');
    expect(canvas.dataset.telegraphSafeY).toBe('-1.100');

    const fullStrength = Number(canvas.dataset.telegraphStrength);
    scene.setComfortMode(true);
    scene.render(simulation, 1 / 60);
    expect(Number(canvas.dataset.telegraphStrength)).toBeCloseTo(
      fullStrength * 0.42,
      2,
    );

    gate.passed = true;
    scene.render(simulation, 1 / 60);
    expect(canvas.dataset.telegraphKind).toBe('block');
    expect(canvas.dataset.telegraphSafeX).toBe('-2.600');
    expect(canvas.dataset.telegraphSafeY).toBe('1.350');

    block.passed = true;
    scene.render(simulation, 1 / 60);
    expect(canvas.dataset).toMatchObject({
      telegraphKind: 'none',
      telegraphTti: '-1.000',
      telegraphStrength: '0.000',
    });

    scene.dispose();
    host.remove();
  });

  it('keeps an upcoming cue hidden until its own authored window opens', async () => {
    const host = sizedHost();
    const scene = await SignalRunBabylonScene.create(host, {
      engineFactory: nullEngineFactory(),
      resizeObserverFactory: () => ({ observe: vi.fn(), disconnect: vi.fn() }),
    });
    const far = {
      ...obstacle(0, 'gate'),
      z: -40,
      telegraphSeconds: 0.5,
      safePoint: { x: 1, y: 1 },
    } as BallObstacle;

    scene.render(simulationWith([far]), 1 / 60);
    expect(scene.getCanvas().dataset).toMatchObject({
      telegraphKind: 'none',
      telegraphTti: '-1.000',
      telegraphStrength: '0.000',
    });

    scene.dispose();
    host.remove();
  });

  it('keeps an early phone solid cue large and separated on its protected guide plane', async () => {
    const host = sizedHost(320, 568);
    const scene = await SignalRunBabylonScene.create(host, {
      engineFactory: nullEngineFactory(),
      resizeObserverFactory: () => ({ observe: vi.fn(), disconnect: vi.fn() }),
      touchFirst: true,
    });
    const earlyBlock = {
      ...obstacle(1, 'block'),
      depth: 2.4,
      z: -30.1,
      telegraphSeconds: 3.15,
      safePoint: { x: 2.8, y: 0 },
    } as BallObstacle;

    scene.render(simulationWith([earlyBlock]), 1 / 60);
    const canvas = scene.getCanvas();
    expect(canvas.dataset.telegraphKind).toBe('block');
    expect(Number(canvas.dataset.telegraphTti)).toBeGreaterThan(2.3);
    expect(Number(canvas.dataset.telegraphTti)).toBeLessThan(2.5);
    expect(canvas.dataset.telegraphSafeX).toBe('2.800');
    expect(canvas.dataset.telegraphSafeY).toBe('0.000');
    expect(canvas.dataset.telegraphGuideZ).toBe('4.500');
    expect(Number(canvas.dataset.telegraphScale)).toBeGreaterThanOrEqual(0.9);

    earlyBlock.passed = true;
    scene.render(simulationWith([earlyBlock]), 1 / 60);
    expect(canvas.dataset).toMatchObject({
      telegraphKind: 'none',
      telegraphGuideZ: '0.000',
      telegraphScale: '0.000',
    });

    scene.dispose();
    host.remove();
  });

  it('applies the performance ratio to the real backing buffer', async () => {
    const host = sizedHost();
    const capture: EngineCapture = {
      hardwareScalingLevel: 1,
      resizeCalls: 0,
    };
    const scene = await SignalRunBabylonScene.create(host, {
      engineFactory: nullEngineFactory(capture),
      resizeObserverFactory: () => ({ observe: vi.fn(), disconnect: vi.fn() }),
      touchFirst: true,
    });
    const canvas = scene.getCanvas();
    const simulation = simulationWith();

    // Balanced touch starts at .86. Sustained 50 ms evidence demotes once the
    // governor's two-second window is full, with no native-size setSize call.
    for (let index = 0; index < 45; index += 1) {
      scene.render(simulation, 0.05);
    }
    expect(canvas.dataset.qualityTier).toBe('performance');
    const ratio = Number(canvas.dataset.pixelRatio);
    expect(ratio).toBeCloseTo(0.48, 3);
    expect(canvas.width).toBeCloseTo(640 * ratio, 0);
    expect(canvas.height).toBeCloseTo(360 * ratio, 0);
    expect(capture.resizeCalls).toBeGreaterThan(0);

    scene.dispose();
    host.remove();
  });

  it('disposes a late engine result after an aborted creation', async () => {
    const host = sizedHost();
    const controller = new AbortController();
    const dispose = vi.fn();
    let resolveFactory: ((selection: {
      engine: NullEngine;
      backend: 'webgl';
    }) => void) | undefined;
    const engineFactory: SignalRunEngineFactory = () => new Promise((resolve) => {
      resolveFactory = resolve;
    });

    const pending = SignalRunBabylonScene.create(host, {
      engineFactory,
      signal: controller.signal,
    });
    controller.abort();
    resolveFactory?.({
      engine: { dispose } as unknown as NullEngine,
      backend: 'webgl',
    });

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(dispose).toHaveBeenCalledTimes(1);
    expect(host.querySelector('canvas')).toBeNull();
    host.remove();
  });
});
