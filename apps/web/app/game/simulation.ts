export type GamePhase = "ember" | "cobalt";

export type GameStatus = "running" | "crashed";

export type SimulationSeed = number | string;

export type GameSector = 1 | 2 | 3 | 4;

export type SignalPhraseKind =
  | "solo-block"
  | "solo-membrane"
  | "slalom"
  | "phase-pulse"
  | "cross-weave"
  | "redline-cascade";

export type SignalPhraseResult = "clean" | "broken";

export interface ActiveSignalPhrase {
  id: string;
  kind: SignalPhraseKind;
  beat: number;
  length: number;
}

export interface SignalPhraseEvent {
  sequence: number;
  phraseId: string;
  phraseKind: SignalPhraseKind;
  result: SignalPhraseResult;
  cleanStreak: number;
  scoreBonus: number;
  resonanceStarted: boolean;
}

export interface SignalPhraseProgress {
  id: string;
  kind: SignalPhraseKind;
  length: number;
  passedBeats: number;
  damaged: boolean;
  scoreBonus: number;
}

export type SignalPhraseBeatBlueprint =
  | {
      kind: "block";
      x: number;
      y: number;
      width: number;
      height: number;
    }
  | {
      kind: "membrane";
      phase: GamePhase;
    };

export interface PendingSignalPhrase {
  id: string;
  kind: SignalPhraseKind;
  nextBeatIndex: number;
  beats: SignalPhraseBeatBlueprint[];
}

export interface InputState {
  x: number;
  y: number;
  phaseToggle: boolean;
}

export interface Vector2 {
  x: number;
  y: number;
}

export interface PlayerState {
  position: Vector2;
  velocity: Vector2;
  radius: number;
}

interface ObstacleBase {
  id: string;
  poolSlot: number;
  phraseId: string;
  phraseKind: SignalPhraseKind;
  phraseBeat: number;
  phraseLength: number;
  x: number;
  y: number;
  z: number;
  depth: number;
  passed: boolean;
  hit: boolean;
}

export interface BlockObstacle extends ObstacleBase {
  kind: "block";
  width: number;
  height: number;
}

export interface MembraneObstacle extends ObstacleBase {
  kind: "membrane";
  radius: number;
  phase: GamePhase;
}

export type GameObstacle = BlockObstacle | MembraneObstacle;

export interface Sphere3D {
  x: number;
  y: number;
  z: number;
  radius: number;
}

export interface GameSimulation {
  seed: number;
  rngState: number;
  nextObstacleId: number;
  player: PlayerState;
  distance: number;
  score: number;
  integrity: number;
  combo: number;
  phase: GamePhase;
  speed: number;
  elapsed: number;
  invulnerability: number;
  phaseCooldown: number;
  status: GameStatus;
  obstacles: GameObstacle[];
  accumulator: number;
  pendingPhaseToggle: boolean;
  nextPhraseId: number;
  lastPhraseKind: SignalPhraseKind | null;
  phrasesSinceMovementCheck: number;
  pendingPhrase: PendingSignalPhrase | null;
  phraseProgress: SignalPhraseProgress[];
  activePhrase: ActiveSignalPhrase | null;
  phrasesCompleted: number;
  cleanPhrases: number;
  cleanPhraseStreak: number;
  peakCleanPhraseStreak: number;
  resonancePips: number;
  resonanceRemaining: number;
  resonanceActivations: number;
  phraseEventSequence: number;
  lastPhraseEvent: SignalPhraseEvent | null;
}

export const FIXED_STEP_SECONDS = 1 / 60;
export const TUNNEL_RADIUS = 9;
// The collider follows the runner's full wing span rather than only its glowing core.
export const PLAYER_RADIUS = 1.7;
export const PLAYER_VERTICAL_COLLISION_RADIUS = 0.95;
export const PLAYER_DEPTH_COLLISION_RADIUS = 1.55;
// All beats score on one conservative center plane. Using each mesh's depth
// made thin membranes award earlier than blocks even at the same authored
// cadence, reintroducing seed luck through content geometry.
export const OBSTACLE_PASS_CENTER_Z = PLAYER_DEPTH_COLLISION_RADIUS + 1.2;
export const PLAYER_BOUNDARY_RADIUS = TUNNEL_RADIUS - PLAYER_RADIUS - 0.25;
export const PLAYER_VERTICAL_BOUNDARY_RADIUS =
  TUNNEL_RADIUS - PLAYER_VERTICAL_COLLISION_RADIUS - 0.25;
export const PHASE_TOGGLE_COOLDOWN_SECONDS = 0.22;
export const HIT_INVULNERABILITY_SECONDS = 0.9;
export const RESONANCE_PIPS_REQUIRED = 3;
export const RESONANCE_DURATION_SECONDS = 6;
export const RESONANCE_SCORE_MULTIPLIER = 2;
export const MAX_PHRASES_WITHOUT_MOVEMENT_CHECK = 3;
export const MOVEMENT_CHECK_BAFFLE_CENTER_X = 5;
export const MOVEMENT_CHECK_BAFFLE_WIDTH = 8;
export const MOVEMENT_CHECK_BAFFLE_HEIGHT = TUNNEL_RADIUS * 2 + 2;

export const SIGNAL_PHRASE_LABELS: Record<SignalPhraseKind, string> = {
  "solo-block": "Drift mark",
  "solo-membrane": "Phase check",
  slalom: "Switchback",
  "phase-pulse": "Call and response",
  "cross-weave": "Cross weave",
  "redline-cascade": "Redline cascade",
};

const INITIAL_INTEGRITY = 3;
export const INITIAL_SPEED = 9.5;
export const MAX_SPEED = 39;
const MAX_FRAME_DELTA_SECONDS = 0.25;
const PLAYER_ACCELERATION = 46;
const PLAYER_DRAG = 5;
const MAX_PLAYER_SPEED = 10;
const MAX_COMBO = 5;
const COMBO_STEP = 0.25;
const PASS_BONUS = 75;
const CLEAN_BEAT_BONUS = 240;
const PHRASE_STREAK_BONUS_CAP = 4;
const OBSTACLE_POOL_SIZE = 8;
const INITIAL_SPAWN_Z = -48;
const BASE_SPAWN_SPACING = 38;
export const MINIMUM_OBSTACLE_REACTION_SECONDS = 1.55;
const SPAWN_SPACING_JITTER = 8;
const DESPAWN_Z = 16;
const RNG_FALLBACK_SEED = 0x6d2b79f5;
const EPSILON = 1e-10;

const PHRASE_MINIMUM_SECTOR: Record<SignalPhraseKind, GameSector> = {
  "solo-block": 1,
  "solo-membrane": 1,
  slalom: 2,
  "phase-pulse": 2,
  "cross-weave": 3,
  "redline-cascade": 4,
};

const SIGNAL_PHRASE_KINDS = Object.keys(
  PHRASE_MINIMUM_SECTOR,
) as SignalPhraseKind[];

const SPEED_KEYFRAMES = [
  { elapsed: 0, speed: INITIAL_SPEED },
  { elapsed: 12, speed: 13 },
  { elapsed: 32, speed: 22 },
  { elapsed: 58, speed: 31 },
  { elapsed: 88, speed: MAX_SPEED },
] as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizedElapsed(elapsedSeconds: number): number {
  if (Number.isNaN(elapsedSeconds) || elapsedSeconds <= 0) {
    return 0;
  }
  return elapsedSeconds;
}

function smootherStep(progress: number): number {
  const value = clamp(progress, 0, 1);
  return value ** 3 * (value * (value * 6 - 15) + 10);
}

/** Returns the current pace band for progression callouts and HUD treatment. */
export function sectorForElapsed(elapsedSeconds: number): GameSector {
  const elapsed = normalizedElapsed(elapsedSeconds);
  if (elapsed < SPEED_KEYFRAMES[1].elapsed) {
    return 1;
  }
  if (elapsed < SPEED_KEYFRAMES[2].elapsed) {
    return 2;
  }
  if (elapsed < SPEED_KEYFRAMES[3].elapsed) {
    return 3;
  }
  return 4;
}

/**
 * Smooth, deterministic pace curve. Each sector accelerates without a velocity
 * jump, keeping the opening readable while still reaching a genuine redline.
 */
export function speedForElapsed(elapsedSeconds: number): number {
  const elapsed = normalizedElapsed(elapsedSeconds);
  for (let index = 1; index < SPEED_KEYFRAMES.length; index += 1) {
    const previous = SPEED_KEYFRAMES[index - 1];
    const next = SPEED_KEYFRAMES[index];
    if (elapsed <= next.elapsed) {
      const progress = (elapsed - previous.elapsed) / (next.elapsed - previous.elapsed);
      const easedProgress = smootherStep(progress);
      return previous.speed + (next.speed - previous.speed) * easedProgress;
    }
  }
  return MAX_SPEED;
}

export function minimumObstacleSpacingForSpeed(speed: number): number {
  const safeSpeed = Number.isFinite(speed) ? clamp(speed, 0, MAX_SPEED) : MAX_SPEED;
  return Math.max(
    BASE_SPAWN_SPACING,
    safeSpeed * MINIMUM_OBSTACLE_REACTION_SECONDS,
  );
}

/**
 * A seed-independent low-discrepancy rhythm for encounter spacing. Phrase
 * content remains seeded and surprising, while an equally clean run receives
 * the same number and timing of scoring opportunities on every retry.
 */
export function obstacleCadenceJitter(sequence: number): number {
  let index = Number.isFinite(sequence)
    ? Math.max(1, Math.trunc(sequence))
    : 1;
  let inverse = 0;
  let place = 0.5;
  while (index > 0) {
    inverse += (index % 2) * place;
    index = Math.floor(index / 2);
    place *= 0.5;
  }
  return inverse * SPAWN_SPACING_JITTER;
}

/** Phrase vocabulary available by the time a sector begins. */
export function eligiblePhraseKindsForSector(
  sector: GameSector,
): SignalPhraseKind[] {
  return SIGNAL_PHRASE_KINDS.filter(
    (kind) => PHRASE_MINIMUM_SECTOR[kind] <= sector,
  );
}

/** Resonance deliberately changes reward only, never movement or hazard timing. */
export function scoreMultiplierForSimulation(
  simulation: Pick<GameSimulation, "resonanceRemaining">,
): number {
  return simulation.resonanceRemaining > EPSILON
    ? RESONANCE_SCORE_MULTIPLIER
    : 1;
}

function normalizedSeed(seed: SimulationSeed): number {
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

function nextRandom(simulation: GameSimulation): number {
  let state = simulation.rngState >>> 0;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  simulation.rngState = state >>> 0 || RNG_FALLBACK_SEED;
  return simulation.rngState / 0x100000000;
}

function cloneObstacle(obstacle: GameObstacle): GameObstacle {
  return { ...obstacle };
}

function cloneSimulation(simulation: GameSimulation): GameSimulation {
  return {
    ...simulation,
    player: {
      ...simulation.player,
      position: { ...simulation.player.position },
      velocity: { ...simulation.player.velocity },
    },
    obstacles: simulation.obstacles.map(cloneObstacle),
    pendingPhrase: simulation.pendingPhrase
      ? {
          ...simulation.pendingPhrase,
          beats: simulation.pendingPhrase.beats.map((beat) => ({ ...beat })),
        }
      : null,
    phraseProgress: simulation.phraseProgress.map((phrase) => ({ ...phrase })),
    activePhrase: simulation.activePhrase ? { ...simulation.activePhrase } : null,
    lastPhraseEvent: simulation.lastPhraseEvent
      ? { ...simulation.lastPhraseEvent }
      : null,
  };
}

function freePoolSlot(obstacles: GameObstacle[]): number | null {
  const occupied = new Set(obstacles.map((obstacle) => obstacle.poolSlot));
  for (let slot = 0; slot < OBSTACLE_POOL_SIZE; slot += 1) {
    if (!occupied.has(slot)) {
      return slot;
    }
  }
  return null;
}

function oppositePhase(phase: GamePhase): GamePhase {
  return phase === "ember" ? "cobalt" : "ember";
}

function blockBeat(
  angle: number,
  radialDistance: number,
  width: number,
  height = width,
): SignalPhraseBeatBlueprint {
  return {
    kind: "block",
    x: Math.cos(angle) * radialDistance,
    y: Math.sin(angle) * radialDistance,
    width,
    height,
  };
}

function buildPhraseBeats(
  simulation: GameSimulation,
  kind: SignalPhraseKind,
): SignalPhraseBeatBlueprint[] {
  const angle = nextRandom(simulation) * Math.PI * 2;
  const basePhase: GamePhase = nextRandom(simulation) < 0.5 ? "ember" : "cobalt";

  switch (kind) {
    case "solo-block": {
      const radialDistance = 1.5 + nextRandom(simulation) * 3.25;
      return [
        blockBeat(
          angle,
          radialDistance,
          2.2 + nextRandom(simulation) * 1.1,
          2.2 + nextRandom(simulation) * 1.1,
        ),
      ];
    }
    case "solo-membrane":
      return [{ kind: "membrane", phase: basePhase }];
    case "slalom": {
      const firstSide = nextRandom(simulation) < 0.5 ? -1 : 1;
      return [
        blockBeat(
          firstSide < 0 ? Math.PI : 0,
          MOVEMENT_CHECK_BAFFLE_CENTER_X,
          MOVEMENT_CHECK_BAFFLE_WIDTH,
          MOVEMENT_CHECK_BAFFLE_HEIGHT,
        ),
        blockBeat(
          firstSide < 0 ? 0 : Math.PI,
          MOVEMENT_CHECK_BAFFLE_CENTER_X,
          MOVEMENT_CHECK_BAFFLE_WIDTH,
          MOVEMENT_CHECK_BAFFLE_HEIGHT,
        ),
        blockBeat(
          firstSide < 0 ? Math.PI : 0,
          MOVEMENT_CHECK_BAFFLE_CENTER_X,
          MOVEMENT_CHECK_BAFFLE_WIDTH,
          MOVEMENT_CHECK_BAFFLE_HEIGHT,
        ),
      ];
    }
    case "phase-pulse":
      return [
        { kind: "membrane", phase: basePhase },
        { kind: "membrane", phase: oppositePhase(basePhase) },
        { kind: "membrane", phase: basePhase },
      ];
    case "cross-weave":
      return [
        { kind: "membrane", phase: basePhase },
        blockBeat(angle, 2.1 + nextRandom(simulation) * 0.5, 2.7),
        { kind: "membrane", phase: oppositePhase(basePhase) },
      ];
    case "redline-cascade": {
      const radialDistance = 2 + nextRandom(simulation) * 0.45;
      return [
        blockBeat(angle, radialDistance, 2.75),
        { kind: "membrane", phase: basePhase },
        blockBeat(angle + (Math.PI * 2) / 3, radialDistance, 2.75),
      ];
    }
  }
}

function choosePhraseKind(
  simulation: GameSimulation,
  sector: GameSector,
): SignalPhraseKind {
  if (
    sector >= 2 &&
    simulation.phrasesSinceMovementCheck >= MAX_PHRASES_WITHOUT_MOVEMENT_CHECK
  ) {
    return "slalom";
  }

  const eligible = eligiblePhraseKindsForSector(sector);
  const withoutImmediateRepeat = eligible.filter(
    (kind) => kind !== simulation.lastPhraseKind,
  );
  const choices = withoutImmediateRepeat.length > 0
    ? withoutImmediateRepeat
    : eligible;
  return choices[Math.floor(nextRandom(simulation) * choices.length)] ?? "solo-block";
}

function queuePhrase(simulation: GameSimulation, sector: GameSector): PendingSignalPhrase {
  const kind = choosePhraseKind(simulation, sector);
  const id = "phrase-" + simulation.nextPhraseId;
  const beats = buildPhraseBeats(simulation, kind);
  simulation.nextPhraseId += 1;
  simulation.lastPhraseKind = kind;
  simulation.phrasesSinceMovementCheck = sector < 2 || kind === "slalom"
    ? 0
    : simulation.phrasesSinceMovementCheck + 1;
  simulation.phraseProgress.push({
    id,
    kind,
    length: beats.length,
    passedBeats: 0,
    damaged: false,
    scoreBonus: 0,
  });
  return { id, kind, nextBeatIndex: 0, beats };
}

function projectedSectorForEncounter(simulation: GameSimulation, z: number): GameSector {
  let projectedElapsed = simulation.elapsed;
  let remainingDistance = Math.max(0, -z);

  // Integrate the known speed curve instead of dividing by today's speed.
  // That prevents far pooled hazards from unlocking a later-sector phrase
  // before the player actually reaches that sector as acceleration builds.
  while (remainingDistance > EPSILON) {
    const currentSpeed = speedForElapsed(projectedElapsed);
    const duration = Math.min(0.25, remainingDistance / currentSpeed);
    const midpointSpeed = speedForElapsed(projectedElapsed + duration / 2);
    remainingDistance = Math.max(0, remainingDistance - midpointSpeed * duration);
    projectedElapsed += duration;
  }

  return sectorForElapsed(projectedElapsed);
}

function spawnObstacle(simulation: GameSimulation): void {
  const poolSlot = freePoolSlot(simulation.obstacles);
  if (poolSlot === null) {
    return;
  }

  const farthestZ = simulation.obstacles.reduce(
    (farthest, obstacle) => Math.min(farthest, obstacle.z),
    INITIAL_SPAWN_Z + BASE_SPAWN_SPACING,
  );
  const approachSpeed = Math.max(INITIAL_SPEED, simulation.speed);
  const secondsUntilFarthestEncounter = Math.max(0, -farthestZ) / approachSpeed;
  const projectedEncounterSpeed = speedForElapsed(
    simulation.elapsed +
      secondsUntilFarthestEncounter +
      MINIMUM_OBSTACLE_REACTION_SECONDS,
  );
  const spacing =
    minimumObstacleSpacingForSpeed(projectedEncounterSpeed) +
    obstacleCadenceJitter(simulation.nextObstacleId);
  const z = simulation.obstacles.length === 0 ? INITIAL_SPAWN_Z : farthestZ - spacing;
  const pendingPhrase = simulation.pendingPhrase ?? queuePhrase(
    simulation,
    projectedSectorForEncounter(simulation, z),
  );
  simulation.pendingPhrase = pendingPhrase;

  const beatIndex = pendingPhrase.nextBeatIndex;
  const beat = pendingPhrase.beats[beatIndex];
  if (!beat) {
    simulation.pendingPhrase = null;
    spawnObstacle(simulation);
    return;
  }

  const phraseBeat = beatIndex + 1;
  const phraseLength = pendingPhrase.beats.length;
  pendingPhrase.nextBeatIndex += 1;
  if (pendingPhrase.nextBeatIndex >= phraseLength) {
    simulation.pendingPhrase = null;
  }

  const sequence = simulation.nextObstacleId;
  const id = beat.kind + "-" + sequence;
  simulation.nextObstacleId += 1;
  const phraseMetadata = {
    phraseId: pendingPhrase.id,
    phraseKind: pendingPhrase.kind,
    phraseBeat,
    phraseLength,
  };

  if (beat.kind === "membrane") {
    simulation.obstacles.push({
      id,
      poolSlot,
      ...phraseMetadata,
      kind: beat.kind,
      x: 0,
      y: 0,
      z,
      radius: TUNNEL_RADIUS,
      depth: 0.4,
      phase: beat.phase,
      passed: false,
      hit: false,
    });
    return;
  }

  simulation.obstacles.push({
    id,
    poolSlot,
    ...phraseMetadata,
    kind: beat.kind,
    x: beat.x,
    y: beat.y,
    z,
    width: beat.width,
    height: beat.height,
    depth: 2.4,
    passed: false,
    hit: false,
  });
}

function updateActivePhrase(simulation: GameSimulation): void {
  const nextObstacle = simulation.obstacles.reduce<GameObstacle | null>(
    (nearest, obstacle) => {
      if (obstacle.passed) return nearest;
      return nearest === null || obstacle.z > nearest.z ? obstacle : nearest;
    },
    null,
  );
  simulation.activePhrase = nextObstacle
    ? {
        id: nextObstacle.phraseId,
        kind: nextObstacle.phraseKind,
        beat: nextObstacle.phraseBeat,
        length: nextObstacle.phraseLength,
      }
    : null;
}

function fillObstaclePool(simulation: GameSimulation): void {
  while (simulation.obstacles.length < OBSTACLE_POOL_SIZE) {
    spawnObstacle(simulation);
  }
  updateActivePhrase(simulation);
}

export function sphereIntersectsAabb(sphere: Sphere3D, block: BlockObstacle): boolean {
  const halfWidth = block.width / 2;
  const halfHeight = block.height / 2;
  const halfDepth = block.depth / 2;
  const closestX = clamp(sphere.x, block.x - halfWidth, block.x + halfWidth);
  const closestY = clamp(sphere.y, block.y - halfHeight, block.y + halfHeight);
  const closestZ = clamp(sphere.z, block.z - halfDepth, block.z + halfDepth);
  const deltaX = sphere.x - closestX;
  const deltaY = sphere.y - closestY;
  const deltaZ = sphere.z - closestZ;
  return deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ <= sphere.radius ** 2;
}

/** Uses the runner's wide, shallow silhouette instead of a phantom-hit sphere. */
export function playerIntersectsBlock(player: PlayerState, block: BlockObstacle): boolean {
  const halfWidth = block.width / 2;
  const halfHeight = block.height / 2;
  const halfDepth = block.depth / 2;
  const closestX = clamp(player.position.x, block.x - halfWidth, block.x + halfWidth);
  const closestY = clamp(player.position.y, block.y - halfHeight, block.y + halfHeight);
  const closestZ = clamp(0, block.z - halfDepth, block.z + halfDepth);
  const normalizedX = (player.position.x - closestX) / player.radius;
  const normalizedY = (player.position.y - closestY) / PLAYER_VERTICAL_COLLISION_RADIUS;
  const normalizedZ = (0 - closestZ) / PLAYER_DEPTH_COLLISION_RADIUS;
  return normalizedX ** 2 + normalizedY ** 2 + normalizedZ ** 2 <= 1;
}

export function membraneCrossesPlayerPlane(
  previousZ: number,
  currentZ: number,
  depth: number,
): boolean {
  const halfDepth = depth / 2;
  return previousZ <= halfDepth && currentZ >= -halfDepth;
}

export function obstacleCollidesWithPlayer(
  player: PlayerState,
  obstacle: GameObstacle,
  phase: GamePhase,
  previousZ = obstacle.z,
): boolean {
  if (obstacle.kind === "membrane") {
    return (
      obstacle.phase !== phase &&
      membraneCrossesPlayerPlane(previousZ, obstacle.z, obstacle.depth)
    );
  }

  return playerIntersectsBlock(player, obstacle);
}

function clampPlayerInPlace(player: PlayerState): PlayerState {
  const { position, velocity } = player;
  const normalizedX = position.x / PLAYER_BOUNDARY_RADIUS;
  const normalizedY = position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS;
  const ellipticalDistance = Math.hypot(normalizedX, normalizedY);
  if (ellipticalDistance <= 1 || ellipticalDistance === 0) {
    return player;
  }

  position.x /= ellipticalDistance;
  position.y /= ellipticalDistance;

  // The ellipse gradient is the surface normal. Removing only its positive
  // component preserves tangential movement instead of making the wall sticky.
  let normalX = position.x / PLAYER_BOUNDARY_RADIUS ** 2;
  let normalY = position.y / PLAYER_VERTICAL_BOUNDARY_RADIUS ** 2;
  const normalLength = Math.hypot(normalX, normalY);
  normalX /= normalLength;
  normalY /= normalLength;
  const outwardVelocity = velocity.x * normalX + velocity.y * normalY;
  if (outwardVelocity > 0) {
    velocity.x -= outwardVelocity * normalX;
    velocity.y -= outwardVelocity * normalY;
  }
  return player;
}

export function clampPlayerToTunnel(player: PlayerState): PlayerState {
  return clampPlayerInPlace({
    ...player,
    position: { ...player.position },
    velocity: { ...player.velocity },
  });
}

function normalizedInput(input: InputState): Vector2 {
  let x = Number.isFinite(input.x) ? clamp(input.x, -1, 1) : 0;
  let y = Number.isFinite(input.y) ? clamp(input.y, -1, 1) : 0;
  const length = Math.hypot(x, y);
  if (length > 1) {
    x /= length;
    y /= length;
  }
  return { x, y };
}

function updatePlayer(simulation: GameSimulation, input: Vector2): void {
  const { player } = simulation;
  player.velocity.x += input.x * PLAYER_ACCELERATION * FIXED_STEP_SECONDS;
  player.velocity.y += input.y * PLAYER_ACCELERATION * FIXED_STEP_SECONDS;
  const damping = Math.exp(-PLAYER_DRAG * FIXED_STEP_SECONDS);
  player.velocity.x *= damping;
  player.velocity.y *= damping;

  const speed = Math.hypot(player.velocity.x, player.velocity.y);
  if (speed > MAX_PLAYER_SPEED) {
    player.velocity.x = (player.velocity.x / speed) * MAX_PLAYER_SPEED;
    player.velocity.y = (player.velocity.y / speed) * MAX_PLAYER_SPEED;
  }

  player.position.x += player.velocity.x * FIXED_STEP_SECONDS;
  player.position.y += player.velocity.y * FIXED_STEP_SECONDS;
  simulation.player = clampPlayerInPlace(player);
}

function phraseProgressFor(
  simulation: GameSimulation,
  phraseId: string,
): SignalPhraseProgress | undefined {
  return simulation.phraseProgress.find((phrase) => phrase.id === phraseId);
}

function markPhraseDamaged(simulation: GameSimulation, phraseId: string): void {
  const progress = phraseProgressFor(simulation, phraseId);
  if (!progress) return;
  progress.damaged = true;
  simulation.cleanPhraseStreak = 0;
  simulation.resonancePips = 0;
}

function awardCleanBeat(
  simulation: GameSimulation,
  scoreMultiplier: number,
): { scoreBonus: number; resonanceStarted: boolean } {
  simulation.cleanPhraseStreak += 1;
  simulation.peakCleanPhraseStreak = Math.max(
    simulation.peakCleanPhraseStreak,
    simulation.cleanPhraseStreak,
  );

  const totalResonanceCharge = simulation.resonancePips + 1;
  const resonanceStarted = totalResonanceCharge >= RESONANCE_PIPS_REQUIRED;
  simulation.resonancePips = totalResonanceCharge % RESONANCE_PIPS_REQUIRED;
  if (resonanceStarted) {
    simulation.resonanceRemaining = RESONANCE_DURATION_SECONDS;
    simulation.resonanceActivations += 1;
  }

  const scoreBonus =
    CLEAN_BEAT_BONUS *
    Math.min(simulation.cleanPhraseStreak, PHRASE_STREAK_BONUS_CAP) *
    scoreMultiplier;
  simulation.score += scoreBonus;
  return { scoreBonus, resonanceStarted };
}

function resolvePhrase(
  simulation: GameSimulation,
  progress: SignalPhraseProgress,
  resonanceStartedOnResolvingBeat: boolean,
): void {
  const clean = !progress.damaged;

  simulation.phrasesCompleted += 1;
  if (clean) {
    simulation.cleanPhrases += 1;
  }

  simulation.phraseEventSequence += 1;
  simulation.lastPhraseEvent = {
    sequence: simulation.phraseEventSequence,
    phraseId: progress.id,
    phraseKind: progress.kind,
    result: clean ? "clean" : "broken",
    cleanStreak: simulation.cleanPhraseStreak,
    scoreBonus: progress.scoreBonus,
    resonanceStarted: resonanceStartedOnResolvingBeat,
  };
  simulation.phraseProgress = simulation.phraseProgress.filter(
    (phrase) => phrase.id !== progress.id,
  );
}

function registerPhraseBeatPassed(
  simulation: GameSimulation,
  obstacle: GameObstacle,
  scoreMultiplier: number,
): void {
  const progress = phraseProgressFor(simulation, obstacle.phraseId);
  if (!progress) return;
  progress.passedBeats += 1;
  let resonanceStartedOnThisBeat = false;
  if (!obstacle.hit) {
    const reward = awardCleanBeat(simulation, scoreMultiplier);
    progress.scoreBonus += reward.scoreBonus;
    resonanceStartedOnThisBeat = reward.resonanceStarted;
  }
  if (progress.passedBeats >= progress.length) {
    resolvePhrase(simulation, progress, resonanceStartedOnThisBeat);
  }
}

function applyObstacleHit(simulation: GameSimulation): void {
  if (simulation.invulnerability > 0 || simulation.status === "crashed") {
    return;
  }

  simulation.integrity = Math.max(0, simulation.integrity - 1);
  simulation.combo = 1;
  simulation.invulnerability = HIT_INVULNERABILITY_SECONDS;
  if (simulation.integrity === 0) {
    simulation.status = "crashed";
    simulation.player.velocity = { x: 0, y: 0 };
  }
}

function processObstacles(
  simulation: GameSimulation,
  travel: number,
  scoreMultiplier: number,
): void {
  for (const obstacle of simulation.obstacles) {
    const previousZ = obstacle.z;
    obstacle.z += travel;

    if (
      !obstacle.hit &&
      obstacleCollidesWithPlayer(simulation.player, obstacle, simulation.phase, previousZ)
    ) {
      obstacle.hit = true;
      markPhraseDamaged(simulation, obstacle.phraseId);
      applyObstacleHit(simulation);
    }

    if (!obstacle.passed && obstacle.z > OBSTACLE_PASS_CENTER_Z) {
      obstacle.passed = true;
      if (!obstacle.hit) {
        simulation.combo = Math.min(MAX_COMBO, simulation.combo + COMBO_STEP);
        simulation.score += PASS_BONUS * simulation.combo * scoreMultiplier;
      }
      registerPhraseBeatPassed(simulation, obstacle, scoreMultiplier);
    }
  }

  if (simulation.obstacles.some((obstacle) => obstacle.z > DESPAWN_Z)) {
    simulation.obstacles = simulation.obstacles.filter((obstacle) => obstacle.z <= DESPAWN_Z);
  }
  fillObstaclePool(simulation);
  updateActivePhrase(simulation);
}

function fixedStep(simulation: GameSimulation, input: Vector2): void {
  const scoreMultiplier = scoreMultiplierForSimulation(simulation);
  if (simulation.resonanceRemaining > EPSILON) {
    simulation.resonanceRemaining = Math.max(
      0,
      simulation.resonanceRemaining - FIXED_STEP_SECONDS,
    );
    if (simulation.resonanceRemaining < EPSILON) {
      simulation.resonanceRemaining = 0;
    }
  }
  simulation.invulnerability = Math.max(
    0,
    simulation.invulnerability - FIXED_STEP_SECONDS,
  );
  simulation.phaseCooldown = Math.max(
    0,
    simulation.phaseCooldown - FIXED_STEP_SECONDS,
  );

  if (simulation.pendingPhaseToggle) {
    if (simulation.phaseCooldown === 0) {
      simulation.phase = simulation.phase === "ember" ? "cobalt" : "ember";
      simulation.phaseCooldown = PHASE_TOGGLE_COOLDOWN_SECONDS;
      simulation.pendingPhaseToggle = false;
    }
  }

  updatePlayer(simulation, input);
  const travel = simulation.speed * FIXED_STEP_SECONDS;
  simulation.distance += travel;
  simulation.score += travel * simulation.combo * scoreMultiplier;
  simulation.elapsed += FIXED_STEP_SECONDS;
  simulation.speed = speedForElapsed(simulation.elapsed);
  processObstacles(simulation, travel, scoreMultiplier);
}

export function createSimulation(seed: SimulationSeed): GameSimulation {
  const normalized = normalizedSeed(seed);
  const simulation: GameSimulation = {
    seed: normalized,
    rngState: normalized,
    nextObstacleId: 1,
    player: {
      position: { x: 0, y: 0 },
      velocity: { x: 0, y: 0 },
      radius: PLAYER_RADIUS,
    },
    distance: 0,
    score: 0,
    integrity: INITIAL_INTEGRITY,
    combo: 1,
    phase: "ember",
    speed: INITIAL_SPEED,
    elapsed: 0,
    invulnerability: 0,
    phaseCooldown: 0,
    status: "running",
    obstacles: [],
    accumulator: 0,
    pendingPhaseToggle: false,
    nextPhraseId: 1,
    lastPhraseKind: null,
    phrasesSinceMovementCheck: 0,
    pendingPhrase: null,
    phraseProgress: [],
    activePhrase: null,
    phrasesCompleted: 0,
    cleanPhrases: 0,
    cleanPhraseStreak: 0,
    peakCleanPhraseStreak: 0,
    resonancePips: 0,
    resonanceRemaining: 0,
    resonanceActivations: 0,
    phraseEventSequence: 0,
    lastPhraseEvent: null,
  };
  fillObstaclePool(simulation);
  return simulation;
}

export function resetSimulation(seed: SimulationSeed): GameSimulation {
  return createSimulation(seed);
}

/**
 * Applies controls staged during a frozen launch or re-entry countdown without
 * moving the world. A promised phase shift must be visible before the first
 * live collision tick.
 */
export function commitPrimedInput(
  simulation: GameSimulation,
  phaseToggle: boolean,
): GameSimulation {
  const next = cloneSimulation(simulation);
  next.pendingPhaseToggle = false;
  next.phaseCooldown = 0;

  if (phaseToggle && next.status === "running") {
    next.phase = next.phase === "ember" ? "cobalt" : "ember";
    next.phaseCooldown = PHASE_TOGGLE_COOLDOWN_SECONDS;
  }

  return next;
}

export function stepSimulation(
  simulation: GameSimulation,
  input: InputState,
  deltaSeconds: number,
): GameSimulation {
  if (simulation.status === "crashed") {
    return cloneSimulation(simulation);
  }

  const pendingPhaseToggle = simulation.pendingPhaseToggle || input.phaseToggle;
  if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) {
    return pendingPhaseToggle === simulation.pendingPhaseToggle
      ? simulation
      : { ...simulation, pendingPhaseToggle };
  }

  const frameDelta = Math.min(deltaSeconds, MAX_FRAME_DELTA_SECONDS);
  const accumulator = simulation.accumulator + frameDelta;
  if (accumulator + EPSILON < FIXED_STEP_SECONDS) {
    return {
      ...simulation,
      accumulator,
      pendingPhaseToggle,
    };
  }

  const next = cloneSimulation(simulation);
  next.pendingPhaseToggle = pendingPhaseToggle;
  next.accumulator = accumulator;
  const movementInput = normalizedInput(input);

  while (next.accumulator + EPSILON >= FIXED_STEP_SECONDS && next.status === "running") {
    next.accumulator -= FIXED_STEP_SECONDS;
    if (Math.abs(next.accumulator) < EPSILON) {
      next.accumulator = 0;
    }
    fixedStep(next, movementInput);
  }

  if (next.integrity === 0) {
    next.accumulator = 0;
    next.pendingPhaseToggle = false;
  }
  return next;
}
