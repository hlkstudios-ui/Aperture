/**
 * Deterministic fixed-step rules for Aperture's single-ball tunnel runner.
 *
 * The simulation owns gameplay truth and deliberately has no browser, Babylon,
 * Rapier, React, audio, or storage dependency. It mutates one bounded state
 * object in place, allowing renderers to interpolate its fractional accumulator
 * without allocating a new obstacle graph on every display frame.
 */

export type BallSeed = number | string;
export type BallStatus = "running" | "crashed" | "extracted";
export type BallPace = 1 | 2 | 3 | 4;
export type BallObstacleKind = "gate" | "block";
export type BallGateResult = "clean" | "clipped";

export interface BallVector2 {
  x: number;
  y: number;
}

export interface BallVector3 extends BallVector2 {
  z: number;
}

export interface BallInput {
  /** Continuous steering intent. Values outside the unit circle are normalized. */
  x: number;
  y: number;
}

export interface BallBody {
  position: BallVector2;
  velocity: BallVector2;
  radius: number;
}

interface BallObstacleBase {
  id: string;
  poolSlot: number;
  active: boolean;
  kind: BallObstacleKind;
  patternId: string;
  /** One-based authored tutorial beat, or null after the lesson. */
  tutorialStep: number | null;
  x: number;
  y: number;
  z: number;
  depth: number;
  passed: boolean;
  hit: boolean;
  /** Presentation hint; collision truth never depends on the renderer. */
  telegraphSeconds: number;
  /** A conservative authored path point used by cues and fairness tests. */
  safePoint: BallVector2;
}

export interface BallGateObstacle extends BallObstacleBase {
  kind: "gate";
  openingRadius: number;
}

export interface BallBlockObstacle extends BallObstacleBase {
  kind: "block";
  width: number;
  height: number;
}

export type BallObstacle = BallGateObstacle | BallBlockObstacle;

export interface BallImpactEvent {
  sequence: number;
  obstacleId: string;
  obstacleKind: BallObstacleKind;
  position: BallVector3;
  /** Unit surface normal pointing away from the contacted hazard. */
  normal: BallVector3;
  shieldsRemaining: number;
  crashed: boolean;
}

export interface BallGateEvent {
  sequence: number;
  obstacleId: string;
  result: BallGateResult;
  position: BallVector3;
  scoreAwarded: number;
  combo: number;
  cleanGateStreak: number;
  overdriveCharge: number;
  overdriveStarted: boolean;
  overdriveActive: boolean;
  nearMiss: boolean;
}

export interface BallSimulationOptions {
  /** Widens generated openings and reduces generated block coverage. */
  assistMode?: boolean;
}

export interface BallSimulation {
  seed: number;
  rngState: number;
  assistMode: boolean;
  status: BallStatus;
  tick: number;
  elapsed: number;
  accumulator: number;
  distance: number;
  score: number;
  speed: number;
  pace: BallPace;
  shields: number;
  invulnerabilityRemaining: number;
  combo: number;
  peakCombo: number;
  cleanGateStreak: number;
  cleanGates: number;
  clippedGates: number;
  nearMisses: number;
  blocksDodged: number;
  impacts: number;
  overdriveCharge: number;
  overdriveRemaining: number;
  overdriveActivations: number;
  overdriveActiveSeconds: number;
  ball: BallBody;
  currentInput: BallInput;
  obstacles: BallObstacle[];
  nextObstacleId: number;
  nextPatternId: number;
  generatedSinceGate: number;
  lastGeneratedKind: BallObstacleKind | null;
  generatedKindRunLength: number;
  generatedKindBag: BallObstacleKind[];
  generatedKindBagIndex: number;
  impactEventSequence: number;
  lastImpactEvent: BallImpactEvent | null;
  gateEventSequence: number;
  lastGateEvent: BallGateEvent | null;
}

export interface BallTutorialBlueprint {
  kind: BallObstacleKind;
  z: number;
  x: number;
  y: number;
  openingRadius?: number;
  width?: number;
  height?: number;
  safePoint: BallVector2;
  patternId: string;
  telegraphSeconds: number;
}

export const BALL_FIXED_STEP_SECONDS = 1 / 60;
export const BALL_TUNNEL_RADIUS = 9;
export const BALL_RADIUS = 0.9;
export const BALL_PLAY_RADIUS = BALL_TUNNEL_RADIUS - BALL_RADIUS - 0.25;
export const BALL_INITIAL_SHIELDS = 3;
export const BALL_HIT_INVULNERABILITY_SECONDS = 0.9;
export const BALL_CONTRACT_DURATION_SECONDS = 105;
export const BALL_CONTRACT_TICKS = Math.round(
  BALL_CONTRACT_DURATION_SECONDS / BALL_FIXED_STEP_SECONDS,
);
export const BALL_OVERDRIVE_GATES_REQUIRED = 4;
export const BALL_OVERDRIVE_DURATION_SECONDS = 5;
export const BALL_OVERDRIVE_SCORE_MULTIPLIER = 2;
export const BALL_OBSTACLE_POOL_SIZE = 12;
export const BALL_MINIMUM_REACTION_SECONDS = 1.55;
export const BALL_INITIAL_SPEED = 9.5;
export const BALL_MAX_SPEED = 39;
export const BALL_PLAYER_ACCELERATION = 70;
export const BALL_PLAYER_DRAG = 6;
export const BALL_PLAYER_MAX_SPEED = 12;

const MAX_FRAME_DELTA_SECONDS = 0.25;
const BALL_OBSTACLE_DESPAWN_Z = 13;
const BALL_BLOCK_PASS_Z = BALL_RADIUS + 1.35;
const GENERATED_BASE_SPACING = 36;
const GENERATED_SPACING_JITTER = 5;
const GATE_SCORE = 300;
const GATE_NEAR_MISS_CLEARANCE = 0.45;
const GATE_NEAR_MISS_BONUS = 100;
const BLOCK_DODGE_SCORE = 120;
const MAX_COMBO = 5;
const COMBO_STEP = 0.25;
const RNG_FALLBACK_SEED = 0x5f3759df;
const EPSILON = 1e-10;

const SPEED_KEYFRAMES = [
  { elapsed: 0, speed: BALL_INITIAL_SPEED },
  { elapsed: 12, speed: 13 },
  { elapsed: 32, speed: 22 },
  { elapsed: 58, speed: 31 },
  { elapsed: 88, speed: BALL_MAX_SPEED },
] as const;

/**
 * Seed-independent opening lesson. Its six physical beats teach four ideas:
 * center, a small deliberate offset, one readable solid, then a gentle slalom.
 */
export const BALL_TUTORIAL_BLUEPRINTS: readonly BallTutorialBlueprint[] = [
  {
    kind: "gate",
    z: -38,
    x: 0,
    y: 0,
    openingRadius: 4.45,
    safePoint: { x: 0, y: 0 },
    patternId: "tutorial-centered-gate",
    telegraphSeconds: 3.2,
  },
  {
    kind: "gate",
    z: -65,
    x: 2.8,
    y: 0.35,
    openingRadius: 3.35,
    safePoint: { x: 2.8, y: 0.35 },
    patternId: "tutorial-offset-gate",
    telegraphSeconds: 3,
  },
  {
    kind: "block",
    z: -95,
    x: -2.7,
    y: 0,
    width: 4,
    height: 4.2,
    safePoint: { x: 2.8, y: 0 },
    patternId: "tutorial-telegraphed-block",
    telegraphSeconds: 3.15,
  },
  {
    kind: "block",
    z: -128,
    x: -5,
    y: 0,
    width: 8,
    height: 20,
    safePoint: { x: 3.25, y: 0 },
    patternId: "tutorial-slalom-right",
    telegraphSeconds: 3.15,
  },
  {
    kind: "block",
    z: -162,
    x: 5,
    y: 0,
    width: 8,
    height: 20,
    safePoint: { x: -3.25, y: 0 },
    patternId: "tutorial-slalom-left",
    telegraphSeconds: 3.15,
  },
  {
    kind: "block",
    z: -196,
    x: -5,
    y: 0,
    width: 8,
    height: 20,
    safePoint: { x: 3.25, y: 0 },
    patternId: "tutorial-slalom-finish",
    telegraphSeconds: 3.15,
  },
] as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function smootherStep(progress: number): number {
  const value = clamp(progress, 0, 1);
  return value ** 3 * (value * (value * 6 - 15) + 10);
}

function normalizedSeed(seed: BallSeed): number {
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

function nextRandom(simulation: BallSimulation): number {
  let state = simulation.rngState >>> 0;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  simulation.rngState = state >>> 0 || RNG_FALLBACK_SEED;
  return simulation.rngState / 0x100000000;
}

export function ballPaceForElapsed(elapsedSeconds: number): BallPace {
  const elapsed = Math.max(0, finite(elapsedSeconds));
  if (elapsed < SPEED_KEYFRAMES[1].elapsed) return 1;
  if (elapsed < SPEED_KEYFRAMES[2].elapsed) return 2;
  if (elapsed < SPEED_KEYFRAMES[3].elapsed) return 3;
  return 4;
}

export function ballSpeedForElapsed(elapsedSeconds: number): number {
  const elapsed = Math.max(0, finite(elapsedSeconds));
  for (let index = 1; index < SPEED_KEYFRAMES.length; index += 1) {
    const previous = SPEED_KEYFRAMES[index - 1];
    const next = SPEED_KEYFRAMES[index];
    if (elapsed <= next.elapsed) {
      const progress = (elapsed - previous.elapsed) / (next.elapsed - previous.elapsed);
      return previous.speed + (next.speed - previous.speed) * smootherStep(progress);
    }
  }
  return BALL_MAX_SPEED;
}

/** Compact aliases for callers that already live in the ball-game namespace. */
export const paceForElapsed = ballPaceForElapsed;
export const speedForElapsed = ballSpeedForElapsed;

export function ballGateCrossesPlayerPlane(
  previousZ: number,
  currentZ: number,
  depth: number,
): boolean {
  const halfDepth = Math.max(0, finite(depth)) / 2;
  return previousZ <= halfDepth && currentZ >= -halfDepth;
}

/** A gate is safe only when the complete sphere fits inside its aperture. */
export function ballFitsGate(
  ball: Readonly<BallBody>,
  gate: Readonly<BallGateObstacle>,
): boolean {
  const distance = Math.hypot(
    ball.position.x - gate.x,
    ball.position.y - gate.y,
  );
  return distance + ball.radius <= gate.openingRadius + EPSILON;
}

export function ballSphereIntersectsBlock(
  ball: Readonly<BallBody>,
  block: Readonly<BallBlockObstacle>,
): boolean {
  const halfWidth = Math.max(0, block.width) / 2;
  const halfHeight = Math.max(0, block.height) / 2;
  const halfDepth = Math.max(0, block.depth) / 2;
  const closestX = clamp(ball.position.x, block.x - halfWidth, block.x + halfWidth);
  const closestY = clamp(ball.position.y, block.y - halfHeight, block.y + halfHeight);
  const closestZ = clamp(0, block.z - halfDepth, block.z + halfDepth);
  const deltaX = ball.position.x - closestX;
  const deltaY = ball.position.y - closestY;
  const deltaZ = -closestZ;
  return deltaX ** 2 + deltaY ** 2 + deltaZ ** 2 <= ball.radius ** 2;
}

function normalized3(vector: BallVector3): BallVector3 {
  const length = Math.hypot(vector.x, vector.y, vector.z);
  if (length <= EPSILON) return { x: 0, y: 0, z: 1 };
  return {
    x: vector.x === 0 ? 0 : vector.x / length,
    y: vector.y === 0 ? 0 : vector.y / length,
    z: vector.z === 0 ? 0 : vector.z / length,
  };
}

export function ballImpactNormalForBlock(
  ball: Readonly<BallBody>,
  block: Readonly<BallBlockObstacle>,
): BallVector3 {
  const halfWidth = block.width / 2;
  const halfHeight = block.height / 2;
  const halfDepth = block.depth / 2;
  const closestX = clamp(ball.position.x, block.x - halfWidth, block.x + halfWidth);
  const closestY = clamp(ball.position.y, block.y - halfHeight, block.y + halfHeight);
  const closestZ = clamp(0, block.z - halfDepth, block.z + halfDepth);
  const outsideNormal = {
    x: ball.position.x - closestX,
    y: ball.position.y - closestY,
    z: -closestZ,
  };
  if (Math.hypot(outsideNormal.x, outsideNormal.y, outsideNormal.z) > EPSILON) {
    return normalized3(outsideNormal);
  }

  const localX = ball.position.x - block.x;
  const localY = ball.position.y - block.y;
  const localZ = -block.z;
  const faces = [
    { distance: halfWidth - Math.abs(localX), normal: { x: localX >= 0 ? 1 : -1, y: 0, z: 0 } },
    { distance: halfHeight - Math.abs(localY), normal: { x: 0, y: localY >= 0 ? 1 : -1, z: 0 } },
    { distance: halfDepth - Math.abs(localZ), normal: { x: 0, y: 0, z: localZ >= 0 ? 1 : -1 } },
  ];
  faces.sort((left, right) => left.distance - right.distance);
  return faces[0]?.normal ?? { x: 0, y: 0, z: 1 };
}

function clampBallInPlace(ball: BallBody): void {
  const distance = Math.hypot(ball.position.x, ball.position.y);
  if (distance <= BALL_PLAY_RADIUS || distance <= EPSILON) return;
  const normalX = ball.position.x / distance;
  const normalY = ball.position.y / distance;
  ball.position.x = normalX * BALL_PLAY_RADIUS;
  ball.position.y = normalY * BALL_PLAY_RADIUS;
  const outwardVelocity = ball.velocity.x * normalX + ball.velocity.y * normalY;
  if (outwardVelocity > 0) {
    ball.velocity.x -= outwardVelocity * normalX;
    ball.velocity.y -= outwardVelocity * normalY;
  }
}

/** Pure convenience wrapper for tests, previews, and external prediction. */
export function clampBallToTunnel(ball: Readonly<BallBody>): BallBody {
  const next: BallBody = {
    position: { ...ball.position },
    velocity: { ...ball.velocity },
    radius: ball.radius,
  };
  clampBallInPlace(next);
  return next;
}

function tutorialObstacle(
  blueprint: Readonly<BallTutorialBlueprint>,
  poolSlot: number,
): BallObstacle {
  const common = {
    id: `tutorial-${poolSlot + 1}`,
    poolSlot,
    active: true,
    patternId: blueprint.patternId,
    tutorialStep: poolSlot + 1,
    x: blueprint.x,
    y: blueprint.y,
    z: blueprint.z,
    depth: blueprint.kind === "gate" ? 0.5 : 2.4,
    passed: false,
    hit: false,
    telegraphSeconds: blueprint.telegraphSeconds,
    safePoint: { ...blueprint.safePoint },
  };
  if (blueprint.kind === "gate") {
    return {
      ...common,
      kind: "gate",
      openingRadius: blueprint.openingRadius ?? 4,
    };
  }
  return {
    ...common,
    kind: "block",
    width: blueprint.width ?? 4,
    height: blueprint.height ?? 4,
  };
}

function inactiveObstacle(poolSlot: number): BallGateObstacle {
  return {
    id: `inactive-${poolSlot}`,
    poolSlot,
    active: false,
    kind: "gate",
    patternId: "inactive",
    tutorialStep: null,
    x: 0,
    y: 0,
    z: -1_000,
    depth: 0.5,
    passed: false,
    hit: false,
    telegraphSeconds: 0,
    safePoint: { x: 0, y: 0 },
    openingRadius: BALL_TUNNEL_RADIUS,
  };
}

function generatedSpacing(simulation: BallSimulation, farthestZ: number): number {
  // Dividing by today's speed intentionally overestimates encounter time while
  // the pace is rising. That samples an equal-or-faster future keyframe, so the
  // authored gap cannot fall below the redline reaction floor.
  const estimatedEncounterElapsed = simulation.elapsed +
    Math.max(0, -farthestZ) / Math.max(simulation.speed, BALL_INITIAL_SPEED);
  const encounterSpeed = ballSpeedForElapsed(estimatedEncounterElapsed);
  return Math.max(
    GENERATED_BASE_SPACING,
    // One complete simulation tick is deliberate safety headroom. It protects
    // the reaction floor from fixed-step quantization at the crossing plane.
    encounterSpeed * (
      BALL_MINIMUM_REACTION_SECONDS + BALL_FIXED_STEP_SECONDS
    ),
  ) + nextRandom(simulation) * GENERATED_SPACING_JITTER;
}

/**
 * Enumerates the tiny set of valid seven-beat shuffle bags. Choosing from the
 * valid set (instead of repeatedly reshuffling) keeps RNG consumption bounded
 * and guarantees both the 4/3 mix and the two-in-a-row limit across bags.
 */
function validGeneratedKindBags(
  previousKind: BallObstacleKind | null,
  previousRunLength: number,
): BallObstacleKind[][] {
  const bags: BallObstacleKind[][] = [];
  const build = (
    gateCount: number,
    blockCount: number,
    lastKind: BallObstacleKind | null,
    runLength: number,
    bag: BallObstacleKind[],
  ) => {
    if (gateCount === 0 && blockCount === 0) {
      bags.push([...bag]);
      return;
    }
    const append = (kind: BallObstacleKind, remaining: number) => {
      if (remaining <= 0 || (kind === lastKind && runLength >= 2)) return;
      bag.push(kind);
      build(
        gateCount - Number(kind === "gate"),
        blockCount - Number(kind === "block"),
        kind,
        kind === lastKind ? runLength + 1 : 1,
        bag,
      );
      bag.pop();
    };
    append("gate", gateCount);
    append("block", blockCount);
  };
  build(
    4,
    3,
    previousKind,
    previousKind ? clamp(Math.floor(previousRunLength), 1, 2) : 0,
    [],
  );
  return bags;
}

function refillGeneratedKindBag(simulation: BallSimulation): void {
  const candidates = validGeneratedKindBags(
    simulation.lastGeneratedKind,
    simulation.generatedKindRunLength,
  );
  const selected = Math.min(
    candidates.length - 1,
    Math.floor(nextRandom(simulation) * candidates.length),
  );
  simulation.generatedKindBag = [...(candidates[selected] ?? [
    "gate",
    "block",
    "gate",
    "block",
    "gate",
    "block",
    "gate",
  ])];
  simulation.generatedKindBagIndex = 0;
}

function nextGeneratedKind(simulation: BallSimulation): BallObstacleKind {
  if (simulation.generatedKindBagIndex >= simulation.generatedKindBag.length) {
    refillGeneratedKindBag(simulation);
  }
  const kind = simulation.generatedKindBag[simulation.generatedKindBagIndex] ?? "gate";
  simulation.generatedKindBagIndex += 1;
  simulation.generatedKindRunLength = kind === simulation.lastGeneratedKind
    ? simulation.generatedKindRunLength + 1
    : 1;
  simulation.lastGeneratedKind = kind;
  simulation.generatedSinceGate = kind === "gate"
    ? 0
    : simulation.generatedSinceGate + 1;
  return kind;
}

function generatedGate(
  simulation: BallSimulation,
  poolSlot: number,
  id: number,
  patternId: string,
  z: number,
): BallGateObstacle {
  const pace = ballPaceForElapsed(
    simulation.elapsed + Math.max(0, -z) / Math.max(simulation.speed, 0.001),
  );
  const baseOpening = ({ 1: 3.85, 2: 3.4, 3: 3.05, 4: 2.72 } as const)[pace];
  const openingRadius = baseOpening +
    (simulation.assistMode ? 0.55 : 0) +
    nextRandom(simulation) * 0.32;
  const maximumCenterRadius = Math.min(
    3.8,
    BALL_TUNNEL_RADIUS - openingRadius - 0.35,
  );
  const centerRadius = (0.35 + nextRandom(simulation) * 0.65) * maximumCenterRadius;
  const angle = nextRandom(simulation) * Math.PI * 2;
  const x = Math.cos(angle) * centerRadius;
  const y = Math.sin(angle) * centerRadius;
  return {
    id: `gate-${id}`,
    poolSlot,
    active: true,
    kind: "gate",
    patternId,
    tutorialStep: null,
    x,
    y,
    z,
    depth: 0.5,
    passed: false,
    hit: false,
    telegraphSeconds: pace >= 3 ? 2.4 : 2.8,
    safePoint: { x, y },
    openingRadius,
  };
}

function generatedBlock(
  simulation: BallSimulation,
  poolSlot: number,
  id: number,
  patternId: string,
  z: number,
): BallBlockObstacle {
  const pace = ballPaceForElapsed(
    simulation.elapsed + Math.max(0, -z) / Math.max(simulation.speed, 0.001),
  );
  const scale = simulation.assistMode ? 0.84 : 1;
  const useBaffle = pace >= 2 && nextRandom(simulation) < 0.48;
  if (useBaffle) {
    const side = nextRandom(simulation) < 0.5 ? -1 : 1;
    const vertical = nextRandom(simulation) < 0.58;
    const coverage = (pace >= 4 ? 8.4 : 7.8) * scale;
    return {
      id: `block-${id}`,
      poolSlot,
      active: true,
      kind: "block",
      patternId,
      tutorialStep: null,
      x: vertical ? side * 5 : 0,
      y: vertical ? 0 : side * 5,
      z,
      depth: 2.4,
      passed: false,
      hit: false,
      telegraphSeconds: 3.15,
      safePoint: vertical
        ? { x: -side * 3.2, y: 0 }
        : { x: 0, y: -side * 3.2 },
      width: vertical ? coverage : 20,
      height: vertical ? 20 : coverage,
    };
  }

  const angle = nextRandom(simulation) * Math.PI * 2;
  const radialDistance = 1.5 + nextRandom(simulation) * 3.4;
  const x = Math.cos(angle) * radialDistance;
  const y = Math.sin(angle) * radialDistance;
  const size = (3.3 + nextRandom(simulation) * (pace >= 3 ? 1.7 : 1.15)) * scale;
  return {
    id: `block-${id}`,
    poolSlot,
    active: true,
    kind: "block",
    patternId,
    tutorialStep: null,
    x,
    y,
    z,
    depth: 2.4,
    passed: false,
    hit: false,
    telegraphSeconds: 2.65,
    safePoint: {
      x: -Math.cos(angle) * 3.4,
      y: -Math.sin(angle) * 3.4,
    },
    width: size,
    height: size * (0.82 + nextRandom(simulation) * 0.36),
  };
}

function spawnGeneratedObstacle(simulation: BallSimulation, poolSlot: number): void {
  const farthestZ = simulation.obstacles.reduce(
    (minimum, obstacle) => obstacle.active ? Math.min(minimum, obstacle.z) : minimum,
    BALL_TUTORIAL_BLUEPRINTS[BALL_TUTORIAL_BLUEPRINTS.length - 1]?.z ?? -196,
  );
  const z = farthestZ - generatedSpacing(simulation, farthestZ);
  const id = simulation.nextObstacleId;
  const patternSequence = simulation.nextPatternId;
  simulation.nextObstacleId += 1;
  simulation.nextPatternId += 1;

  const kind = nextGeneratedKind(simulation);
  const patternId = `generated-${patternSequence}-${kind}`;
  simulation.obstacles[poolSlot] = kind === "gate"
    ? generatedGate(simulation, poolSlot, id, patternId, z)
    : generatedBlock(simulation, poolSlot, id, patternId, z);
}

function fillObstaclePool(simulation: BallSimulation): void {
  for (let slot = 0; slot < BALL_OBSTACLE_POOL_SIZE; slot += 1) {
    if (!simulation.obstacles[slot]?.active) {
      spawnGeneratedObstacle(simulation, slot);
    }
  }
}

function normalizedInput(input: Readonly<BallInput>): BallVector2 {
  let x = clamp(finite(input.x), -1, 1);
  let y = clamp(finite(input.y), -1, 1);
  const length = Math.hypot(x, y);
  if (length > 1) {
    x /= length;
    y /= length;
  }
  return { x, y };
}

function updateBall(simulation: BallSimulation): void {
  const input = normalizedInput(simulation.currentInput);
  const ball = simulation.ball;
  ball.velocity.x += input.x * BALL_PLAYER_ACCELERATION * BALL_FIXED_STEP_SECONDS;
  ball.velocity.y += input.y * BALL_PLAYER_ACCELERATION * BALL_FIXED_STEP_SECONDS;
  const damping = Math.exp(-BALL_PLAYER_DRAG * BALL_FIXED_STEP_SECONDS);
  ball.velocity.x *= damping;
  ball.velocity.y *= damping;
  const speed = Math.hypot(ball.velocity.x, ball.velocity.y);
  if (speed > BALL_PLAYER_MAX_SPEED) {
    ball.velocity.x = (ball.velocity.x / speed) * BALL_PLAYER_MAX_SPEED;
    ball.velocity.y = (ball.velocity.y / speed) * BALL_PLAYER_MAX_SPEED;
  }
  ball.position.x += ball.velocity.x * BALL_FIXED_STEP_SECONDS;
  ball.position.y += ball.velocity.y * BALL_FIXED_STEP_SECONDS;
  clampBallInPlace(ball);
}

function overdriveMultiplier(simulation: BallSimulation): number {
  return simulation.overdriveRemaining > EPSILON
    ? BALL_OVERDRIVE_SCORE_MULTIPLIER
    : 1;
}

function updateOverdrive(simulation: BallSimulation): void {
  if (simulation.overdriveRemaining <= EPSILON) return;
  simulation.overdriveActiveSeconds += BALL_FIXED_STEP_SECONDS;
  simulation.overdriveRemaining = Math.max(
    0,
    simulation.overdriveRemaining - BALL_FIXED_STEP_SECONDS,
  );
  if (simulation.overdriveRemaining < EPSILON) simulation.overdriveRemaining = 0;
}

function applyImpact(
  simulation: BallSimulation,
  obstacle: BallObstacle,
  normal: BallVector3,
): boolean {
  if (
    simulation.invulnerabilityRemaining > EPSILON ||
    simulation.status !== "running"
  ) return false;

  simulation.shields = Math.max(0, simulation.shields - 1);
  simulation.impacts += 1;
  simulation.combo = 1;
  simulation.cleanGateStreak = 0;
  simulation.overdriveCharge = 0;
  simulation.overdriveRemaining = 0;
  simulation.score = Math.max(0, simulation.score - 100);
  simulation.invulnerabilityRemaining = BALL_HIT_INVULNERABILITY_SECONDS;
  const crashed = simulation.shields === 0;
  if (crashed) {
    simulation.status = "crashed";
    simulation.ball.velocity.x = 0;
    simulation.ball.velocity.y = 0;
  }
  simulation.impactEventSequence += 1;
  simulation.lastImpactEvent = {
    sequence: simulation.impactEventSequence,
    obstacleId: obstacle.id,
    obstacleKind: obstacle.kind,
    position: {
      x: simulation.ball.position.x,
      y: simulation.ball.position.y,
      z: obstacle.z,
    },
    normal: normalized3(normal),
    shieldsRemaining: simulation.shields,
    crashed,
  };
  return true;
}

function clippedGateNormal(
  ball: Readonly<BallBody>,
  gate: Readonly<BallGateObstacle>,
): BallVector3 {
  return normalized3({
    x: ball.position.x - gate.x,
    y: ball.position.y - gate.y,
    z: 0.12,
  });
}

function resolveGate(simulation: BallSimulation, gate: BallGateObstacle): void {
  gate.passed = true;
  const clean = ballFitsGate(simulation.ball, gate);
  let scoreAwarded = 0;
  let overdriveStarted = false;
  let nearMiss = false;
  if (clean) {
    simulation.cleanGates += 1;
    simulation.cleanGateStreak += 1;
    simulation.combo = Math.min(MAX_COMBO, simulation.combo + COMBO_STEP);
    simulation.peakCombo = Math.max(simulation.peakCombo, simulation.combo);
    simulation.overdriveCharge += 1;
    if (simulation.overdriveCharge >= BALL_OVERDRIVE_GATES_REQUIRED) {
      simulation.overdriveCharge = 0;
      simulation.overdriveRemaining = BALL_OVERDRIVE_DURATION_SECONDS;
      simulation.overdriveActivations += 1;
      overdriveStarted = true;
    }
    const clearance = gate.openingRadius - (
      Math.hypot(
        simulation.ball.position.x - gate.x,
        simulation.ball.position.y - gate.y,
      ) + simulation.ball.radius
    );
    nearMiss = clearance <= GATE_NEAR_MISS_CLEARANCE + EPSILON;
    if (nearMiss) simulation.nearMisses += 1;
    scoreAwarded = (
      GATE_SCORE * simulation.combo + (nearMiss ? GATE_NEAR_MISS_BONUS : 0)
    ) * overdriveMultiplier(simulation);
    simulation.score += scoreAwarded;
  } else {
    gate.hit = true;
    simulation.clippedGates += 1;
    applyImpact(simulation, gate, clippedGateNormal(simulation.ball, gate));
  }

  simulation.gateEventSequence += 1;
  simulation.lastGateEvent = {
    sequence: simulation.gateEventSequence,
    obstacleId: gate.id,
    result: clean ? "clean" : "clipped",
    position: { x: gate.x, y: gate.y, z: gate.z },
    scoreAwarded,
    combo: simulation.combo,
    cleanGateStreak: simulation.cleanGateStreak,
    overdriveCharge: simulation.overdriveCharge,
    overdriveStarted,
    overdriveActive: simulation.overdriveRemaining > EPSILON,
    nearMiss,
  };
}

function processObstacles(simulation: BallSimulation, travel: number): void {
  for (const obstacle of simulation.obstacles) {
    if (!obstacle.active) continue;
    const previousZ = obstacle.z;
    obstacle.z += travel;

    if (
      obstacle.kind === "gate" &&
      !obstacle.passed &&
      ballGateCrossesPlayerPlane(previousZ, obstacle.z, obstacle.depth)
    ) {
      resolveGate(simulation, obstacle);
    } else if (
      obstacle.kind === "block" &&
      !obstacle.hit &&
      ballSphereIntersectsBlock(simulation.ball, obstacle)
    ) {
      obstacle.hit = true;
      applyImpact(
        simulation,
        obstacle,
        ballImpactNormalForBlock(simulation.ball, obstacle),
      );
    }

    // A terminal impact owns the remainder of its fixed tick. Later pool slots
    // must not award a gate, dodge, or Overdrive after the run has crashed.
    if (simulation.status !== "running") return;

    if (
      obstacle.kind === "block" &&
      !obstacle.passed &&
      obstacle.z > BALL_BLOCK_PASS_Z
    ) {
      obstacle.passed = true;
      if (!obstacle.hit) {
        simulation.blocksDodged += 1;
        simulation.combo = Math.min(MAX_COMBO, simulation.combo + COMBO_STEP);
        simulation.peakCombo = Math.max(simulation.peakCombo, simulation.combo);
        simulation.score += BLOCK_DODGE_SCORE *
          simulation.combo *
          overdriveMultiplier(simulation);
      }
    }

    if (obstacle.z > BALL_OBSTACLE_DESPAWN_Z) obstacle.active = false;
  }
  fillObstaclePool(simulation);
}

function fixedStep(simulation: BallSimulation): void {
  simulation.invulnerabilityRemaining = Math.max(
    0,
    simulation.invulnerabilityRemaining - BALL_FIXED_STEP_SECONDS,
  );
  if (simulation.invulnerabilityRemaining < EPSILON) {
    simulation.invulnerabilityRemaining = 0;
  }
  updateOverdrive(simulation);
  updateBall(simulation);

  const travel = simulation.speed * BALL_FIXED_STEP_SECONDS;
  simulation.distance += travel;
  simulation.score += travel * simulation.combo * overdriveMultiplier(simulation);
  processObstacles(simulation, travel);

  simulation.tick += 1;
  simulation.elapsed = simulation.tick * BALL_FIXED_STEP_SECONDS;
  simulation.pace = ballPaceForElapsed(simulation.elapsed);
  simulation.speed = ballSpeedForElapsed(simulation.elapsed);
  // Obstacles own this tick first. If the last shield is lost on tick 6300,
  // that impact wins and the run cannot also be cleared.
  if (
    simulation.status === "running" &&
    simulation.tick >= BALL_CONTRACT_TICKS
  ) {
    simulation.status = "extracted";
  }
  if (simulation.status !== "running") {
    simulation.ball.velocity.x = 0;
    simulation.ball.velocity.y = 0;
    simulation.accumulator = 0;
  }
}

export function createBallSimulation(
  seed: BallSeed,
  options: BallSimulationOptions = {},
): BallSimulation {
  const normalized = normalizedSeed(seed);
  const obstacles = Array.from(
    { length: BALL_OBSTACLE_POOL_SIZE },
    (_, slot) => slot < BALL_TUTORIAL_BLUEPRINTS.length
      ? tutorialObstacle(BALL_TUTORIAL_BLUEPRINTS[slot], slot)
      : inactiveObstacle(slot),
  );
  const simulation: BallSimulation = {
    seed: normalized,
    rngState: normalized,
    assistMode: Boolean(options.assistMode),
    status: "running",
    tick: 0,
    elapsed: 0,
    accumulator: 0,
    distance: 0,
    score: 0,
    speed: BALL_INITIAL_SPEED,
    pace: 1,
    shields: BALL_INITIAL_SHIELDS,
    invulnerabilityRemaining: 0,
    combo: 1,
    peakCombo: 1,
    cleanGateStreak: 0,
    cleanGates: 0,
    clippedGates: 0,
    nearMisses: 0,
    blocksDodged: 0,
    impacts: 0,
    overdriveCharge: 0,
    overdriveRemaining: 0,
    overdriveActivations: 0,
    overdriveActiveSeconds: 0,
    ball: {
      position: { x: 0, y: 0 },
      velocity: { x: 0, y: 0 },
      radius: BALL_RADIUS,
    },
    currentInput: { x: 0, y: 0 },
    obstacles,
    nextObstacleId: 1,
    nextPatternId: 1,
    generatedSinceGate: 0,
    lastGeneratedKind: null,
    generatedKindRunLength: 0,
    generatedKindBag: [],
    generatedKindBagIndex: 0,
    impactEventSequence: 0,
    lastImpactEvent: null,
    gateEventSequence: 0,
    lastGateEvent: null,
  };
  fillObstaclePool(simulation);
  return simulation;
}

export function resetBallSimulation(
  seed: BallSeed,
  options: BallSimulationOptions = {},
): BallSimulation {
  return createBallSimulation(seed, options);
}

/**
 * Advances `simulation` in place and returns the identical object. The display
 * layer can retain a reference, while event sequence counters make every
 * one-shot impact and gate result snapshot-safe for throttled UI consumers.
 */
export function stepBallSimulation(
  simulation: BallSimulation,
  input: Readonly<BallInput>,
  deltaSeconds: number,
): BallSimulation {
  if (simulation.status !== "running") return simulation;
  simulation.currentInput.x = finite(input.x);
  simulation.currentInput.y = finite(input.y);
  if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return simulation;

  simulation.accumulator += Math.min(deltaSeconds, MAX_FRAME_DELTA_SECONDS);
  while (
    simulation.accumulator + EPSILON >= BALL_FIXED_STEP_SECONDS &&
    simulation.status === "running"
  ) {
    simulation.accumulator -= BALL_FIXED_STEP_SECONDS;
    if (Math.abs(simulation.accumulator) < EPSILON) simulation.accumulator = 0;
    fixedStep(simulation);
  }
  return simulation;
}
