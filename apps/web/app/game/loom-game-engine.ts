import type { SignalLoomScene } from './rendering/signal-loom-scene';
import type { LoomRapierPhysics } from './physics/loom-rapier-physics';
import { SignalRunAudio } from './audio';
import {
  LOOM_CONTRACT_SECONDS,
  LOOM_RESONANCE_CHARGE_REQUIRED,
  createLoomSimulation,
  loomIrisSecondsToContact,
  stepLoomSimulation,
  type LoomInput,
  type LoomPhase,
  type LoomSeed,
  type LoomSimulation,
} from './loom-simulation';
import type {
  LoomActiveEncounter,
  LoomGameEngineOptions,
  LoomGameSnapshot,
  LoomPrimedInputFeedback,
} from './loom-game-types';

const SNAPSHOT_INTERVAL_SECONDS = 0.1;
const MAX_POINTER_STEER_DISTANCE = 92;
const POINTER_TAP_SLOP = 12;
const POINTER_TAP_DURATION_MS = 320;

interface PointerGesture {
  id: number;
  pointerType: string;
  originX: number;
  originY: number;
  startedAt: number;
  maxExcursion: number;
}

const EMPTY_PRIMED_INPUT: LoomPrimedInputFeedback = Object.freeze({
  direction: null,
  phase: null,
  reel: false,
  resonance: false,
});

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function loomPrimedDirectionLabel(x: number, y: number): string | null {
  const horizontal = x > 0.15 ? 'Right' : x < -0.15 ? 'Left' : '';
  const vertical = y > 0.15 ? 'Upper' : y < -0.15 ? 'Lower' : '';
  if (!horizontal && !vertical) return null;
  return vertical && horizontal
    ? `${vertical} ${horizontal.toLowerCase()}`
    : vertical || horizontal;
}

function activeEncounterForSimulation(
  simulation: Readonly<LoomSimulation>,
): LoomActiveEncounter | null {
  let selected: (typeof simulation.anchors)[number] | null = null;
  for (const anchor of simulation.anchors) {
    if (!anchor.active || anchor.resolved || anchor.z > 1.55) continue;
    if (!selected || anchor.z > selected.z) selected = anchor;
  }
  if (!selected) return null;
  return {
    kind: selected.encounterKind,
    beat: selected.beat,
    route: selected.route,
    phase: selected.phase,
    secondsToContact: Math.max(0, -selected.z) /
      Math.max(simulation.forwardSpeed, 0.001),
  };
}

export function snapshotOfLoom(
  simulation: Readonly<LoomSimulation>,
): LoomGameSnapshot {
  const contractRemaining = Math.max(0, LOOM_CONTRACT_SECONDS - simulation.elapsed);
  return {
    score: Math.floor(simulation.score),
    exactScore: simulation.score,
    distance: simulation.distance,
    elapsed: simulation.elapsed,
    contractRemaining,
    contractProgress: clamp(simulation.elapsed / LOOM_CONTRACT_SECONDS, 0, 1),
    speed: simulation.forwardSpeed,
    phase: simulation.phase,
    arc: simulation.arc,
    activeEncounter: activeEncounterForSimulation(simulation),
    needle: { ...simulation.needle.position },
    echo: { ...simulation.echo.position },
    threadLength: simulation.thread.length,
    threadTension: simulation.thread.tension,
    peakThreadTension: simulation.thread.peakTension,
    reeling: simulation.currentInput.reel,
    stitches: simulation.stitches,
    safeStitches: simulation.safeStitches,
    expressiveStitches: simulation.expressiveStitches,
    missedAnchors: simulation.missedAnchors,
    nearMisses: simulation.nearMisses,
    threadBreaks: simulation.threadBreaks,
    stitchChain: simulation.stitchChain,
    bestStitchChain: simulation.bestStitchChain,
    resonanceCharge: simulation.resonanceCharge,
    resonanceReady:
      simulation.resonanceCharge >= LOOM_RESONANCE_CHARGE_REQUIRED &&
      simulation.resonanceRemaining <= 0 &&
      simulation.resonanceCooldownRemaining <= 0,
    resonanceRemaining: simulation.resonanceRemaining,
    resonanceCooldownRemaining: simulation.resonanceCooldownRemaining,
    resonanceActivations: simulation.resonanceActivations,
    authoredChunksSeen: simulation.authoredChunksSeen,
    iris: {
      ...simulation.iris,
      gapCenter: { ...simulation.iris.gapCenter },
      secondsToContact: loomIrisSecondsToContact(simulation.elapsed),
    },
    extraction: simulation.result,
  };
}

/**
 * Owns the authoritative Loom clock and input lifecycle. Babylon and Rapier
 * are deliberately presentation sidecars: neither can mutate score, latches,
 * phase truth, or extraction results.
 */
export class SignalLoomGameEngine {
  private readonly host: HTMLElement;
  private readonly options: LoomGameEngineOptions;
  private readonly audio = new SignalRunAudio();
  private readonly touchFirst: boolean;
  private readonly abortController = new AbortController();
  private readonly keys = new Set<string>();

  private scene: SignalLoomScene | null = null;
  private physics: LoomRapierPhysics | null = null;
  private simulation: LoomSimulation = createLoomSimulation(1);
  private canvas: HTMLCanvasElement | null = null;
  private pointer: PointerGesture | null = null;
  private virtualInput = { x: 0, y: 0 };
  private running = false;
  private inputPrimed = false;
  private reelHeld = false;
  private pendingPhaseToggle = false;
  private pendingResonanceActivation = false;
  private animationFrame: number | null = null;
  private lastFrameTime = 0;
  private snapshotElapsed = 0;
  private audioElapsed = 0;
  private disposed = false;
  private ready = false;
  private comfortMode = false;
  private primedSignature = '';

  constructor(host: HTMLElement, options: LoomGameEngineOptions) {
    this.host = host;
    this.options = options;
    this.touchFirst = window.matchMedia('(hover: none), (pointer: coarse)').matches;
    void this.initialize();
  }

  private async initialize() {
    let pendingScene: SignalLoomScene | null = null;
    let pendingPhysics: LoomRapierPhysics | null = null;
    try {
      const [{ SignalLoomScene }, physics] = await Promise.all([
        import('./rendering/signal-loom-scene'),
        import('./physics/loom-rapier-physics')
          .then(({ LoomRapierPhysics }) =>
            LoomRapierPhysics.create({ touchFirst: this.touchFirst }),
          )
          .catch(() => null),
      ]);
      pendingPhysics = physics;
      pendingScene = await SignalLoomScene.create(this.host, {
        signal: this.abortController.signal,
        touchFirst: this.touchFirst,
        comfortMode: this.comfortMode,
        physicsBackend: physics ? 'rapier' : 'none',
      });
      if (this.disposed) {
        pendingScene.dispose();
        pendingPhysics?.dispose();
        return;
      }

      this.scene = pendingScene;
      this.physics = physics;
      this.canvas = pendingScene.getCanvas();
      this.configureCanvas(this.canvas);
      this.installPointerInput(this.canvas);
      physics?.reset(this.simulation);
      pendingScene.render(this.simulation, 0, true);
      pendingScene = null;
      pendingPhysics = null;
      this.ready = true;
      queueMicrotask(() => {
        if (this.disposed) return;
        this.options.onReady();
        if (!physics) this.options.onPhysicsFallback?.();
      });
    } catch (error) {
      pendingScene?.dispose();
      pendingPhysics?.dispose();
      if (this.disposed || this.abortController.signal.aborted) return;
      const detail = error instanceof Error ? error.message : '';
      this.options.onError?.(
        detail
          ? `The Signal Loom renderer could not initialize: ${detail}`
          : 'The Signal Loom renderer could not initialize. Hardware acceleration may be disabled.',
      );
    }
  }

  private configureCanvas(canvas: HTMLCanvasElement) {
    canvas.dataset.renderProfile = this.touchFirst ? 'touch' : 'desktop';
    canvas.dataset.physicsBackend = this.physics ? 'rapier' : 'none';
    canvas.setAttribute('role', 'application');
    canvas.setAttribute('aria-label', 'Signal Loom interactive projection conduit');
    canvas.setAttribute(
      'aria-description',
      'Steer the Needle with WASD, arrow keys, drag, or touch controls. Hold Shift or Reel to control the Echo. Press Space to shift phase and R to release stored Resonance.',
    );
    canvas.tabIndex = -1;
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
      pointerType: event.pointerType,
      originX: event.clientX,
      originY: event.clientY,
      startedAt: performance.now(),
      maxExcursion: 0,
    };
    try {
      this.canvas?.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is an enhancement; document-level pointerup still ends it.
    }
  };

  private handlePointerMove = (event: PointerEvent) => {
    const gesture = this.pointer;
    if (!gesture || event.pointerId !== gesture.id || !this.canAcceptInput()) return;
    event.preventDefault();
    const deltaX = event.clientX - gesture.originX;
    const deltaY = event.clientY - gesture.originY;
    gesture.maxExcursion = Math.max(
      gesture.maxExcursion,
      Math.hypot(deltaX, deltaY),
    );
    this.setVirtualDirection(
      clamp(deltaX / MAX_POINTER_STEER_DISTANCE, -1, 1),
      clamp(-deltaY / MAX_POINTER_STEER_DISTANCE, -1, 1),
    );
  };

  private finishPointer(event: PointerEvent, allowTap: boolean) {
    const gesture = this.pointer;
    if (!gesture || event.pointerId !== gesture.id) return;
    const duration = performance.now() - gesture.startedAt;
    const wasTap =
      allowTap &&
      gesture.pointerType === 'mouse' &&
      gesture.maxExcursion <= POINTER_TAP_SLOP &&
      duration <= POINTER_TAP_DURATION_MS;
    this.pointer = null;
    this.virtualInput = { x: 0, y: 0 };
    try {
      this.canvas?.releasePointerCapture(event.pointerId);
    } catch {
      // Capture may already have been released by the browser.
    }
    if (wasTap) this.togglePhase();
    else this.emitPrimedInput();
  }

  private handlePointerUp = (event: PointerEvent) => {
    event.preventDefault();
    this.finishPointer(event, true);
  };

  private handlePointerCancel = (event: PointerEvent) => {
    this.finishPointer(event, false);
  };

  private handleLostPointerCapture = (event: PointerEvent) => {
    this.finishPointer(event, false);
  };

  private inputVector() {
    const keyboardX = Number(this.keys.has('ArrowRight') || this.keys.has('KeyD')) -
      Number(this.keys.has('ArrowLeft') || this.keys.has('KeyA'));
    const keyboardY = Number(this.keys.has('ArrowUp') || this.keys.has('KeyW')) -
      Number(this.keys.has('ArrowDown') || this.keys.has('KeyS'));
    let x = clamp(keyboardX + this.virtualInput.x, -1, 1);
    let y = clamp(keyboardY + this.virtualInput.y, -1, 1);
    const length = Math.hypot(x, y);
    if (length > 1) {
      x /= length;
      y /= length;
    }
    return { x, y };
  }

  private emitPrimedInput() {
    if (!this.inputPrimed) return;
    const direction = loomPrimedDirectionLabel(
      this.inputVector().x,
      this.inputVector().y,
    );
    const phase: LoomPhase | null = this.pendingPhaseToggle
      ? this.simulation.phase === 'ember' ? 'cobalt' : 'ember'
      : null;
    const feedback: LoomPrimedInputFeedback = {
      direction,
      phase,
      reel: this.reelHeld,
      resonance: this.pendingResonanceActivation,
    };
    const signature = JSON.stringify(feedback);
    if (signature === this.primedSignature) return;
    this.primedSignature = signature;
    this.options.onPrimedInput(feedback);
  }

  private setSurfaceInteractive(interactive: boolean) {
    if (!this.canvas) return;
    this.canvas.tabIndex = interactive ? 0 : -1;
    this.canvas.setAttribute('aria-disabled', String(!interactive));
  }

  private scheduleFrame() {
    if (!this.running || this.animationFrame !== null || this.disposed) return;
    this.animationFrame = window.requestAnimationFrame(this.frame);
  }

  private frame = (timestamp: number) => {
    this.animationFrame = null;
    if (!this.running || this.disposed) return;
    const deltaSeconds = this.lastFrameTime > 0
      ? Math.min(Math.max((timestamp - this.lastFrameTime) / 1_000, 0), 0.25)
      : 0;
    this.lastFrameTime = timestamp;
    const previousTick = this.simulation.tick;
    const previousPhase = this.simulation.phase;
    const previousArc = this.simulation.arc;
    const previousBreaks = this.simulation.threadBreaks;
    const previousMissedAnchors = this.simulation.missedAnchors;
    const previousIrisCycle = this.simulation.iris.cycle;
    const previousIrisResolved = this.simulation.iris.resolved;
    const previousStitchSequence = this.simulation.stitchEventSequence;
    const previousResonanceActivations = this.simulation.resonanceActivations;

    const input = this.currentInput();
    stepLoomSimulation(this.simulation, input, deltaSeconds);
    if (this.simulation.tick > previousTick) {
      this.pendingPhaseToggle = false;
      this.pendingResonanceActivation = false;
      const physicsSteps = Math.min(this.simulation.tick - previousTick, 15);
      for (let index = 0; index < physicsSteps; index += 1) {
        this.physics?.fixedStep(this.simulation);
      }
    }

    this.emitSimulationEvents({
      previousPhase,
      previousArc,
      previousBreaks,
      previousMissedAnchors,
      previousIrisCycle,
      previousIrisResolved,
      previousStitchSequence,
      previousResonanceActivations,
    });
    if (this.physics && this.scene) {
      const poses: Parameters<SignalLoomScene['syncDebris']>[0] extends Iterable<infer T>
        ? T[]
        : never[] = [];
      this.physics.forEachActiveDebrisPose((pose) => poses.push(pose));
      this.scene.syncDebris(poses);
    }
    this.scene?.render(this.simulation, deltaSeconds, previousArc !== this.simulation.arc);

    this.snapshotElapsed += deltaSeconds;
    if (this.snapshotElapsed >= SNAPSHOT_INTERVAL_SECONDS) {
      this.snapshotElapsed = 0;
      this.options.onSnapshot(snapshotOfLoom(this.simulation));
    }
    this.audioElapsed += deltaSeconds;
    if (this.audioElapsed >= SNAPSHOT_INTERVAL_SECONDS) {
      this.audioElapsed = 0;
      this.audio.setLoomState(
        this.simulation.forwardSpeed,
        this.simulation.thread.tension,
        this.reelHeld,
        this.simulation.resonanceRemaining > 0,
      );
    }

    if (this.simulation.status === 'extracted') {
      this.running = false;
      this.lastFrameTime = 0;
      this.setSurfaceInteractive(false);
      this.audio.setRunning(false);
      this.audio.extraction();
      this.physics?.pause();
      this.scene?.pause();
      const snapshot = snapshotOfLoom(this.simulation);
      this.options.onSnapshot(snapshot);
      this.options.onExtract(snapshot);
      return;
    }
    this.scheduleFrame();
  };

  private currentInput(): LoomInput {
    const direction = this.inputVector();
    return {
      ...direction,
      reel: this.reelHeld,
      phaseToggle: this.pendingPhaseToggle,
      activateResonance: this.pendingResonanceActivation,
    };
  }

  private emitSimulationEvents(previous: {
    previousPhase: LoomPhase;
    previousArc: LoomSimulation['arc'];
    previousBreaks: number;
    previousMissedAnchors: number;
    previousIrisCycle: number;
    previousIrisResolved: boolean;
    previousStitchSequence: number;
    previousResonanceActivations: number;
  }) {
    const irisResolvedNow =
      this.simulation.iris.resolved &&
      this.simulation.iris.outcome !== null &&
      (
        this.simulation.iris.cycle !== previous.previousIrisCycle ||
        !previous.previousIrisResolved
      );
    const irisHitNow =
      irisResolvedNow && this.simulation.iris.outcome === 'hit';
    if (this.simulation.phase !== previous.previousPhase) {
      this.audio.phase(this.simulation.phase);
      this.options.onPhase(this.simulation.phase);
    }
    if (this.simulation.arc !== previous.previousArc) {
      this.audio.loomArc(this.simulation.arc);
      this.options.onArc(this.simulation.arc);
    }
    if (this.simulation.threadBreaks > previous.previousBreaks) {
      const anchor = this.closestResolvedAnchor(true);
      const position = anchor
        ? { x: anchor.x, y: anchor.y, z: anchor.z }
        : { x: this.simulation.needle.position.x, y: this.simulation.needle.position.y, z: 0 };
      this.physics?.emitThreadBreak(position, { x: 0, y: 0, z: 1 }, 1);
      // An Iris blade is still a real recorded Thread break, but it owns one
      // strong, specific feedback beat. Stacking the generic break channel in
      // the same tick sounds and feels like two collisions.
      if (!irisHitNow) {
        this.audio.threadBreak();
        this.options.onThreadBreak(snapshotOfLoom(this.simulation));
      }
    }
    if (
      this.simulation.missedAnchors > previous.previousMissedAnchors &&
      !irisHitNow
    ) {
      const opening =
        previous.previousMissedAnchors === 0 &&
        this.simulation.stitches === 0 &&
        this.simulation.elapsed < 30;
      this.audio.anchorMiss(opening);
      this.options.onAnchorMiss(snapshotOfLoom(this.simulation), opening);
    }
    if (irisResolvedNow) {
      const current = snapshotOfLoom(this.simulation);
      const position = {
        x: this.simulation.iris.gapCenter.x,
        y: this.simulation.iris.gapCenter.y,
        z: this.simulation.iris.z,
      };
      if (this.simulation.iris.outcome === 'clear') {
        this.physics?.emitStitch(position, { x: 0, y: 1, z: 0.2 }, 1.5);
        this.audio.irisClear();
        this.options.onIrisClear(current);
      } else {
        this.audio.irisHit();
        this.options.onIrisHit(current);
      }
    }
    if (
      this.simulation.stitchEventSequence > previous.previousStitchSequence &&
      this.simulation.lastStitchEvent
    ) {
      const event = this.simulation.lastStitchEvent;
      const anchor = this.simulation.anchors.find(
        (candidate) => candidate.id === event.anchorId,
      );
      const position = anchor
        ? { x: anchor.x, y: anchor.y, z: anchor.z }
        : { x: this.simulation.echo.position.x, y: this.simulation.echo.position.y, z: 0 };
      const tangent = {
        x: this.simulation.echo.position.x - this.simulation.needle.position.x,
        y: this.simulation.echo.position.y - this.simulation.needle.position.y,
        z: 0.25,
      };
      this.physics?.emitStitch(position, tangent, event.expressive ? 1.2 : 0.8);
      this.audio.stitch(event);
      this.options.onStitch(event);
    }
    if (
      this.simulation.resonanceActivations > previous.previousResonanceActivations
    ) {
      const position = {
        x: this.simulation.needle.position.x,
        y: this.simulation.needle.position.y,
        z: 0,
      };
      this.physics?.emitResonance(position);
      this.audio.resonance();
      this.options.onResonance();
    }
  }

  private closestResolvedAnchor(hit: boolean) {
    let selected: LoomSimulation['anchors'][number] | null = null;
    for (const anchor of this.simulation.anchors) {
      if (!anchor.active || anchor.hit !== hit || Math.abs(anchor.z) > 3) continue;
      if (!selected || Math.abs(anchor.z) < Math.abs(selected.z)) selected = anchor;
    }
    return selected;
  }

  async unlockAudio() {
    try {
      return await this.audio.unlock();
    } catch {
      this.audio.setMuted(true);
      return false;
    }
  }

  prepareRun(seed: LoomSeed) {
    if (this.disposed || !this.ready) return;
    this.stopLoop();
    this.simulation = createLoomSimulation(seed);
    this.inputPrimed = false;
    this.releaseInput();
    this.snapshotElapsed = 0;
    this.audioElapsed = 0;
    this.physics?.reset(this.simulation);
    this.scene?.resonance(false);
    this.scene?.resume();
    this.scene?.render(this.simulation, 0, true);
    this.scene?.pause();
    this.options.onSnapshot(snapshotOfLoom(this.simulation));
  }

  start() {
    if (this.disposed || !this.ready || this.simulation.status === 'extracted') return;
    const stagedPhase = this.inputPrimed && this.pendingPhaseToggle;
    if (stagedPhase) {
      this.simulation.phase = this.simulation.phase === 'ember' ? 'cobalt' : 'ember';
      // The visible countdown is longer than the ordinary phase cooldown. A
      // staged phase must therefore be true before the first moving/collision
      // tick, even when the run was paused mid-cooldown.
      this.simulation.phaseCooldown = 0.18;
      this.pendingPhaseToggle = false;
      this.audio.phase(this.simulation.phase);
      this.options.onPhase(this.simulation.phase);
      this.options.onSnapshot(snapshotOfLoom(this.simulation));
    }
    this.running = true;
    this.inputPrimed = false;
    this.primedSignature = '';
    this.options.onPrimedInput(EMPTY_PRIMED_INPUT);
    this.lastFrameTime = 0;
    this.physics?.resume(this.simulation);
    this.scene?.resume();
    this.setSurfaceInteractive(true);
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
    this.setSurfaceInteractive(false);
    this.audio.setRunning(false);
    this.scene?.render(this.simulation, 0, true);
    this.scene?.pause();
    this.options.onSnapshot(snapshotOfLoom(this.simulation));
  }

  getSnapshot() {
    return snapshotOfLoom(this.simulation);
  }

  finishRun() {
    this.pause();
    const snapshot = this.getSnapshot();
    this.options.onSnapshot(snapshot);
    return snapshot;
  }

  primeInput() {
    if (this.disposed || this.running || this.simulation.status === 'extracted') return;
    this.inputPrimed = true;
    this.primedSignature = '__initial__';
    this.setSurfaceInteractive(true);
    this.canvas?.focus({ preventScroll: true });
    this.emitPrimedInput();
  }

  togglePhase() {
    if (!this.canAcceptInput()) return;
    this.pendingPhaseToggle = !this.pendingPhaseToggle;
    this.emitPrimedInput();
  }

  activateResonance() {
    if (!this.canAcceptInput()) return;
    if (
      (
        this.simulation.resonanceCharge < LOOM_RESONANCE_CHARGE_REQUIRED ||
        this.simulation.resonanceRemaining > 0 ||
        this.simulation.resonanceCooldownRemaining > 0
      )
    ) return;
    this.pendingResonanceActivation = !this.pendingResonanceActivation;
    this.emitPrimedInput();
  }

  setReel(pressed: boolean) {
    if (!this.canAcceptInput()) return;
    this.reelHeld = pressed;
    this.emitPrimedInput();
  }

  setKey(code: string, pressed: boolean) {
    if (!this.canAcceptInput()) return;
    if (pressed) this.keys.add(code);
    else this.keys.delete(code);
    this.emitPrimedInput();
  }

  setVirtualDirection(x: number, y: number) {
    if (!this.canAcceptInput()) return;
    this.virtualInput = {
      x: clamp(Number.isFinite(x) ? x : 0, -1, 1),
      y: clamp(Number.isFinite(y) ? y : 0, -1, 1),
    };
    this.emitPrimedInput();
  }

  releaseInput() {
    this.keys.clear();
    this.virtualInput = { x: 0, y: 0 };
    this.reelHeld = false;
    this.pendingPhaseToggle = false;
    this.pendingResonanceActivation = false;
    if (this.pointer && this.canvas) {
      try {
        this.canvas.releasePointerCapture(this.pointer.id);
      } catch {
        // Capture may already be gone after blur or visibility change.
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

  getDiagnostics() {
    return {
      ready: this.ready,
      running: this.running,
      disposed: this.disposed,
      render: this.scene?.getDiagnostics() ?? null,
      physics: this.physics?.getDiagnostics() ?? null,
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
  LoomGameSnapshot,
  LoomPrimedInputFeedback,
  LoomRunMode,
} from './loom-game-types';
export type { LoomStitchEvent } from './loom-simulation';
