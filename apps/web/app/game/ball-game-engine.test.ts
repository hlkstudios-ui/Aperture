import type { BallSimulation } from './ball-simulation';

const harness = vi.hoisted(() => ({
  audio: {
    crash: vi.fn(),
    damage: vi.fn(),
    dispose: vi.fn(),
    extraction: vi.fn(),
    gate: vi.fn(),
    overdrive: vi.fn(),
    sector: vi.fn(),
    setMuted: vi.fn(),
    setRunning: vi.fn(),
    setSpeed: vi.fn(),
    unlock: vi.fn(async () => true),
  },
  createPhysics: vi.fn(),
  createScene: vi.fn(),
  physicsFail: false,
  physicsInstances: [] as Array<Record<string, ReturnType<typeof vi.fn>>>,
  sceneInstances: [] as Array<{
    canvas: HTMLCanvasElement;
    physicsBackend: 'rapier' | 'none';
    getCanvas: ReturnType<typeof vi.fn>;
    render: ReturnType<typeof vi.fn>;
    syncDebris: ReturnType<typeof vi.fn>;
    impact: ReturnType<typeof vi.fn>;
    gate: ReturnType<typeof vi.fn>;
    overdrive: ReturnType<typeof vi.fn>;
    setComfortMode: ReturnType<typeof vi.fn>;
    pause: ReturnType<typeof vi.fn>;
    resume: ReturnType<typeof vi.fn>;
    getDiagnostics: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
  }>,
}));

vi.mock('./ball-audio', () => ({
  BallSignalRunAudio: function BallSignalRunAudio() {
    return harness.audio;
  },
}));

vi.mock('./rendering/signal-run-babylon-scene', () => ({
  SignalRunBabylonScene: {
    create: harness.createScene,
  },
}));

vi.mock('./physics/ball-rapier-physics', () => ({
  BallRapierPhysics: {
    create: harness.createPhysics,
  },
}));

import {
  BallGameEngine,
  ballPrimedDirectionLabel,
  snapshotOfBall,
} from './ball-game-engine';
import {
  BALL_CONTRACT_TICKS,
  BALL_FIXED_STEP_SECONDS,
  createBallSimulation,
} from './ball-simulation';
import type { BallGameEngineOptions } from './ball-game-types';

function engineOptions(): BallGameEngineOptions {
  return {
    onReady: vi.fn(),
    onSnapshot: vi.fn(),
    onImpact: vi.fn(),
    onGate: vi.fn(),
    onPace: vi.fn(),
    onOverdrive: vi.fn(),
    onCrash: vi.fn(),
    onExtract: vi.fn(),
    onPrimedInput: vi.fn(),
    onPhysicsFallback: vi.fn(),
    onError: vi.fn(),
  };
}

function pointerEvent(
  type: string,
  init: {
    clientX: number;
    clientY: number;
    pointerId?: number;
    pointerType?: string;
  },
): PointerEvent {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperties(event, {
    clientX: { value: init.clientX },
    clientY: { value: init.clientY },
    pointerId: { value: init.pointerId ?? 1 },
    pointerType: { value: init.pointerType ?? 'touch' },
  });
  return event as PointerEvent;
}

describe('BallGameEngine helpers', () => {
  it('exposes concise direction labels and truthful snapshots', () => {
    expect(ballPrimedDirectionLabel(0, 0)).toBeNull();
    expect(ballPrimedDirectionLabel(1, 0)).toBe('Right');
    expect(ballPrimedDirectionLabel(-1, 1)).toBe('Upper left');

    const simulation = createBallSimulation('snapshot');
    simulation.score = 123.75;
    simulation.nearMisses = 2;
    const snapshot = snapshotOfBall(simulation);
    expect(snapshot).toMatchObject({
      status: 'running',
      score: 123,
      exactScore: 123.75,
      contractRemaining: 105,
      nearMisses: 2,
      ball: { x: 0, y: 0 },
    });
    expect(snapshot.ball).not.toBe(simulation.ball.position);
  });
});

describe('BallGameEngine lifecycle and input', () => {
  let nextAnimationFrame = 1;
  let animationFrames: Map<number, FrameRequestCallback>;

  const runFrame = (timestamp: number) => {
    const entry = [...animationFrames.entries()][0];
    if (!entry) throw new Error('Expected one scheduled animation frame.');
    animationFrames.delete(entry[0]);
    entry[1](timestamp);
  };

  beforeEach(() => {
    animationFrames = new Map();
    nextAnimationFrame = 1;
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      const id = nextAnimationFrame;
      nextAnimationFrame += 1;
      animationFrames.set(id, callback);
      return id;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id) => {
      animationFrames.delete(id);
    });
    if (typeof window.matchMedia !== 'function') {
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: vi.fn(() => ({ matches: false })),
      });
    }

    harness.physicsFail = false;
    harness.physicsInstances.length = 0;
    harness.sceneInstances.length = 0;
    for (const method of Object.values(harness.audio)) {
      if ('mockClear' in method) method.mockClear();
    }
    harness.createScene.mockReset();
    harness.createPhysics.mockReset();

    harness.createPhysics.mockImplementation(async () => {
      if (harness.physicsFail) throw new Error('Rapier unavailable');
      const physics = {
        reset: vi.fn(),
        resume: vi.fn(),
        pause: vi.fn(),
        fixedStep: vi.fn(() => ({ contacts: [] })),
        forEachActiveDebrisPose: vi.fn(),
        emitImpact: vi.fn(),
        emitGate: vi.fn(),
        emitOverdrive: vi.fn(),
        getDiagnostics: vi.fn(() => ({ disposed: false, paused: false })),
        dispose: vi.fn(),
      };
      harness.physicsInstances.push(physics);
      return physics;
    });

    harness.createScene.mockImplementation(async (
      host: HTMLElement,
      options: { physicsBackend: 'rapier' | 'none'; signal?: AbortSignal },
    ) => {
      if (options.signal?.aborted) {
        throw new DOMException('Aborted', 'AbortError');
      }
      const canvas = host.ownerDocument.createElement('canvas');
      canvas.className = 'signal-run__canvas';
      host.appendChild(canvas);
      const scene = {
        canvas,
        physicsBackend: options.physicsBackend,
        getCanvas: vi.fn(() => canvas),
        render: vi.fn(),
        syncDebris: vi.fn(),
        impact: vi.fn(),
        gate: vi.fn(),
        overdrive: vi.fn(),
        setComfortMode: vi.fn(),
        pause: vi.fn(),
        resume: vi.fn(),
        getDiagnostics: vi.fn(() => ({
          renderBackend: 'webgl',
          physicsBackend: options.physicsBackend,
        })),
        dispose: vi.fn(() => canvas.remove()),
      };
      harness.sceneInstances.push(scene);
      return scene;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.replaceChildren();
  });

  async function readyEngine(options = engineOptions()) {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const engine = new BallGameEngine(host, options);
    await vi.waitFor(() => expect(options.onReady).toHaveBeenCalledTimes(1));
    return { engine, host, options, scene: harness.sceneInstances.at(-1)! };
  }

  it('owns one canvas and one RAF, then disposes every sidecar once', async () => {
    const { engine, host, scene } = await readyEngine();
    expect(host.querySelectorAll('canvas')).toHaveLength(1);
    expect(engine.getDiagnostics()).toMatchObject({
      ready: true,
      running: false,
      physicsBackend: 'rapier',
      renderBackend: 'webgl',
      canvasCount: 1,
    });

    engine.prepareRun('one-loop');
    engine.primeInput();
    const canvas = scene.canvas;
    expect(canvas.tabIndex).toBe(0);
    expect(canvas).toHaveAttribute('aria-describedby', 'signal-run-controls');
    expect(canvas).toHaveAttribute('aria-keyshortcuts');
    engine.start();
    engine.start();
    expect(animationFrames.size).toBe(1);
    runFrame(100);
    expect(animationFrames.size).toBe(1);

    engine.dispose();
    engine.dispose();
    expect(animationFrames.size).toBe(0);
    expect(scene.dispose).toHaveBeenCalledTimes(1);
    expect(harness.physicsInstances[0].dispose).toHaveBeenCalledTimes(1);
    expect(harness.audio.dispose).toHaveBeenCalledTimes(1);
    expect(host.querySelectorAll('canvas')).toHaveLength(0);
  });

  it('stages direct keys and a target-relative drag without advancing or tapping', async () => {
    const { engine, options, scene } = await readyEngine();
    engine.prepareRun('staged-drag');
    const before = engine.getSnapshot();
    engine.primeInput();
    engine.setKey('KeyD', true);
    expect(options.onPrimedInput).toHaveBeenLastCalledWith({ direction: 'Right' });
    expect(engine.getSnapshot().elapsed).toBe(before.elapsed);
    engine.setKey('KeyD', false);

    const canvas = scene.canvas;
    canvas.dispatchEvent(pointerEvent('pointerdown', { clientX: 100, clientY: 100 }));
    canvas.dispatchEvent(pointerEvent('pointerup', { clientX: 100, clientY: 100 }));
    expect(options.onGate).not.toHaveBeenCalled();
    expect(options.onImpact).not.toHaveBeenCalled();
    expect(engine.getSnapshot().elapsed).toBe(before.elapsed);

    canvas.dispatchEvent(pointerEvent('pointerdown', { clientX: 100, clientY: 100 }));
    canvas.dispatchEvent(pointerEvent('pointermove', { clientX: 160, clientY: 100 }));
    canvas.dispatchEvent(pointerEvent('pointerup', { clientX: 160, clientY: 100 }));
    expect(options.onPrimedInput).toHaveBeenLastCalledWith({ direction: 'Right' });

    engine.start();
    runFrame(1_000);
    for (let index = 1; index <= 32; index += 1) {
      runFrame(1_000 + index * 16.7);
    }
    expect(engine.getSnapshot().ball.x).toBeGreaterThan(0.2);
    engine.dispose();
  });

  it('drops an interrupted pointer target instead of steering toward stale input', async () => {
    const { engine, options, scene } = await readyEngine();
    engine.prepareRun('cancelled-drag');
    engine.primeInput();
    const canvas = scene.canvas;
    canvas.dispatchEvent(pointerEvent('pointerdown', { clientX: 80, clientY: 100 }));
    canvas.dispatchEvent(pointerEvent('pointermove', { clientX: 180, clientY: 100 }));
    expect(options.onPrimedInput).toHaveBeenLastCalledWith({ direction: 'Right' });

    canvas.dispatchEvent(pointerEvent('pointercancel', { clientX: 180, clientY: 100 }));
    expect(options.onPrimedInput).toHaveBeenLastCalledWith({ direction: null });
    engine.start();
    runFrame(1_000);
    for (let index = 1; index <= 24; index += 1) {
      runFrame(1_000 + index * 16.7);
    }
    expect(engine.getSnapshot().ball.x).toBeCloseTo(0, 8);
    engine.dispose();
  });

  it('freezes authoritative time while paused', async () => {
    const { engine } = await readyEngine();
    engine.prepareRun('pause-freeze');
    engine.start();
    runFrame(2_000);
    runFrame(2_017);
    const moving = engine.getSnapshot();
    expect(moving.elapsed).toBeGreaterThan(0);

    engine.pause();
    const paused = engine.getSnapshot();
    expect(animationFrames.size).toBe(0);
    expect(engine.getDiagnostics().running).toBe(false);
    expect(engine.getSnapshot()).toEqual(paused);
    engine.dispose();
  });

  it('emits a gate event once even across later render frames', async () => {
    const { engine, options, scene } = await readyEngine();
    engine.prepareRun('one-shot-gate');
    const simulation = (
      engine as unknown as { simulation: BallSimulation }
    ).simulation;
    for (const obstacle of simulation.obstacles) obstacle.active = false;
    Object.assign(simulation.obstacles[0], {
      active: true,
      kind: 'gate',
      x: 0,
      y: 0,
      z: -0.6,
      depth: 1,
      openingRadius: 4,
      passed: false,
      hit: false,
    });

    engine.start();
    runFrame(3_000);
    runFrame(3_017);
    expect(options.onGate).toHaveBeenCalledTimes(1);
    expect(scene.gate).toHaveBeenCalledTimes(1);
    expect(harness.audio.gate).toHaveBeenCalledTimes(1);
    for (let index = 1; index <= 8; index += 1) {
      runFrame(3_017 + index * 17);
    }
    expect(options.onGate).toHaveBeenCalledTimes(1);
    expect(scene.gate).toHaveBeenCalledTimes(1);
    engine.dispose();
  });

  it('treats the third impact as terminal and never schedules another frame', async () => {
    const { engine, options, scene } = await readyEngine();
    engine.prepareRun('terminal-impact');
    const simulation = (
      engine as unknown as { simulation: BallSimulation }
    ).simulation;
    simulation.shields = 1;
    for (const obstacle of simulation.obstacles) obstacle.active = false;
    Object.assign(simulation.obstacles[0], {
      active: true,
      kind: 'block',
      x: 0,
      y: 0,
      z: 0,
      depth: 2,
      width: 8,
      height: 8,
      passed: false,
      hit: false,
    });

    engine.start();
    runFrame(4_000);
    runFrame(4_017);
    expect(options.onImpact).toHaveBeenCalledTimes(1);
    expect(options.onCrash).toHaveBeenCalledTimes(1);
    expect(engine.getSnapshot().status).toBe('crashed');
    expect(animationFrames.size).toBe(0);
    expect(scene.canvas.tabIndex).toBe(-1);
    expect(scene.canvas.dataset.gameState).toBe('crashed');
    engine.dispose();
  });

  it('reports extraction exactly once, stops its loop, and can restart cleanly', async () => {
    const { engine, options, scene } = await readyEngine();
    engine.prepareRun('finish-once');
    const simulation = (
      engine as unknown as { simulation: BallSimulation }
    ).simulation;
    for (const obstacle of simulation.obstacles) {
      obstacle.active = true;
      obstacle.z = -10_000;
    }
    simulation.tick = BALL_CONTRACT_TICKS - 1;
    simulation.elapsed = simulation.tick * BALL_FIXED_STEP_SECONDS;

    engine.start();
    runFrame(5_000);
    runFrame(5_017);
    expect(options.onExtract).toHaveBeenCalledTimes(1);
    expect(options.onCrash).not.toHaveBeenCalled();
    expect(harness.audio.extraction).toHaveBeenCalledTimes(1);
    expect(engine.getSnapshot()).toMatchObject({
      status: 'extracted',
      contractRemaining: 0,
    });
    expect(animationFrames.size).toBe(0);
    expect(scene.canvas.dataset.gameState).toBe('extracted');

    engine.start();
    expect(options.onExtract).toHaveBeenCalledTimes(1);
    expect(harness.audio.extraction).toHaveBeenCalledTimes(1);
    expect(animationFrames.size).toBe(0);

    engine.prepareRun('fresh-after-finish');
    expect(engine.getSnapshot()).toMatchObject({
      status: 'running',
      elapsed: 0,
      contractRemaining: 105,
    });
    engine.start();
    expect(animationFrames.size).toBe(1);
    engine.dispose();
  });

  it('keeps the game ready and announces an honest Rapier fallback', async () => {
    harness.physicsFail = true;
    const options = engineOptions();
    const { engine, scene } = await readyEngine(options);
    await vi.waitFor(() => {
      expect(options.onPhysicsFallback).toHaveBeenCalledTimes(1);
    });
    expect(engine.getDiagnostics()).toMatchObject({
      ready: true,
      physicsBackend: 'none',
      renderBackend: 'webgl',
    });
    expect(scene.physicsBackend).toBe('none');
    engine.dispose();
  });
});
