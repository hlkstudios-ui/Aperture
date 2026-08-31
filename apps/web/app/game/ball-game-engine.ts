import { BallSignalRunAudio } from './ball-audio';
import {
  BALL_CONTRACT_DURATION_SECONDS,
  BALL_PLAY_RADIUS,
  createBallSimulation,
  stepBallSimulation,
  type BallGateEvent,
  type BallImpactEvent,
  type BallInput,
  type BallPace,
  type BallSeed,
  type BallSimulation,
  type BallSimulationOptions,
  type BallStatus,
} from './ball-simulation';
import type {
  BallGameDiagnostics,
  BallGameEngineOptions,
  BallGameSnapshot,
  BallPrimedInputFeedback,
} from './ball-game-types';
import type {
  SignalRunBabylonScene,
  SignalRunDebrisPose,
} from './rendering/signal-run-babylon-scene';

const SNAPSHOT_INTERVAL_SECONDS = 0.1;
const MAX_FRAME_DELTA_SECONDS = 0.25;
const POINTER_PIXELS_PER_WORLD_UNIT = 30;
const TARGET_INPUT_GAIN = 0.82;

const EMPTY_PRIMED_INPUT: BallPrimedInputFeedback = Object.freeze({
  direction: null,
});

interface PointerTargetGesture {
  id: number;
  originClientX: number;
  originClientY: number;
  originBallX: number;
  originBallY: number;
}

interface BallPhysicsDiagnosticsLike {
  disposed?: boolean;
  paused?: boolean;
  [key: string]: unknown;
}

interface BallPhysicsSidecar {
  reset(simulation: Readonly<BallSimulation>): void;
  resume(simulation: Readonly<BallSimulation>): void;
  pause(): void;
  fixedStep(simulation: Readonly<BallSimulation>): unknown;
  forEachActiveDebrisPose(
    callback: (pose: Readonly<SignalRunDebrisPose>) => void,
  ): void;
  emitImpact?(
    event: Readonly<BallImpactEvent>,
    strength?: number,
  ): void;
  emitGate?(
    event: Readonly<BallGateEvent>,
    strength?: number,
  ): void;
  emitOverdrive?(
    position: Readonly<{ x: number; y: number; z: number }>,
  ): void;
  getDiagnostics(): BallPhysicsDiagnosticsLike;
  dispose(): void;
}

interface BallPhysicsConstructor {
  create(options: { touchFirst: boolean }): Promise<BallPhysicsSidecar>;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizedVector(x: number, y: number): { x: number; y: number } {
  let safeX = Number.isFinite(x) ? clamp(x, -1, 1) : 0;
  let safeY = Number.isFinite(y) ? clamp(y, -1, 1) : 0;
  const length = Math.hypot(safeX, safeY);
  if (length > 1) {
    safeX /= length;
    safeY /= length;
  }
  return { x: safeX, y: safeY };
}

function clampTargetToPlayfield(x: number, y: number) {
  const distance = Math.hypot(x, y);
  if (distance <= BALL_PLAY_RADIUS || distance <= 1e-8) return { x, y };
  return {
    x: x / distance * BALL_PLAY_RADIUS,
    y: y / distance * BALL_PLAY_RADIUS,
  };
}

export function ballPrimedDirectionLabel(
  x: number,
  y: number,
): string | null {
  const horizontal = x > 0.15 ? 'Right' : x < -0.15 ? 'Left' : '';
  const vertical = y > 0.15 ? 'Upper' : y < -0.15 ? 'Lower' : '';
  if (!horizontal && !vertical) return null;
  return vertical && horizontal
    ? `${vertical} ${horizontal.toLowerCase()}`
    : vertical || horizontal;
}

export function snapshotOfBall(
  simulation: Readonly<BallSimulation>,
): BallGameSnapshot {
  return {
    status: simulation.status,
    score: Math.floor(simulation.score),
    exactScore: simulation.score,
    distance: simulation.distance,
    elapsed: simulation.elapsed,
    contractRemaining: Math.max(
      0,
      BALL_CONTRACT_DURATION_SECONDS - simulation.elapsed,
    ),
    speed: simulation.speed,
    pace: simulation.pace,
    integrity: simulation.shields,
    combo: simulation.combo,
    ball: { ...simulation.ball.position },
    gatesCleared: simulation.cleanGates,
    nearMisses: simulation.nearMisses,
    impacts: simulation.impacts,
    overdriveCharge: simulation.overdriveCharge,
    overdriveRemaining: simulation.overdriveRemaining,
    overdriveActivations: simulation.overdriveActivations,
  };
}

/**
 * Owns Signal Run's single fixed-step clock and input lifecycle. Babylon and
 * Rapier consume readonly snapshots; neither presentation sidecar can mutate
 * collision, score, shields, gates, Overdrive, or terminal crash truth.
 */
export class BallGameEngine {
  private readonly host: HTMLElement;
  private readonly options: BallGameEngineOptions;
  private readonly audio = new BallSignalRunAudio();
  private readonly touchFirst: boolean;
  private readonly abortController = new AbortController();
  private readonly keys = new Set<string>();

  private scene: SignalRunBabylonScene | null = null;
  private physics: BallPhysicsSidecar | null = null;
  private simulation: BallSimulation = createBallSimulation(1);
  private canvas: HTMLCanvasElement | null = null;
  private pointer: PointerTargetGesture | null = null;
  private pointerTarget: { x: number; y: number } | null = null;
  private running = false;
  private inputPrimed = false;
  private animationFrame: number | null = null;
  private lastFrameTime = 0;
  private snapshotElapsed = 0;
  private audioElapsed = 0;
  private disposed = false;
  private ready = false;
  private comfortMode = false;
  private primedSignature = '';
  private terminalReported: Exclude<BallStatus, 'running'> | null = null;

  constructor(host: HTMLElement, options: BallGameEngineOptions) {
    this.host = host;
    this.options = options;
    this.touchFirst = typeof window.matchMedia === 'function' &&
      window.matchMedia('(hover: none), (pointer: coarse)').matches;
    void this.initialize();
  }

  private async initialize() {
    let pendingScene: SignalRunBabylonScene | null = null;
    let pendingPhysics: BallPhysicsSidecar | null = null;
    try {
      const [{ SignalRunBabylonScene }, physicsModule] = await Promise.all([
        import('./rendering/signal-run-babylon-scene'),
        import('./physics/ball-rapier-physics').catch(() => null),
      ]);
      if (physicsModule) {
        const Physics = (
          physicsModule as unknown as { BallRapierPhysics?: BallPhysicsConstructor }
        ).BallRapierPhysics;
        if (Physics) {
          try {
            pendingPhysics = await Physics.create({ touchFirst: this.touchFirst });
          } catch {
            pendingPhysics = null;
          }
        }
      }
      if (this.disposed || this.abortController.signal.aborted) {
        pendingPhysics?.dispose();
        return;
      }

      pendingScene = await SignalRunBabylonScene.create(this.host, {
        signal: this.abortController.signal,
        touchFirst: this.touchFirst,
        comfortMode: this.comfortMode,
        physicsBackend: pendingPhysics ? 'rapier' : 'none',
      });
      if (this.disposed || this.abortController.signal.aborted) {
        pendingScene.dispose();
        pendingPhysics?.dispose();
        return;
      }

      this.scene = pendingScene;
      this.physics = pendingPhysics;
      this.canvas = pendingScene.getCanvas();
      this.configureCanvas(this.canvas);
      this.installPointerInput(this.canvas);
      this.physics?.reset(this.simulation);
      pendingScene.render(this.simulation, 0, true);
      pendingScene.pause();
      pendingScene = null;
      pendingPhysics = null;
      this.ready = true;
      this.updateCanvasState('idle');
      queueMicrotask(() => {
        if (this.disposed) return;
        this.options.onReady();
        if (!this.physics) this.options.onPhysicsFallback?.();
      });
    } catch (error) {
      pendingScene?.dispose();
      pendingPhysics?.dispose();
      if (this.disposed || this.abortController.signal.aborted) return;
      const detail = error instanceof Error ? error.message : '';
      this.options.onError?.(
        detail
          ? `The Signal Run renderer could not initialize: ${detail}`
          : 'The Signal Run renderer could not initialize. Hardware acceleration may be disabled.',
      );
    }
  }

  private configureCanvas(canvas: HTMLCanvasElement) {
    canvas.dataset.renderProfile = this.touchFirst ? 'touch' : 'desktop';
    canvas.dataset.physicsBackend = this.physics ? 'rapier' : 'none';
    canvas.dataset.playerAvatar = 'ball';
    canvas.setAttribute('role', 'application');
    canvas.setAttribute('aria-label', 'Signal Run luminous ball tunnel');
    canvas.setAttribute('aria-describedby', 'signal-run-controls');
    canvas.setAttribute(
      'aria-description',
      'Steer the ball with W A S D, arrow keys, or a target-relative drag. Pass through bright gates and avoid solid blocks.',
    );
    canvas.setAttribute(
      'aria-keyshortcuts',
      'W A S D ArrowUp ArrowDown ArrowLeft ArrowRight',
    );
    canvas.tabIndex = -1;
    canvas.setAttribute('aria-disabled', 'true');
  }

  private installPointerInput(canvas: HTMLCanvasElement) {
    canvas.addEventListener('pointerdown', this.handlePointerDown);
    canvas.addEventListener('pointermove', this.handlePointerMove);
    canvas.addEventListener('pointerup', this.handlePointerUp);
    canvas.addEventListener('pointercancel', this.handlePointerCancel);
    canvas.addEventListener('lostpointercapture', this.handleLostPointerCapture);
  }

  private removePointerInput(canvas: HTMLCanvasElement) {
    canvas.removeEventListener('pointerdown', this.handlePointerDown);
    canvas.removeEventListener('pointermove', this.handlePointerMove);
    canvas.removeEventListener('pointerup', this.handlePointerUp);
    canvas.removeEventListener('pointercancel', this.handlePointerCancel);
    canvas.removeEventListener('lostpointercapture', this.handleLostPointerCapture);
  }

  private canAcceptInput() {
    return !this.disposed && (this.running || this.inputPrimed);
  }

  private handlePointerDown = (event: PointerEvent) => {
    if (!this.canAcceptInput() || this.pointer) return;
    event.preventDefault();
    this.pointer = {
      id: event.pointerId,
      originClientX: event.clientX,
      originClientY: event.clientY,
      originBallX: this.simulation.ball.position.x,
      originBallY: this.simulation.ball.position.y,
    };
    this.pointerTarget = {
      x: this.simulation.ball.position.x,
      y: this.simulation.ball.position.y,
    };
    try {
      this.canvas?.setPointerCapture(event.pointerId);
    } catch {
      // Capture improves continuity but is not required for deterministic input.
    }
    this.emitPrimedInput();
  };

  private handlePointerMove = (event: PointerEvent) => {
    const pointer = this.pointer;
    if (!pointer || pointer.id !== event.pointerId || !this.canAcceptInput()) {
      return;
    }
    event.preventDefault();
    const target = clampTargetToPlayfield(
      pointer.originBallX +
        (event.clientX - pointer.originClientX) / POINTER_PIXELS_PER_WORLD_UNIT,
      pointer.originBallY -
        (event.clientY - pointer.originClientY) / POINTER_PIXELS_PER_WORLD_UNIT,
    );
    this.pointerTarget = target;
    this.emitPrimedInput();
  };

  private finishPointer(event: PointerEvent) {
    if (!this.pointer || this.pointer.id !== event.pointerId) return;
    this.pointer = null;
    try {
      this.canvas?.releasePointerCapture(event.pointerId);
    } catch {
      // The browser may already have released capture.
    }
    // The target intentionally survives release. Input decays as the physical
    // ball approaches it, avoiding the old snap-to-zero steering discontinuity.
    this.emitPrimedInput();
  }

  private handlePointerUp = (event: PointerEvent) => {
    event.preventDefault();
    this.finishPointer(event);
  };

  private handlePointerCancel = (event: PointerEvent) => {
    this.finishPointer(event);
    // Cancellation means the gesture was interrupted by the browser or OS,
    // not that the player deliberately chose a destination. Drop that target
    // so the ball naturally damps instead of continuing a stale steer.
    this.pointerTarget = null;
    this.emitPrimedInput();
  };

  private handleLostPointerCapture = (event: PointerEvent) => {
    this.finishPointer(event);
  };

  private keyboardInput(): BallInput {
    return normalizedVector(
      Number(this.keys.has('ArrowRight') || this.keys.has('KeyD')) -
        Number(this.keys.has('ArrowLeft') || this.keys.has('KeyA')),
      Number(this.keys.has('ArrowUp') || this.keys.has('KeyW')) -
        Number(this.keys.has('ArrowDown') || this.keys.has('KeyS')),
    );
  }

  private targetInput(): BallInput {
    if (!this.pointerTarget) return { x: 0, y: 0 };
    const deltaX = this.pointerTarget.x - this.simulation.ball.position.x;
    const deltaY = this.pointerTarget.y - this.simulation.ball.position.y;
    const distance = Math.hypot(deltaX, deltaY);
    if (distance <= 0.015) return { x: 0, y: 0 };
    const strength = clamp(distance * TARGET_INPUT_GAIN, 0, 1);
    return {
      x: deltaX / distance * strength,
      y: deltaY / distance * strength,
    };
  }

  private inputVector(): BallInput {
    const keyboard = this.keyboardInput();
    if (Math.hypot(keyboard.x, keyboard.y) > 0) return keyboard;
    return this.targetInput();
  }

  private emitPrimedInput() {
    if (!this.inputPrimed) return;
    const input = this.inputVector();
    const feedback: BallPrimedInputFeedback = {
      direction: ballPrimedDirectionLabel(input.x, input.y),
    };
    const signature = feedback.direction ?? '';
    if (signature === this.primedSignature) return;
    this.primedSignature = signature;
    this.options.onPrimedInput(feedback);
  }

  private setSurfaceInteractive(interactive: boolean) {
    if (!this.canvas) return;
    this.canvas.tabIndex = interactive ? 0 : -1;
    this.canvas.setAttribute('aria-disabled', String(!interactive));
  }

  private updateCanvasState(state: string) {
    if (!this.canvas) return;
    this.canvas.dataset.gameState = state;
    this.canvas.dataset.simulationStatus = this.simulation.status;
    this.canvas.dataset.ballX = this.simulation.ball.position.x.toFixed(3);
    this.canvas.dataset.ballY = this.simulation.ball.position.y.toFixed(3);
    this.canvas.dataset.ballRadius = this.simulation.ball.radius.toFixed(3);
  }

  private scheduleFrame() {
    if (!this.running || this.animationFrame !== null || this.disposed) return;
    this.animationFrame = window.requestAnimationFrame(this.frame);
  }

  private frame = (timestamp: number) => {
    this.animationFrame = null;
    if (!this.running || this.disposed) return;
    const deltaSeconds = this.lastFrameTime > 0
      ? clamp((timestamp - this.lastFrameTime) / 1_000, 0, MAX_FRAME_DELTA_SECONDS)
      : 0;
    this.lastFrameTime = timestamp;

    const previousTick = this.simulation.tick;
    const previousPace = this.simulation.pace;
    const previousImpactSequence = this.simulation.impactEventSequence;
    const previousGateSequence = this.simulation.gateEventSequence;
    const previousOverdriveActivations = this.simulation.overdriveActivations;

    stepBallSimulation(this.simulation, this.inputVector(), deltaSeconds);
    if (this.simulation.tick > previousTick) {
      const steps = Math.min(this.simulation.tick - previousTick, 15);
      for (let index = 0; index < steps; index += 1) {
        this.physics?.fixedStep(this.simulation);
      }
    }

    // Publish the regular HUD snapshot before one-shot gameplay callbacks so a
    // gate, impact, or Overdrive message from this frame remains the audible
    // priority over a coincident finish-countdown threshold.
    this.snapshotElapsed += deltaSeconds;
    if (this.snapshotElapsed >= SNAPSHOT_INTERVAL_SECONDS) {
      this.snapshotElapsed %= SNAPSHOT_INTERVAL_SECONDS;
      this.options.onSnapshot(snapshotOfBall(this.simulation));
    }

    this.emitSimulationEvents({
      previousPace,
      previousImpactSequence,
      previousGateSequence,
      previousOverdriveActivations,
    });
    if (this.physics && this.scene) {
      this.scene.syncDebris((visit) => {
        this.physics?.forEachActiveDebrisPose(visit);
      });
    }
    this.scene?.render(
      this.simulation,
      deltaSeconds,
      previousPace !== this.simulation.pace,
    );
    this.updateCanvasState(this.simulation.status);

    this.audioElapsed += deltaSeconds;
    if (this.audioElapsed >= SNAPSHOT_INTERVAL_SECONDS) {
      this.audioElapsed %= SNAPSHOT_INTERVAL_SECONDS;
      this.audio.setSpeed(this.simulation.speed);
    }

    if (this.simulation.status !== 'running') {
      this.running = false;
      this.lastFrameTime = 0;
      this.setSurfaceInteractive(false);
      this.audio.setRunning(false);
      this.physics?.pause();
      this.scene?.pause();
      this.updateCanvasState(this.simulation.status);
      const snapshot = snapshotOfBall(this.simulation);
      this.options.onSnapshot(snapshot);
      if (this.terminalReported !== this.simulation.status) {
        this.terminalReported = this.simulation.status;
        if (this.simulation.status === 'crashed') {
          this.options.onCrash(snapshot);
        } else {
          this.audio.extraction();
          this.options.onExtract(snapshot);
        }
      }
      return;
    }
    this.scheduleFrame();
  };

  private emitSimulationEvents(previous: {
    previousPace: BallPace;
    previousImpactSequence: number;
    previousGateSequence: number;
    previousOverdriveActivations: number;
  }) {
    if (this.simulation.pace !== previous.previousPace) {
      this.audio.sector(this.simulation.pace);
      this.options.onPace(this.simulation.pace);
    }

    if (
      this.simulation.impactEventSequence > previous.previousImpactSequence &&
      this.simulation.lastImpactEvent
    ) {
      const event = this.simulation.lastImpactEvent;
      this.scene?.impact(event);
      this.physics?.emitImpact?.(
        event,
        event.crashed ? 1.6 : 1,
      );
      this.audio.damage();
      if (event.crashed) this.audio.crash();
      this.options.onImpact(event, snapshotOfBall(this.simulation));
    }

    if (
      this.simulation.gateEventSequence > previous.previousGateSequence &&
      this.simulation.lastGateEvent
    ) {
      const event = this.simulation.lastGateEvent;
      if (event.result === 'clean') {
        this.scene?.gate(event);
        this.physics?.emitGate?.(event, event.nearMiss ? 1.35 : 1);
        this.audio.gate();
      }
      this.options.onGate(event, snapshotOfBall(this.simulation));
    }

    if (
      this.simulation.overdriveActivations >
        previous.previousOverdriveActivations
    ) {
      this.scene?.overdrive(true);
      this.physics?.emitOverdrive?.({
        x: this.simulation.ball.position.x,
        y: this.simulation.ball.position.y,
        z: 0,
      });
      this.audio.overdrive();
      this.options.onOverdrive(snapshotOfBall(this.simulation));
    }
    if (this.simulation.overdriveRemaining <= 0) this.scene?.overdrive(false);
  }

  async unlockAudio() {
    try {
      return await this.audio.unlock();
    } catch {
      this.audio.setMuted(true);
      return false;
    }
  }

  prepareRun(
    seed: BallSeed,
    simulationOptions: BallSimulationOptions = {},
  ) {
    if (this.disposed || !this.ready) return;
    this.stopLoop();
    this.simulation = createBallSimulation(seed, simulationOptions);
    this.terminalReported = null;
    this.inputPrimed = false;
    this.releaseInput();
    this.snapshotElapsed = 0;
    this.audioElapsed = 0;
    this.physics?.reset(this.simulation);
    this.scene?.overdrive(false);
    this.scene?.resume();
    this.scene?.render(this.simulation, 0, true);
    this.scene?.pause();
    this.setSurfaceInteractive(false);
    this.updateCanvasState('idle');
    this.options.onSnapshot(snapshotOfBall(this.simulation));
  }

  primeInput() {
    if (
      this.disposed ||
      !this.ready ||
      this.running ||
      this.simulation.status !== 'running'
    ) return;
    this.inputPrimed = true;
    this.primedSignature = '__initial__';
    this.setSurfaceInteractive(true);
    this.updateCanvasState('countdown');
    this.canvas?.focus({ preventScroll: true });
    this.emitPrimedInput();
  }

  start() {
    if (
      this.disposed ||
      !this.ready ||
      this.running ||
      this.simulation.status !== 'running'
    ) return;
    this.running = true;
    this.inputPrimed = false;
    this.primedSignature = '';
    this.options.onPrimedInput(EMPTY_PRIMED_INPUT);
    this.lastFrameTime = 0;
    this.physics?.resume(this.simulation);
    this.scene?.resume();
    this.setSurfaceInteractive(true);
    this.updateCanvasState('running');
    this.audio.setRunning(true);
    this.canvas?.focus({ preventScroll: true });
    this.scheduleFrame();
  }

  pause() {
    if (this.disposed) return;
    this.running = false;
    this.inputPrimed = false;
    this.stopLoop();
    this.releaseInput();
    this.physics?.pause();
    this.audio.setRunning(false);
    this.scene?.render(this.simulation, 0, true);
    this.scene?.pause();
    this.setSurfaceInteractive(false);
    this.updateCanvasState(
      this.simulation.status === 'running' ? 'paused' : this.simulation.status,
    );
    this.options.onSnapshot(snapshotOfBall(this.simulation));
  }

  getSnapshot(): BallGameSnapshot {
    return snapshotOfBall(this.simulation);
  }

  setKey(code: string, pressed: boolean) {
    if (!this.canAcceptInput()) return;
    if (pressed) this.keys.add(code);
    else this.keys.delete(code);
    this.emitPrimedInput();
  }

  releaseInput() {
    this.keys.clear();
    this.pointerTarget = null;
    if (this.pointer && this.canvas) {
      try {
        this.canvas.releasePointerCapture(this.pointer.id);
      } catch {
        // Capture may already be gone after a blur or visibility transition.
      }
    }
    this.pointer = null;
    this.emitPrimedInput();
  }

  setMuted(muted: boolean) {
    this.audio.setMuted(muted);
  }

  setComfortMode(enabled: boolean) {
    this.comfortMode = enabled;
    this.scene?.setComfortMode(enabled);
    if (!this.running) this.scene?.render(this.simulation, 0, true);
  }

  getDiagnostics(): BallGameDiagnostics {
    const sceneDiagnostics = this.scene?.getDiagnostics();
    return {
      ready: this.ready,
      running: this.running,
      physicsBackend: this.physics ? 'rapier' : 'none',
      renderBackend: sceneDiagnostics?.renderBackend ?? 'none',
      canvasCount: this.host.querySelectorAll('canvas').length,
    };
  }

  private stopLoop() {
    if (this.animationFrame !== null) {
      window.cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    this.lastFrameTime = 0;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.ready = false;
    this.running = false;
    this.inputPrimed = false;
    this.abortController.abort();
    this.stopLoop();
    if (this.canvas) this.removePointerInput(this.canvas);
    this.releaseInput();
    this.audio.dispose();
    this.physics?.dispose();
    this.physics = null;
    this.scene?.dispose();
    this.scene = null;
    this.canvas = null;
  }
}

export type {
  BallGameDiagnostics,
  BallGameEngineOptions,
  BallGameSnapshot,
  BallPrimedInputFeedback,
} from './ball-game-types';
export type { BallGateEvent, BallImpactEvent } from './ball-simulation';
