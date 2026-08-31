/**
 * Deterministic greybox rules for the Signal Loom prototype.
 *
 * This module deliberately owns no renderer, audio, browser, Babylon, or Rapier
 * state. The Needle/Echo/Thread rules remain authoritative at a fixed 60 Hz;
 * presentation layers can mirror the bodies and react to the emitted events.
 * `stepLoomSimulation` mutates and returns the supplied simulation so high-refresh
 * zero-step calls do not clone the bounded anchor pool.
 */

export type LoomSeed = number | string;
export type LoomPhase = "ember" | "cobalt";
export type LoomStatus = "running" | "extracted";
export type LoomArc = 1 | 2 | 3 | 4;
export type LoomAnchorRoute = "safe" | "expressive";
export type LoomIrisStage =
  | "dormant"
  | "telegraph"
  | "approach"
  | "close"
  | "contact"
  | "recovery";
export type LoomIrisOutcome = "clear" | "hit" | null;
export type LoomEncounterKind =
  | "opening-thread"
  | "quiet-splice"
  | "wide-exposure"
  | "phase-lattice"
  | "counterturn"
  | "iris-approach"
  | "extraction-mark";

export interface LoomVector2 {
  x: number;
  y: number;
}

export interface LoomBody {
  position: LoomVector2;
  velocity: LoomVector2;
}

export interface LoomInput {
  /** Continuous steering intent, normalized to a unit circle. */
  x: number;
  y: number;
  /** Continuous hold. Reel shortens the Thread and increases its damping. */
  reel: boolean;
  /** One-shot intent. UI adapters should edge-detect held buttons. */
  phaseToggle: boolean;
  /** One-shot intent. Activation never refreshes an active Resonance window. */
  activateResonance: boolean;
}

export interface LoomThreadState {
  length: number;
  restLength: number;
  targetLength: number;
  tension: number;
  peakTension: number;
}

/**
 * Compact authoritative state for the Arc III/IV Iris set-piece. Render and
 * physics layers consume this as readonly data; only the fixed-step simulation
 * advances or resolves it.
 */
export interface LoomIrisState {
  readonly active: boolean;
  readonly cycle: number;
  readonly stage: LoomIrisStage;
  readonly z: number;
  readonly gapCenter: Readonly<LoomVector2>;
  readonly gapRadius: number;
  readonly intensity: number;
  readonly resolved: boolean;
  readonly outcome: LoomIrisOutcome;
  readonly chargeAwarded: boolean;
}

type MutableLoomIrisState = {
  -readonly [Key in keyof LoomIrisState]: LoomIrisState[Key];
} & { gapCenter: LoomVector2 };

export interface LoomAnchor {
  poolSlot: number;
  active: boolean;
  id: string;
  chunkId: string;
  encounterKind: LoomEncounterKind;
  beat: number;
  route: LoomAnchorRoute;
  phase: LoomPhase;
  x: number;
  y: number;
  z: number;
  latched: boolean;
  armed: boolean;
  resolved: boolean;
  hit: boolean;
  closestEndpointDistance: number;
}

export interface LoomStitchEvent {
  sequence: number;
  anchorId: string;
  chunkId: string;
  encounterKind: LoomEncounterKind;
  route: LoomAnchorRoute;
  phase: LoomPhase;
  scoreAwarded: number;
  chain: number;
  expressive: boolean;
  nearMiss: boolean;
  tension: number;
  resonanceActive: boolean;
}

export interface LoomExtractionResult {
  outcome: "extracted";
  finalScore: number;
  exactScore: number;
  durationSeconds: number;
  distance: number;
  stitches: number;
  safeStitches: number;
  expressiveStitches: number;
  missedAnchors: number;
  nearMisses: number;
  threadBreaks: number;
  bestStitchChain: number;
  resonanceActivations: number;
  resonanceActiveSeconds: number;
  peakThreadTension: number;
  authoredChunksSeen: number;
}

export interface LoomSimulation {
  seed: number;
  rngState: number;
  status: LoomStatus;
  tick: number;
  elapsed: number;
  accumulator: number;
  distance: number;
  forwardSpeed: number;
  arc: LoomArc;
  score: number;
  phase: LoomPhase;
  phaseCooldown: number;
  previousReelInput: boolean;
  hasPlayerAuthorship: boolean;
  pendingPhaseToggle: boolean;
  pendingResonanceActivation: boolean;
  currentInput: LoomInput;
  needle: LoomBody;
  echo: LoomBody;
  thread: LoomThreadState;
  iris: LoomIrisState;
  anchors: LoomAnchor[];
  nextAnchorId: number;
  nextChunkId: number;
  nextSpawnZ: number;
  lastEncounterKind: LoomEncounterKind | null;
  chunkBag: LoomEncounterKind[];
  chunkBagArc: LoomArc | null;
  authoredChunksSeen: number;
  stitchEventSequence: number;
  lastStitchEvent: LoomStitchEvent | null;
  stitches: number;
  safeStitches: number;
  expressiveStitches: number;
  missedAnchors: number;
  nearMisses: number;
  threadBreaks: number;
  stitchChain: number;
  bestStitchChain: number;
  resonanceCharge: number;
  resonanceRemaining: number;
  resonanceCooldownRemaining: number;
  resonanceActivations: number;
  resonanceActiveSeconds: number;
  result: LoomExtractionResult | null;
}

type AuthoredPhase = LoomPhase | "alternate";

export interface LoomAnchorBlueprint {
  zOffset: number;
  x: number;
  y: number;
  phase: AuthoredPhase;
  route: LoomAnchorRoute;
}

export interface LoomEncounterChunk {
  kind: LoomEncounterKind;
  minimumArc: LoomArc;
  maximumArc: LoomArc;
  anchors: readonly LoomAnchorBlueprint[];
}

export const LOOM_FIXED_STEP_SECONDS = 1 / 60;
export const LOOM_CONTRACT_SECONDS = 6 * 60;
export const LOOM_RESONANCE_DURATION_SECONDS = 6;
export const LOOM_RESONANCE_RECOVERY_SECONDS = 12;
export const LOOM_RESONANCE_CHARGE_REQUIRED = 3;
export const LOOM_RESONANCE_SCORE_MULTIPLIER = 2;
export const LOOM_ANCHOR_POOL_SIZE = 24;
export const LOOM_FLIGHT_BOUNDARY = 7.2;
export const LOOM_REELED_LENGTH = 2.2;
export const LOOM_EXTENDED_LENGTH = 4.8;
export const LOOM_MAX_THREAD_LENGTH = 7.1;
export const LOOM_IRIS_START_SECONDS = 210;
export const LOOM_IRIS_CYCLE_SECONDS = 18;
export const LOOM_IRIS_TELEGRAPH_SECONDS = 3;
export const LOOM_IRIS_APPROACH_SECONDS = 4;
export const LOOM_IRIS_CLOSE_SECONDS = 2;
export const LOOM_IRIS_CONTACT_SECONDS = 0.5;
export const LOOM_IRIS_RECOVERY_SECONDS =
  LOOM_IRIS_CYCLE_SECONDS -
  LOOM_IRIS_TELEGRAPH_SECONDS -
  LOOM_IRIS_APPROACH_SECONDS -
  LOOM_IRIS_CLOSE_SECONDS -
  LOOM_IRIS_CONTACT_SECONDS;
export const LOOM_IRIS_CONTACT_OFFSET_SECONDS =
  LOOM_IRIS_TELEGRAPH_SECONDS +
  LOOM_IRIS_APPROACH_SECONDS +
  LOOM_IRIS_CLOSE_SECONDS;
export const LOOM_IRIS_MAX_CYCLES = Math.floor(
  (LOOM_CONTRACT_SECONDS -
    LOOM_IRIS_START_SECONDS -
    LOOM_IRIS_CONTACT_OFFSET_SECONDS) /
    LOOM_IRIS_CYCLE_SECONDS,
) + 1;
export const LOOM_IRIS_END_SECONDS =
  LOOM_IRIS_START_SECONDS + LOOM_IRIS_MAX_CYCLES * LOOM_IRIS_CYCLE_SECONDS;
export const LOOM_IRIS_CLEAR_SCORE = 1_200;
export const LOOM_IRIS_HIT_SCORE_PENALTY = 160;
export const LOOM_IRIS_NEEDLE_RADIUS = 0.28;
export const LOOM_IRIS_ECHO_RADIUS = 0.24;
export const LOOM_IRIS_THREAD_RADIUS = 0.16;
export const LOOM_IRIS_BLADE_COUNT = 12;
export const LOOM_IRIS_ARC_THREE_GAP_RADIUS = 3.35;
export const LOOM_IRIS_ARC_FOUR_GAP_RADIUS = 3;
export const LOOM_IRIS_GAP_CENTER_MIN_RADIUS = 3.2;
export const LOOM_IRIS_GAP_CENTER_RADIUS_RANGE = 1;
export const LOOM_IRIS_TELEGRAPH_Z = -110;
export const LOOM_IRIS_CLOSE_Z = -24;
export const LOOM_IRIS_CONTACT_Z = 0;
export const LOOM_IRIS_RECOVERY_Z = 34;

/** Authoritative wall-clock time until the current Iris reaches contact. */
export function loomIrisSecondsToContact(
  elapsedSeconds: number,
): number | null {
  const elapsed = Number.isFinite(elapsedSeconds)
    ? Math.max(0, elapsedSeconds)
    : 0;
  if (elapsed < LOOM_IRIS_START_SECONDS || elapsed >= LOOM_IRIS_END_SECONDS) {
    return null;
  }
  const cycle = Math.floor(
    (elapsed - LOOM_IRIS_START_SECONDS) / LOOM_IRIS_CYCLE_SECONDS,
  );
  const contactAt =
    LOOM_IRIS_START_SECONDS +
    cycle * LOOM_IRIS_CYCLE_SECONDS +
    LOOM_IRIS_CONTACT_OFFSET_SECONDS;
  const recoveryStartsAt = contactAt + LOOM_IRIS_CONTACT_SECONDS;
  if (elapsed >= recoveryStartsAt) return null;
  return Math.max(0, contactAt - elapsed);
}

const MAX_FRAME_DELTA_SECONDS = 0.25;
const PHASE_TOGGLE_COOLDOWN_SECONDS = 0.18;
const NEEDLE_ACCELERATION = 28;
const NEEDLE_DRAG = 5.2;
const NEEDLE_MAX_SPEED = 7.8;
const ECHO_MAX_SPEED = 14;
const REEL_RATE = 5.8;
const ANCHOR_LATCH_RADIUS = 0.42;
const ANCHOR_BODY_COLLISION_RADIUS = 0.34;
const ANCHOR_NEAR_MISS_RADIUS = 0.92;
const ANCHOR_INTERACTION_HALF_DEPTH = 0.9;
const ANCHOR_PASS_Z = 1.55;
const ANCHOR_DESPAWN_Z = 8;
const ACTIVE_ANCHOR_TARGET = 18;
const INITIAL_SPAWN_Z = -18;
const CHUNK_GAP = 18;
const RNG_FALLBACK_SEED = 0x7f4a7c15;
const EPSILON = 1e-10;

export const LOOM_AUTHORED_CHUNKS: readonly LoomEncounterChunk[] = [
  {
    kind: "opening-thread",
    minimumArc: 1,
    maximumArc: 1,
    anchors: [
      { zOffset: 0, x: -1.4, y: 0, phase: "ember", route: "safe" },
      { zOffset: -14, x: -1.15, y: 0.45, phase: "ember", route: "safe" },
    ],
  },
  {
    kind: "quiet-splice",
    minimumArc: 1,
    maximumArc: 2,
    anchors: [
      { zOffset: 0, x: -1.1, y: -0.5, phase: "alternate", route: "safe" },
      { zOffset: -13, x: -1.35, y: 0.55, phase: "alternate", route: "safe" },
    ],
  },
  {
    kind: "wide-exposure",
    minimumArc: 1,
    maximumArc: 4,
    anchors: [
      { zOffset: 0, x: -1.05, y: 0, phase: "alternate", route: "safe" },
      { zOffset: -11, x: -3.55, y: 0.7, phase: "alternate", route: "expressive" },
      { zOffset: -22, x: -1.2, y: -0.45, phase: "alternate", route: "safe" },
    ],
  },
  {
    kind: "phase-lattice",
    minimumArc: 2,
    maximumArc: 4,
    anchors: [
      { zOffset: 0, x: -1.3, y: -0.8, phase: "ember", route: "safe" },
      { zOffset: -10, x: -3.35, y: 0.2, phase: "cobalt", route: "expressive" },
      { zOffset: -20, x: -1.15, y: 0.8, phase: "ember", route: "safe" },
    ],
  },
  {
    kind: "counterturn",
    minimumArc: 2,
    maximumArc: 4,
    anchors: [
      { zOffset: 0, x: -3.45, y: -1.05, phase: "alternate", route: "expressive" },
      { zOffset: -11, x: -1.1, y: 0.15, phase: "alternate", route: "safe" },
      { zOffset: -22, x: -3.6, y: 1.05, phase: "alternate", route: "expressive" },
    ],
  },
  {
    kind: "iris-approach",
    minimumArc: 3,
    maximumArc: 4,
    anchors: [
      { zOffset: 0, x: -1, y: -1.15, phase: "ember", route: "safe" },
      { zOffset: -9, x: -3.7, y: -0.3, phase: "cobalt", route: "expressive" },
      { zOffset: -18, x: -3.45, y: 0.85, phase: "ember", route: "expressive" },
      { zOffset: -27, x: -1.2, y: 1.15, phase: "cobalt", route: "safe" },
    ],
  },
  {
    kind: "extraction-mark",
    minimumArc: 4,
    maximumArc: 4,
    anchors: [
      { zOffset: 0, x: -1.2, y: -0.65, phase: "alternate", route: "safe" },
      { zOffset: -9, x: -3.65, y: 0, phase: "alternate", route: "expressive" },
      { zOffset: -18, x: -1.2, y: 0.65, phase: "alternate", route: "safe" },
    ],
  },
] as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function smootherStep(progress: number): number {
  const value = clamp(progress, 0, 1);
  return value ** 3 * (value * (value * 6 - 15) + 10);
}

function oppositePhase(phase: LoomPhase): LoomPhase {
  return phase === "ember" ? "cobalt" : "ember";
}

function normalizedSeed(seed: LoomSeed): number {
  if (typeof seed === "number") {
    const value = Number.isFinite(seed) ? Math.trunc(seed) >>> 0 : RNG_FALLBACK_SEED;
    return value || RNG_FALLBACK_SEED;
  }

  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) || RNG_FALLBACK_SEED;
}

function nextRandom(simulation: LoomSimulation): number {
  let state = simulation.rngState >>> 0;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  simulation.rngState = state >>> 0 || RNG_FALLBACK_SEED;
  return simulation.rngState / 0x100000000;
}

export function loomArcForElapsed(elapsedSeconds: number): LoomArc {
  const elapsed = Number.isFinite(elapsedSeconds) ? Math.max(0, elapsedSeconds) : 0;
  if (elapsed < 90) return 1;
  if (elapsed < 210) return 2;
  if (elapsed < 330) return 3;
  return 4;
}

export function loomForwardSpeedForElapsed(elapsedSeconds: number): number {
  const elapsed = Number.isFinite(elapsedSeconds) ? Math.max(0, elapsedSeconds) : 0;
  const keyframes = [
    { elapsed: 0, speed: 8.5 },
    { elapsed: 45, speed: 10.5 },
    { elapsed: 120, speed: 14 },
    { elapsed: 240, speed: 18.5 },
    { elapsed: 330, speed: 22 },
    { elapsed: LOOM_CONTRACT_SECONDS, speed: 16 },
  ] as const;

  for (let index = 1; index < keyframes.length; index += 1) {
    const previous = keyframes[index - 1];
    const next = keyframes[index];
    if (elapsed <= next.elapsed) {
      const progress = (elapsed - previous.elapsed) / (next.elapsed - previous.elapsed);
      return previous.speed + (next.speed - previous.speed) * smootherStep(progress);
    }
  }
  return keyframes[keyframes.length - 1].speed;
}

function irisCycleRandom(seed: number, cycle: number, salt: number): number {
  let state = (seed ^ Math.imul(cycle + 1, 0x9e3779b1) ^ salt) >>> 0;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  return (state >>> 0) / 0x100000000;
}

function irisGapCenterForCycle(seed: number, cycle: number): LoomVector2 {
  const angle = irisCycleRandom(seed, cycle, 0xa341316c) * Math.PI * 2;
  const radius = LOOM_IRIS_GAP_CENTER_MIN_RADIUS +
    irisCycleRandom(seed, cycle, 0xc8013ea4) *
      LOOM_IRIS_GAP_CENTER_RADIUS_RANGE;
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  };
}

function lerp(start: number, end: number, progress: number): number {
  return start + (end - start) * clamp(progress, 0, 1);
}

/**
 * Pure deterministic Iris schedule. It does not consume the encounter RNG, so
 * adding presentation consumers cannot alter authored anchor order.
 */
export function loomIrisStateForElapsed(
  seed: number,
  elapsedSeconds: number,
): LoomIrisState {
  const elapsed = Number.isFinite(elapsedSeconds)
    ? Math.max(0, elapsedSeconds)
    : 0;
  if (elapsed < LOOM_IRIS_START_SECONDS || elapsed >= LOOM_IRIS_END_SECONDS) {
    return {
      active: false,
      cycle: 0,
      stage: "dormant",
      z: LOOM_IRIS_TELEGRAPH_Z,
      gapCenter: { x: 0, y: 0 },
      gapRadius: LOOM_IRIS_ARC_THREE_GAP_RADIUS,
      intensity: 0,
      resolved: false,
      outcome: null,
      chargeAwarded: false,
    };
  }

  const irisElapsed = elapsed - LOOM_IRIS_START_SECONDS;
  const cycle = Math.floor(irisElapsed / LOOM_IRIS_CYCLE_SECONDS) + 1;
  const cycleElapsed = irisElapsed % LOOM_IRIS_CYCLE_SECONDS;
  const gapCenter = irisGapCenterForCycle(seed >>> 0, cycle);
  const gapRadius = loomArcForElapsed(elapsed) >= 4
    ? LOOM_IRIS_ARC_FOUR_GAP_RADIUS
    : LOOM_IRIS_ARC_THREE_GAP_RADIUS;

  let stage: LoomIrisStage;
  let z: number;
  let intensity: number;
  if (cycleElapsed < LOOM_IRIS_TELEGRAPH_SECONDS) {
    const progress = cycleElapsed / LOOM_IRIS_TELEGRAPH_SECONDS;
    stage = "telegraph";
    z = LOOM_IRIS_TELEGRAPH_Z;
    intensity = lerp(0.25, 0.7, smootherStep(progress));
  } else if (
    cycleElapsed <
    LOOM_IRIS_TELEGRAPH_SECONDS + LOOM_IRIS_APPROACH_SECONDS
  ) {
    const progress =
      (cycleElapsed - LOOM_IRIS_TELEGRAPH_SECONDS) /
      LOOM_IRIS_APPROACH_SECONDS;
    stage = "approach";
    z = lerp(LOOM_IRIS_TELEGRAPH_Z, LOOM_IRIS_CLOSE_Z, smootherStep(progress));
    intensity = lerp(0.7, 0.88, progress);
  } else if (
    cycleElapsed <
    LOOM_IRIS_TELEGRAPH_SECONDS +
      LOOM_IRIS_APPROACH_SECONDS +
      LOOM_IRIS_CLOSE_SECONDS
  ) {
    const progress =
      (cycleElapsed -
        LOOM_IRIS_TELEGRAPH_SECONDS -
        LOOM_IRIS_APPROACH_SECONDS) /
      LOOM_IRIS_CLOSE_SECONDS;
    stage = "close";
    z = lerp(LOOM_IRIS_CLOSE_Z, LOOM_IRIS_CONTACT_Z, smootherStep(progress));
    intensity = lerp(0.88, 1, progress);
  } else if (
    cycleElapsed <
    LOOM_IRIS_TELEGRAPH_SECONDS +
      LOOM_IRIS_APPROACH_SECONDS +
      LOOM_IRIS_CLOSE_SECONDS +
      LOOM_IRIS_CONTACT_SECONDS
  ) {
    stage = "contact";
    z = LOOM_IRIS_CONTACT_Z;
    intensity = 1;
  } else {
    const progress =
      (cycleElapsed -
        LOOM_IRIS_TELEGRAPH_SECONDS -
        LOOM_IRIS_APPROACH_SECONDS -
        LOOM_IRIS_CLOSE_SECONDS -
        LOOM_IRIS_CONTACT_SECONDS) /
      LOOM_IRIS_RECOVERY_SECONDS;
    stage = "recovery";
    z = lerp(LOOM_IRIS_CONTACT_Z, LOOM_IRIS_RECOVERY_Z, smootherStep(progress));
    intensity = 1 - smootherStep(progress);
  }

  return {
    active: true,
    cycle,
    stage,
    z,
    gapCenter,
    gapRadius,
    intensity: clamp(intensity, 0, 1),
    resolved: false,
    outcome: null,
    chargeAwarded: false,
  };
}

export interface LoomIrisClearance {
  needle: number;
  echo: number;
  thread: number;
  minimum: number;
}

/**
 * Signed clearance from every authoritative actor to the circular safe gap.
 * The Thread is a straight capsule in the rules simulation. Because a circle
 * is convex, its farthest segment point is one of the two endpoints.
 */
export function loomIrisClearance(
  simulation: Pick<LoomSimulation, "needle" | "echo" | "iris">,
): LoomIrisClearance {
  const { gapCenter, gapRadius } = simulation.iris;
  const needleDistance = Math.hypot(
    simulation.needle.position.x - gapCenter.x,
    simulation.needle.position.y - gapCenter.y,
  );
  const echoDistance = Math.hypot(
    simulation.echo.position.x - gapCenter.x,
    simulation.echo.position.y - gapCenter.y,
  );
  const needle = gapRadius - LOOM_IRIS_NEEDLE_RADIUS - needleDistance;
  const echo = gapRadius - LOOM_IRIS_ECHO_RADIUS - echoDistance;
  const thread =
    gapRadius - LOOM_IRIS_THREAD_RADIUS - Math.max(needleDistance, echoDistance);
  return {
    needle,
    echo,
    thread,
    minimum: Math.min(needle, echo, thread),
  };
}

function emptyAnchor(poolSlot: number): LoomAnchor {
  return {
    poolSlot,
    active: false,
    id: "",
    chunkId: "",
    encounterKind: "opening-thread",
    beat: 0,
    route: "safe",
    phase: "ember",
    x: 0,
    y: 0,
    z: 0,
    latched: false,
    armed: false,
    resolved: false,
    hit: false,
    closestEndpointDistance: Number.POSITIVE_INFINITY,
  };
}

function freeAnchorCount(simulation: LoomSimulation): number {
  let free = 0;
  for (const anchor of simulation.anchors) {
    if (!anchor.active) free += 1;
  }
  return free;
}

function activeAnchorCount(simulation: LoomSimulation): number {
  return LOOM_ANCHOR_POOL_SIZE - freeAnchorCount(simulation);
}

function chooseChunk(simulation: LoomSimulation, arc: LoomArc): LoomEncounterChunk {
  if (simulation.nextChunkId === 1) return LOOM_AUTHORED_CHUNKS[0];

  if (simulation.chunkBagArc !== arc || simulation.chunkBag.length === 0) {
    const nextBag = LOOM_AUTHORED_CHUNKS
      .slice(1)
      .filter((chunk) => arc >= chunk.minimumArc && arc <= chunk.maximumArc)
      .map((chunk) => chunk.kind);

    // A seeded shuffle bag keeps the encounter order fresh while guaranteeing
    // equal opportunity coverage. Personal records should measure execution,
    // not whether a lucky seed rolled more high-value patterns.
    for (let index = nextBag.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(nextRandom(simulation) * (index + 1));
      [nextBag[index], nextBag[swapIndex]] = [nextBag[swapIndex], nextBag[index]];
    }
    if (
      nextBag.length > 1 &&
      nextBag[0] === simulation.lastEncounterKind
    ) {
      const swapIndex = nextBag.findIndex(
        (kind) => kind !== simulation.lastEncounterKind,
      );
      [nextBag[0], nextBag[swapIndex]] = [nextBag[swapIndex], nextBag[0]];
    }
    simulation.chunkBag = nextBag;
    simulation.chunkBagArc = arc;
  }

  const selectedKind = simulation.chunkBag.shift() ?? "quiet-splice";
  return LOOM_AUTHORED_CHUNKS.find((chunk) => chunk.kind === selectedKind) ??
    LOOM_AUTHORED_CHUNKS[1];
}

function resolvedBlueprintPhase(
  blueprint: LoomAnchorBlueprint,
  beat: number,
  phaseFlipped: boolean,
): LoomPhase {
  let phase: LoomPhase;
  if (blueprint.phase === "alternate") {
    phase = beat % 2 === 1 ? "ember" : "cobalt";
  } else {
    phase = blueprint.phase;
  }
  return phaseFlipped ? oppositePhase(phase) : phase;
}

function spawnChunk(simulation: LoomSimulation): boolean {
  const projectedSeconds = Math.max(
    0,
    -simulation.nextSpawnZ / Math.max(simulation.forwardSpeed, 1),
  );
  const projectedArc = loomArcForElapsed(simulation.elapsed + projectedSeconds);
  const chunk = chooseChunk(simulation, projectedArc);
  if (freeAnchorCount(simulation) < chunk.anchors.length) return false;

  const chunkNumber = simulation.nextChunkId;
  const chunkId = `loom-chunk-${chunkNumber}`;
  const verticalMirror = chunk.kind === "opening-thread" || nextRandom(simulation) < 0.5 ? 1 : -1;
  const phaseFlipped = chunk.kind !== "opening-thread" && nextRandom(simulation) < 0.5;
  const quarterTurns = chunk.kind === "opening-thread"
    ? 0
    : Math.floor(nextRandom(simulation) * 4);
  let beat = 0;
  let minimumZ = simulation.nextSpawnZ;

  for (const blueprint of chunk.anchors) {
    const anchor = simulation.anchors.find((candidate) => !candidate.active);
    if (!anchor) return false;
    beat += 1;
    const z = simulation.nextSpawnZ + blueprint.zOffset;
    minimumZ = Math.min(minimumZ, z);
    anchor.active = true;
    anchor.id = `loom-anchor-${simulation.nextAnchorId}`;
    anchor.chunkId = chunkId;
    anchor.encounterKind = chunk.kind;
    anchor.beat = beat;
    anchor.route = blueprint.route;
    anchor.phase = resolvedBlueprintPhase(blueprint, beat, phaseFlipped);
    const sourceX = blueprint.x;
    const sourceY = blueprint.y * verticalMirror;
    if (quarterTurns === 1) {
      anchor.x = -sourceY;
      anchor.y = sourceX;
    } else if (quarterTurns === 2) {
      anchor.x = -sourceX;
      anchor.y = -sourceY;
    } else if (quarterTurns === 3) {
      anchor.x = sourceY;
      anchor.y = -sourceX;
    } else {
      anchor.x = sourceX;
      anchor.y = sourceY;
    }
    anchor.z = z;
    anchor.latched = false;
    anchor.armed = false;
    anchor.resolved = false;
    anchor.hit = false;
    anchor.closestEndpointDistance = Number.POSITIVE_INFINITY;
    simulation.nextAnchorId += 1;
  }

  simulation.nextChunkId += 1;
  simulation.nextSpawnZ = minimumZ - CHUNK_GAP;
  simulation.lastEncounterKind = chunk.kind;
  simulation.authoredChunksSeen += 1;
  return true;
}

function fillAnchorPool(simulation: LoomSimulation): void {
  while (activeAnchorCount(simulation) < ACTIVE_ANCHOR_TARGET) {
    if (!spawnChunk(simulation)) break;
  }
}

function normalizeSteering(input: LoomInput): { x: number; y: number } {
  let x = Number.isFinite(input.x) ? clamp(input.x, -1, 1) : 0;
  let y = Number.isFinite(input.y) ? clamp(input.y, -1, 1) : 0;
  const length = Math.hypot(x, y);
  if (length > 1) {
    x /= length;
    y /= length;
  }
  return { x, y };
}

function clampBodyToFlightPlane(body: LoomBody): void {
  const distance = Math.hypot(body.position.x, body.position.y);
  if (distance <= LOOM_FLIGHT_BOUNDARY) return;
  const normalX = body.position.x / distance;
  const normalY = body.position.y / distance;
  body.position.x = normalX * LOOM_FLIGHT_BOUNDARY;
  body.position.y = normalY * LOOM_FLIGHT_BOUNDARY;
  const outwardSpeed = body.velocity.x * normalX + body.velocity.y * normalY;
  if (outwardSpeed > 0) {
    body.velocity.x -= outwardSpeed * normalX;
    body.velocity.y -= outwardSpeed * normalY;
  }
}

function clampBodySpeed(body: LoomBody, maximum: number): void {
  const speed = Math.hypot(body.velocity.x, body.velocity.y);
  if (speed <= maximum) return;
  body.velocity.x = (body.velocity.x / speed) * maximum;
  body.velocity.y = (body.velocity.y / speed) * maximum;
}

function updateNeedle(simulation: LoomSimulation, inputX: number, inputY: number): void {
  const { needle } = simulation;
  needle.velocity.x += inputX * NEEDLE_ACCELERATION * LOOM_FIXED_STEP_SECONDS;
  needle.velocity.y += inputY * NEEDLE_ACCELERATION * LOOM_FIXED_STEP_SECONDS;
  const damping = 1 / (1 + NEEDLE_DRAG * LOOM_FIXED_STEP_SECONDS);
  needle.velocity.x *= damping;
  needle.velocity.y *= damping;
  clampBodySpeed(needle, NEEDLE_MAX_SPEED);
  needle.position.x += needle.velocity.x * LOOM_FIXED_STEP_SECONDS;
  needle.position.y += needle.velocity.y * LOOM_FIXED_STEP_SECONDS;
  clampBodyToFlightPlane(needle);
}

function updateEchoAndThread(simulation: LoomSimulation, reel: boolean): void {
  const { needle, echo, thread } = simulation;
  thread.targetLength = reel ? LOOM_REELED_LENGTH : LOOM_EXTENDED_LENGTH;
  const lengthDelta = thread.targetLength - thread.restLength;
  const reelStep = REEL_RATE * LOOM_FIXED_STEP_SECONDS;
  thread.restLength += clamp(lengthDelta, -reelStep, reelStep);

  let deltaX = echo.position.x - needle.position.x;
  let deltaY = echo.position.y - needle.position.y;
  let distance = Math.hypot(deltaX, deltaY);
  if (distance < EPSILON) {
    deltaX = -1;
    deltaY = 0;
    distance = 1;
  }
  const unitX = deltaX / distance;
  const unitY = deltaY / distance;
  const relativeVelocityX = echo.velocity.x - needle.velocity.x;
  const relativeVelocityY = echo.velocity.y - needle.velocity.y;
  const radialVelocity = relativeVelocityX * unitX + relativeVelocityY * unitY;
  const tangentVelocityX = relativeVelocityX - radialVelocity * unitX;
  const tangentVelocityY = relativeVelocityY - radialVelocity * unitY;
  const stiffness = reel ? 43 : 25;
  const radialDamping = reel ? 15 : 8;
  const tangentDamping = reel ? 8.5 : 2.1;
  const springForce = -stiffness * (distance - thread.restLength) - radialDamping * radialVelocity;

  echo.velocity.x += (
    springForce * unitX - tangentDamping * tangentVelocityX
  ) * LOOM_FIXED_STEP_SECONDS;
  echo.velocity.y += (
    springForce * unitY - tangentDamping * tangentVelocityY
  ) * LOOM_FIXED_STEP_SECONDS;
  clampBodySpeed(echo, ECHO_MAX_SPEED);
  echo.position.x += echo.velocity.x * LOOM_FIXED_STEP_SECONDS;
  echo.position.y += echo.velocity.y * LOOM_FIXED_STEP_SECONDS;

  deltaX = echo.position.x - needle.position.x;
  deltaY = echo.position.y - needle.position.y;
  distance = Math.hypot(deltaX, deltaY);
  if (distance > LOOM_MAX_THREAD_LENGTH) {
    const normalX = deltaX / distance;
    const normalY = deltaY / distance;
    echo.position.x = needle.position.x + normalX * LOOM_MAX_THREAD_LENGTH;
    echo.position.y = needle.position.y + normalY * LOOM_MAX_THREAD_LENGTH;
    const relativeOutward =
      (echo.velocity.x - needle.velocity.x) * normalX +
      (echo.velocity.y - needle.velocity.y) * normalY;
    if (relativeOutward > 0) {
      echo.velocity.x -= relativeOutward * normalX;
      echo.velocity.y -= relativeOutward * normalY;
    }
    distance = LOOM_MAX_THREAD_LENGTH;
  }
  clampBodyToFlightPlane(echo);

  const finalDeltaX = echo.position.x - needle.position.x;
  const finalDeltaY = echo.position.y - needle.position.y;
  const finalDistance = Math.hypot(finalDeltaX, finalDeltaY);
  const finalUnitX = finalDistance > EPSILON ? finalDeltaX / finalDistance : -1;
  const finalUnitY = finalDistance > EPSILON ? finalDeltaY / finalDistance : 0;
  const finalRadialVelocity =
    (echo.velocity.x - needle.velocity.x) * finalUnitX +
    (echo.velocity.y - needle.velocity.y) * finalUnitY;
  const stretch = Math.max(0, finalDistance - thread.restLength);
  thread.length = finalDistance;
  thread.tension = clamp(
    stretch / 1.65 + Math.max(0, finalRadialVelocity) / 12,
    0,
    1,
  );
  thread.peakTension = Math.max(thread.peakTension, thread.tension);
}

function pointToThreadDistanceSquared(
  simulation: LoomSimulation,
  x: number,
  y: number,
): number {
  const start = simulation.needle.position;
  const end = simulation.echo.position;
  const lineX = end.x - start.x;
  const lineY = end.y - start.y;
  const lengthSquared = lineX * lineX + lineY * lineY;
  if (lengthSquared < EPSILON) {
    const offsetX = x - start.x;
    const offsetY = y - start.y;
    return offsetX * offsetX + offsetY * offsetY;
  }
  const progress = clamp(
    ((x - start.x) * lineX + (y - start.y) * lineY) / lengthSquared,
    0,
    1,
  );
  const closestX = start.x + lineX * progress;
  const closestY = start.y + lineY * progress;
  const offsetX = x - closestX;
  const offsetY = y - closestY;
  return offsetX * offsetX + offsetY * offsetY;
}

function endpointDistance(simulation: LoomSimulation, anchor: LoomAnchor): number {
  return Math.min(
    Math.hypot(
      simulation.needle.position.x - anchor.x,
      simulation.needle.position.y - anchor.y,
    ),
    Math.hypot(
      simulation.echo.position.x - anchor.x,
      simulation.echo.position.y - anchor.y,
    ),
  );
}

function resonanceMultiplier(simulation: LoomSimulation): number {
  return simulation.resonanceRemaining > EPSILON
    ? LOOM_RESONANCE_SCORE_MULTIPLIER
    : 1;
}

function awardStitch(simulation: LoomSimulation, anchor: LoomAnchor): void {
  const extensionRisk = clamp(
    (simulation.thread.length - LOOM_REELED_LENGTH) /
      (LOOM_EXTENDED_LENGTH - LOOM_REELED_LENGTH),
    0,
    1,
  );
  const closestEndpoint = endpointDistance(simulation, anchor);
  const nearMiss =
    closestEndpoint > ANCHOR_BODY_COLLISION_RADIUS &&
    closestEndpoint <= ANCHOR_NEAR_MISS_RADIUS;
  // Extension raises technique score, but only an authored high-risk route may
  // be described as expressive. Otherwise an untouched extended Thread would
  // falsely receive the game's strongest praise.
  const expressive = anchor.route === "expressive" && extensionRisk >= 0.55;
  simulation.stitchChain += 1;
  simulation.bestStitchChain = Math.max(
    simulation.bestStitchChain,
    simulation.stitchChain,
  );
  simulation.stitches += 1;
  if (expressive) simulation.expressiveStitches += 1;
  else simulation.safeStitches += 1;
  if (nearMiss) simulation.nearMisses += 1;

  const exposureTechnique = anchor.route === "expressive"
    ? extensionRisk * 240 + simulation.thread.tension * 110
    : 0;
  const techniqueScore =
    160 +
    exposureTechnique +
    (anchor.route === "expressive" ? 120 : 0) +
    (nearMiss ? 80 : 0) +
    Math.min(simulation.stitchChain - 1, 8) * 14;
  const multiplier = resonanceMultiplier(simulation);
  const scoreAwarded = techniqueScore * multiplier;
  simulation.score += scoreAwarded;
  simulation.resonanceCharge = Math.min(
    LOOM_RESONANCE_CHARGE_REQUIRED,
    simulation.resonanceCharge + 1,
  );
  simulation.stitchEventSequence += 1;
  simulation.lastStitchEvent = {
    sequence: simulation.stitchEventSequence,
    anchorId: anchor.id,
    chunkId: anchor.chunkId,
    encounterKind: anchor.encounterKind,
    route: anchor.route,
    phase: anchor.phase,
    scoreAwarded,
    chain: simulation.stitchChain,
    expressive,
    nearMiss,
    tension: simulation.thread.tension,
    resonanceActive: multiplier > 1,
  };
}

function approachingAnchor(simulation: LoomSimulation): LoomAnchor | null {
  let selected: LoomAnchor | null = null;
  for (const anchor of simulation.anchors) {
    if (!anchor.active || anchor.resolved || anchor.z > ANCHOR_PASS_Z) continue;
    if (!selected || anchor.z > selected.z) selected = anchor;
  }
  return selected;
}

function armApproachingAnchor(simulation: LoomSimulation): void {
  const anchor = approachingAnchor(simulation);
  if (anchor) anchor.armed = true;
}

function processAnchors(simulation: LoomSimulation, travel: number): void {
  for (const anchor of simulation.anchors) {
    if (!anchor.active) continue;
    anchor.z += travel;

    if (!anchor.resolved && Math.abs(anchor.z) <= ANCHOR_INTERACTION_HALF_DEPTH) {
      const closestEndpoint = endpointDistance(simulation, anchor);
      anchor.closestEndpointDistance = Math.min(
        anchor.closestEndpointDistance,
        closestEndpoint,
      );
      if (!anchor.hit && closestEndpoint <= ANCHOR_BODY_COLLISION_RADIUS) {
        anchor.hit = true;
        simulation.threadBreaks += 1;
        simulation.stitchChain = 0;
        simulation.score = Math.max(0, simulation.score - 60);
      }
      if (
        !anchor.hit &&
        !anchor.latched &&
        anchor.armed &&
        (anchor.encounterKind !== "opening-thread" ||
          simulation.currentInput.reel) &&
        anchor.phase === simulation.phase &&
        pointToThreadDistanceSquared(simulation, anchor.x, anchor.y) <=
          ANCHOR_LATCH_RADIUS ** 2
      ) {
        anchor.latched = true;
        awardStitch(simulation, anchor);
      }
    }

    if (!anchor.resolved && anchor.z >= ANCHOR_PASS_Z) {
      anchor.resolved = true;
      if (!anchor.latched) {
        simulation.missedAnchors += 1;
        simulation.stitchChain = 0;
      }
    }

    if (anchor.z > ANCHOR_DESPAWN_Z) {
      anchor.active = false;
    }
  }
  fillAnchorPool(simulation);
}

function updateResonanceTimers(simulation: LoomSimulation): void {
  if (simulation.resonanceRemaining > EPSILON) {
    simulation.resonanceActiveSeconds += LOOM_FIXED_STEP_SECONDS;
    simulation.resonanceRemaining = Math.max(
      0,
      simulation.resonanceRemaining - LOOM_FIXED_STEP_SECONDS,
    );
    if (simulation.resonanceRemaining < EPSILON) {
      simulation.resonanceRemaining = 0;
      simulation.resonanceCooldownRemaining = LOOM_RESONANCE_RECOVERY_SECONDS;
    }
  } else if (simulation.resonanceCooldownRemaining > EPSILON) {
    simulation.resonanceCooldownRemaining = Math.max(
      0,
      simulation.resonanceCooldownRemaining - LOOM_FIXED_STEP_SECONDS,
    );
    if (simulation.resonanceCooldownRemaining < EPSILON) {
      simulation.resonanceCooldownRemaining = 0;
    }
  }
}

function consumeOneShotInput(simulation: LoomSimulation): void {
  simulation.phaseCooldown = Math.max(
    0,
    simulation.phaseCooldown - LOOM_FIXED_STEP_SECONDS,
  );
  if (simulation.pendingPhaseToggle && simulation.phaseCooldown <= EPSILON) {
    simulation.phase = oppositePhase(simulation.phase);
    simulation.phaseCooldown = PHASE_TOGGLE_COOLDOWN_SECONDS;
    simulation.pendingPhaseToggle = false;
  }

  if (simulation.pendingResonanceActivation) {
    if (
      simulation.resonanceCharge >= LOOM_RESONANCE_CHARGE_REQUIRED &&
      simulation.resonanceRemaining <= EPSILON &&
      simulation.resonanceCooldownRemaining <= EPSILON
    ) {
      simulation.resonanceCharge -= LOOM_RESONANCE_CHARGE_REQUIRED;
      simulation.resonanceRemaining = LOOM_RESONANCE_DURATION_SECONDS;
      simulation.resonanceActivations += 1;
    }
    // A denied press never arms an unexpected future activation.
    simulation.pendingResonanceActivation = false;
  }
}

function resolveIrisContact(simulation: LoomSimulation): void {
  const clearance = loomIrisClearance(simulation);
  const iris = simulation.iris as MutableLoomIrisState;
  iris.resolved = true;
  iris.chargeAwarded = false;
  if (clearance.minimum >= -EPSILON) {
    iris.outcome = "clear";
    simulation.score += LOOM_IRIS_CLEAR_SCORE * resonanceMultiplier(simulation);
    const previousCharge = simulation.resonanceCharge;
    simulation.resonanceCharge = Math.min(
      LOOM_RESONANCE_CHARGE_REQUIRED,
      simulation.resonanceCharge + 1,
    );
    iris.chargeAwarded = simulation.resonanceCharge > previousCharge;
    return;
  }

  iris.outcome = "hit";
  simulation.threadBreaks += 1;
  simulation.missedAnchors += 1;
  simulation.stitchChain = 0;
  simulation.score = Math.max(
    0,
    simulation.score - LOOM_IRIS_HIT_SCORE_PENALTY,
  );
}

function updateIrisSetPiece(simulation: LoomSimulation): void {
  const scheduled = loomIrisStateForElapsed(simulation.seed, simulation.elapsed);
  const newCycle = scheduled.cycle !== simulation.iris.cycle;
  const iris = simulation.iris as MutableLoomIrisState;
  iris.active = scheduled.active;
  iris.cycle = scheduled.cycle;
  iris.stage = scheduled.stage;
  iris.z = scheduled.z;
  iris.gapCenter.x = scheduled.gapCenter.x;
  iris.gapCenter.y = scheduled.gapCenter.y;
  iris.gapRadius = scheduled.gapRadius;
  iris.intensity = scheduled.intensity;

  if (!scheduled.active || newCycle) {
    iris.resolved = false;
    iris.outcome = null;
    iris.chargeAwarded = false;
  }
  if (iris.stage === "contact" && !iris.resolved) {
    resolveIrisContact(simulation);
  }
}

function extractContract(simulation: LoomSimulation): void {
  simulation.status = "extracted";
  simulation.accumulator = 0;
  simulation.result = {
    outcome: "extracted",
    finalScore: Math.floor(simulation.score),
    exactScore: simulation.score,
    durationSeconds: LOOM_CONTRACT_SECONDS,
    distance: simulation.distance,
    stitches: simulation.stitches,
    safeStitches: simulation.safeStitches,
    expressiveStitches: simulation.expressiveStitches,
    missedAnchors: simulation.missedAnchors,
    nearMisses: simulation.nearMisses,
    threadBreaks: simulation.threadBreaks,
    bestStitchChain: simulation.bestStitchChain,
    resonanceActivations: simulation.resonanceActivations,
    resonanceActiveSeconds: simulation.resonanceActiveSeconds,
    peakThreadTension: simulation.thread.peakTension,
    authoredChunksSeen: simulation.authoredChunksSeen,
  };
}

function fixedStep(simulation: LoomSimulation): void {
  const steeringIntent = Math.hypot(
    simulation.currentInput.x,
    simulation.currentInput.y,
  );
  const reelChanged =
    simulation.currentInput.reel !== simulation.previousReelInput;
  const explicitAuthorship =
    steeringIntent > 0.12 ||
    reelChanged ||
    simulation.pendingPhaseToggle ||
    simulation.pendingResonanceActivation;
  if (explicitAuthorship) {
    simulation.hasPlayerAuthorship = true;
    armApproachingAnchor(simulation);
  }
  simulation.previousReelInput = simulation.currentInput.reel;

  const previousNeedleX = simulation.needle.position.x;
  const previousNeedleY = simulation.needle.position.y;
  const previousEchoX = simulation.echo.position.x;
  const previousEchoY = simulation.echo.position.y;
  updateResonanceTimers(simulation);
  consumeOneShotInput(simulation);
  const steering = normalizeSteering(simulation.currentInput);
  updateNeedle(simulation, steering.x, steering.y);
  updateEchoAndThread(simulation, simulation.currentInput.reel);
  const authoredThreadTravel =
    Math.hypot(
      simulation.needle.position.x - previousNeedleX,
      simulation.needle.position.y - previousNeedleY,
    ) +
    Math.hypot(
      simulation.echo.position.x - previousEchoX,
      simulation.echo.position.y - previousEchoY,
    );
  if (simulation.hasPlayerAuthorship && authoredThreadTravel > 0.018) {
    armApproachingAnchor(simulation);
  }

  const travel = simulation.forwardSpeed * LOOM_FIXED_STEP_SECONDS;
  simulation.distance += travel;
  simulation.score += travel * 0.15 * resonanceMultiplier(simulation);
  simulation.nextSpawnZ += travel;
  processAnchors(simulation, travel);

  simulation.tick += 1;
  simulation.elapsed = simulation.tick * LOOM_FIXED_STEP_SECONDS;
  simulation.arc = loomArcForElapsed(simulation.elapsed);
  simulation.forwardSpeed = loomForwardSpeedForElapsed(simulation.elapsed);
  updateIrisSetPiece(simulation);
  if (simulation.elapsed + EPSILON >= LOOM_CONTRACT_SECONDS) {
    simulation.elapsed = LOOM_CONTRACT_SECONDS;
    extractContract(simulation);
  }
}

export function createLoomSimulation(seed: LoomSeed): LoomSimulation {
  const normalized = normalizedSeed(seed);
  const anchors = Array.from(
    { length: LOOM_ANCHOR_POOL_SIZE },
    (_, index) => emptyAnchor(index),
  );
  const simulation: LoomSimulation = {
    seed: normalized,
    rngState: normalized,
    status: "running",
    tick: 0,
    elapsed: 0,
    accumulator: 0,
    distance: 0,
    forwardSpeed: loomForwardSpeedForElapsed(0),
    arc: 1,
    score: 0,
    phase: "ember",
    phaseCooldown: 0,
    previousReelInput: false,
    hasPlayerAuthorship: false,
    pendingPhaseToggle: false,
    pendingResonanceActivation: false,
    currentInput: {
      x: 0,
      y: 0,
      reel: false,
      phaseToggle: false,
      activateResonance: false,
    },
    needle: {
      position: { x: 0, y: 0 },
      velocity: { x: 0, y: 0 },
    },
    echo: {
      position: { x: -4.6, y: 0 },
      velocity: { x: 0, y: 0 },
    },
    thread: {
      length: 4.6,
      restLength: LOOM_EXTENDED_LENGTH,
      targetLength: LOOM_EXTENDED_LENGTH,
      tension: 0,
      peakTension: 0,
    },
    iris: loomIrisStateForElapsed(normalized, 0),
    anchors,
    nextAnchorId: 1,
    nextChunkId: 1,
    nextSpawnZ: INITIAL_SPAWN_Z,
    lastEncounterKind: null,
    chunkBag: [],
    chunkBagArc: null,
    authoredChunksSeen: 0,
    stitchEventSequence: 0,
    lastStitchEvent: null,
    stitches: 0,
    safeStitches: 0,
    expressiveStitches: 0,
    missedAnchors: 0,
    nearMisses: 0,
    threadBreaks: 0,
    stitchChain: 0,
    bestStitchChain: 0,
    resonanceCharge: 0,
    resonanceRemaining: 0,
    resonanceCooldownRemaining: 0,
    resonanceActivations: 0,
    resonanceActiveSeconds: 0,
    result: null,
  };
  fillAnchorPool(simulation);
  return simulation;
}

export function resetLoomSimulation(seed: LoomSeed): LoomSimulation {
  return createLoomSimulation(seed);
}

/**
 * Advances the supplied simulation in place and returns the same reference.
 * One-shot input is latched even when a 120 Hz render call has not accumulated
 * a complete 60 Hz simulation step yet.
 */
export function stepLoomSimulation(
  simulation: LoomSimulation,
  input: LoomInput,
  deltaSeconds: number,
): LoomSimulation {
  if (simulation.status !== "running") return simulation;

  simulation.pendingPhaseToggle ||= Boolean(input.phaseToggle);
  simulation.pendingResonanceActivation ||= Boolean(input.activateResonance);
  simulation.currentInput.x = Number.isFinite(input.x) ? input.x : 0;
  simulation.currentInput.y = Number.isFinite(input.y) ? input.y : 0;
  simulation.currentInput.reel = Boolean(input.reel);
  simulation.currentInput.phaseToggle = false;
  simulation.currentInput.activateResonance = false;

  if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return simulation;
  simulation.accumulator += Math.min(deltaSeconds, MAX_FRAME_DELTA_SECONDS);
  while (
    simulation.accumulator + EPSILON >= LOOM_FIXED_STEP_SECONDS &&
    simulation.status === "running"
  ) {
    simulation.accumulator -= LOOM_FIXED_STEP_SECONDS;
    if (Math.abs(simulation.accumulator) < EPSILON) simulation.accumulator = 0;
    fixedStep(simulation);
  }
  return simulation;
}
