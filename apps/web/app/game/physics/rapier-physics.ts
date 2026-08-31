import type {
  Collider,
  ColliderHandle,
  EventQueue,
  RigidBody,
  World,
} from '@dimforge/rapier3d-compat';
import {
  FIXED_STEP_SECONDS,
  TUNNEL_RADIUS,
  type GameObstacle,
  type GamePhase,
  type GameSimulation,
} from '../simulation';
import { loadRapier, type RapierApi } from './rapier-loader';

export const RAPIER_HAZARD_POOL_SIZE = 8;
export const RAPIER_TOUCH_DEBRIS_CAP = 10;
export const RAPIER_DESKTOP_DEBRIS_CAP = 18;

const PLAYER_Z = 0;
const DISABLED_Z = -1_000;
const DEBRIS_MIN_LIFETIME_SECONDS = 2.2;
const DEBRIS_LIFETIME_VARIANCE_SECONDS = 1.2;
const DEBRIS_DESPAWN_DISTANCE = 170;

const LAYER_PLAYER_EMBER = 1 << 0;
const LAYER_PLAYER_COBALT = 1 << 1;
const LAYER_BLOCK = 1 << 2;
const LAYER_MEMBRANE_EMBER = 1 << 3;
const LAYER_MEMBRANE_COBALT = 1 << 4;
const LAYER_FX_DEBRIS = 1 << 5;

const EMPTY_VECTOR = Object.freeze({ x: 0, y: 0, z: 0 });
const IDENTITY_ROTATION = Object.freeze({ x: 0, y: 0, z: 0, w: 1 });
const QUARTER_TURN_X = Object.freeze({
  x: Math.SQRT1_2,
  y: 0,
  z: 0,
  w: Math.SQRT1_2,
});

export interface RapierVector3 {
  x: number;
  y: number;
  z: number;
}

export interface RapierQuaternion {
  x: number;
  y: number;
  z: number;
  w: number;
}

export interface RapierShadowContact {
  obstacleId: string;
  poolSlot: number;
  kind: GameObstacle['kind'];
  normal: RapierVector3;
  /**
   * Rapier never decides damage. This reports the authoritative simulation's
   * state so a renderer can ignore an earlier, more generous shadow contact.
   */
  authoritativeHit: boolean;
}

export interface RapierFixedStepResult {
  contacts: readonly RapierShadowContact[];
}

export interface RapierDebrisPose {
  id: number;
  position: RapierVector3;
  rotation: RapierQuaternion;
  sleeping: boolean;
}

export interface RapierPhysicsDiagnostics {
  bodyCount: number;
  colliderCount: number;
  hazardCapacity: number;
  debrisCapacity: number;
  activeDebris: number;
  physicsSteps: number;
  timestep: number;
  paused: boolean;
  disposed: boolean;
}

export interface SignalRunRapierPhysicsOptions {
  touchFirst: boolean;
}

type ColliderTag =
  | { role: 'player' }
  | { role: 'hazard'; slot: number; kind: GameObstacle['kind'] };

interface HazardSlot {
  body: RigidBody;
  blockCollider: Collider;
  membraneCollider: Collider;
  obstacleId: string | null;
  kind: GameObstacle['kind'] | null;
  enabled: boolean;
  blockHalfWidth: number;
  blockHalfHeight: number;
  blockHalfDepth: number;
  membraneRadius: number;
  membraneHalfDepth: number;
  membranePhase: GamePhase | null;
}

interface DebrisBody {
  id: number;
  body: RigidBody;
  active: boolean;
  expiresAt: number;
}

function interactionGroups(membership: number, filter: number): number {
  return (((membership & 0xffff) << 16) | (filter & 0xffff)) >>> 0;
}

const PLAYER_EMBER_GROUPS = interactionGroups(
  LAYER_PLAYER_EMBER,
  LAYER_BLOCK | LAYER_MEMBRANE_COBALT,
);
const PLAYER_COBALT_GROUPS = interactionGroups(
  LAYER_PLAYER_COBALT,
  LAYER_BLOCK | LAYER_MEMBRANE_EMBER,
);
const BLOCK_GROUPS = interactionGroups(
  LAYER_BLOCK,
  LAYER_PLAYER_EMBER | LAYER_PLAYER_COBALT,
);
const MEMBRANE_EMBER_GROUPS = interactionGroups(
  LAYER_MEMBRANE_EMBER,
  LAYER_PLAYER_COBALT,
);
const MEMBRANE_COBALT_GROUPS = interactionGroups(
  LAYER_MEMBRANE_COBALT,
  LAYER_PLAYER_EMBER,
);
const DEBRIS_GROUPS = interactionGroups(LAYER_FX_DEBRIS, 0);
const NO_SOLVER_GROUPS = interactionGroups(0, 0);

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function normalizedVector(vector: RapierVector3): RapierVector3 {
  const x = finite(vector.x);
  const y = finite(vector.y);
  const z = finite(vector.z);
  const length = Math.hypot(x, y, z);
  if (length < 1e-6) return { x: 0, y: 0, z: 1 };
  return { x: x / length, y: y / length, z: z / length };
}

function phasePlayerGroups(phase: GamePhase): number {
  return phase === 'ember' ? PLAYER_EMBER_GROUPS : PLAYER_COBALT_GROUPS;
}

function phaseMembraneGroups(phase: GamePhase): number {
  return phase === 'ember' ? MEMBRANE_EMBER_GROUPS : MEMBRANE_COBALT_GROUPS;
}

function shadowNormal(
  simulation: Readonly<GameSimulation>,
  obstacle: Readonly<GameObstacle>,
): RapierVector3 {
  if (obstacle.kind === 'membrane') {
    return { x: 0, y: 0, z: obstacle.z <= PLAYER_Z ? 1 : -1 };
  }

  const halfWidth = obstacle.width / 2;
  const halfHeight = obstacle.height / 2;
  const halfDepth = obstacle.depth / 2;
  const playerX = simulation.player.position.x;
  const playerY = simulation.player.position.y;
  const closestX = clamp(playerX, obstacle.x - halfWidth, obstacle.x + halfWidth);
  const closestY = clamp(playerY, obstacle.y - halfHeight, obstacle.y + halfHeight);
  const closestZ = clamp(PLAYER_Z, obstacle.z - halfDepth, obstacle.z + halfDepth);
  const normal = {
    x: playerX - closestX,
    y: playerY - closestY,
    z: PLAYER_Z - closestZ,
  };
  if (Math.hypot(normal.x, normal.y, normal.z) >= 1e-6) {
    return normalizedVector(normal);
  }

  const localX = playerX - obstacle.x;
  const localY = playerY - obstacle.y;
  const localZ = PLAYER_Z - obstacle.z;
  const faceDistances = [
    { distance: halfWidth - Math.abs(localX), normal: { x: localX >= 0 ? 1 : -1, y: 0, z: 0 } },
    { distance: halfHeight - Math.abs(localY), normal: { x: 0, y: localY >= 0 ? 1 : -1, z: 0 } },
    { distance: halfDepth - Math.abs(localZ), normal: { x: 0, y: 0, z: localZ >= 0 ? 1 : -1 } },
  ];
  faceDistances.sort((left, right) => left.distance - right.distance);
  return faceDistances[0]?.normal ?? { x: 0, y: 0, z: 1 };
}

/**
 * A bounded Rapier sidecar for contact metadata and physical presentation.
 * The supplied GameSimulation remains the only authority for movement, hits,
 * passes, phase rules, score, and replay fairness.
 */
export class SignalRunRapierPhysics {
  private readonly RAPIER: RapierApi;
  private readonly world: World;
  private readonly eventQueue: EventQueue;
  private readonly playerBody: RigidBody;
  private readonly playerColliders: Collider[];
  private readonly hazardSlots: HazardSlot[];
  private readonly debris: DebrisBody[];
  private readonly colliderTags = new Map<ColliderHandle, ColliderTag>();
  private readonly debrisCapacity: number;

  private disposed = false;
  private paused = false;
  private physicsSteps = 0;
  private physicsTime = 0;
  private lastSpeed = 0;
  private fxRngState = 0x6d2b79f5;
  private nextDebrisIndex = 0;
  private playerPhase: GamePhase | null = null;

  static async create(
    options: SignalRunRapierPhysicsOptions,
  ): Promise<SignalRunRapierPhysics> {
    const RAPIER = await loadRapier();
    return new SignalRunRapierPhysics(RAPIER, options);
  }

  private constructor(
    RAPIER: RapierApi,
    options: SignalRunRapierPhysicsOptions,
  ) {
    this.RAPIER = RAPIER;
    this.debrisCapacity = options.touchFirst
      ? RAPIER_TOUCH_DEBRIS_CAP
      : RAPIER_DESKTOP_DEBRIS_CAP;
    this.world = new RAPIER.World({ x: 0, y: 0, z: 0 });
    this.world.timestep = FIXED_STEP_SECONDS;
    this.world.lengthUnit = 1;
    this.world.maxCcdSubsteps = 1;
    this.eventQueue = new RAPIER.EventQueue(true);

    this.playerBody = this.world.createRigidBody(
      RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, PLAYER_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    this.playerColliders = this.createPlayerColliders();
    this.hazardSlots = Array.from(
      { length: RAPIER_HAZARD_POOL_SIZE },
      (_, slot) => this.createHazardSlot(slot),
    );
    this.debris = Array.from(
      { length: this.debrisCapacity },
      (_, id) => this.createDebrisBody(id),
    );
  }

  private createPlayerColliders(): Collider[] {
    const activeCollisionTypes = this.RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC;
    const common = <T extends ReturnType<RapierApi['ColliderDesc']['cuboid']>>(descriptor: T): T =>
      descriptor
        .setCollisionGroups(PLAYER_EMBER_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes) as T;

    const fuselage = this.world.createCollider(
      common(
        this.RAPIER.ColliderDesc.capsule(1, 0.55).setRotation(QUARTER_TURN_X),
      ),
      this.playerBody,
    );
    const wing = this.world.createCollider(
      common(this.RAPIER.ColliderDesc.cuboid(1.65, 0.18, 0.42)),
      this.playerBody,
    );
    const fin = this.world.createCollider(
      common(this.RAPIER.ColliderDesc.cuboid(0.18, 0.82, 0.36)),
      this.playerBody,
    );
    const colliders = [fuselage, wing, fin];
    colliders.forEach((collider) => {
      this.colliderTags.set(collider.handle, { role: 'player' });
    });
    return colliders;
  }

  private createHazardSlot(slot: number): HazardSlot {
    const activeCollisionTypes = this.RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC;
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, DISABLED_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    const blockCollider = this.world.createCollider(
      this.RAPIER.ColliderDesc.cuboid(0.5, 0.5, 0.5)
        .setEnabled(false)
        .setCollisionGroups(BLOCK_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes)
        .setActiveEvents(this.RAPIER.ActiveEvents.COLLISION_EVENTS),
      body,
    );
    const membraneCollider = this.world.createCollider(
      this.RAPIER.ColliderDesc.cylinder(0.2, TUNNEL_RADIUS)
        .setRotation(QUARTER_TURN_X)
        .setSensor(true)
        .setEnabled(false)
        .setCollisionGroups(MEMBRANE_EMBER_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes)
        .setActiveEvents(this.RAPIER.ActiveEvents.COLLISION_EVENTS),
      body,
    );
    body.setEnabled(false);
    this.colliderTags.set(blockCollider.handle, { role: 'hazard', slot, kind: 'block' });
    this.colliderTags.set(membraneCollider.handle, {
      role: 'hazard',
      slot,
      kind: 'membrane',
    });
    return {
      body,
      blockCollider,
      membraneCollider,
      obstacleId: null,
      kind: null,
      enabled: false,
      blockHalfWidth: Number.NaN,
      blockHalfHeight: Number.NaN,
      blockHalfDepth: Number.NaN,
      membraneRadius: Number.NaN,
      membraneHalfDepth: Number.NaN,
      membranePhase: null,
    };
  }

  private createDebrisBody(id: number): DebrisBody {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.dynamic()
        .setTranslation(0, 0, DISABLED_Z)
        .setGravityScale(0)
        .setLinearDamping(1.8)
        .setAngularDamping(2.2)
        .setCanSleep(true)
        .setCcdEnabled(false),
    );
    this.world.createCollider(
      this.RAPIER.ColliderDesc.ball(0.095 + (id % 3) * 0.025)
        .setSensor(true)
        .setDensity(0.65)
        .setCollisionGroups(DEBRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS),
      body,
    );
    body.setEnabled(false);
    return { id, body, active: false, expiresAt: 0 };
  }

  private nextRandom(): number {
    let state = this.fxRngState >>> 0;
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    this.fxRngState = state >>> 0 || 0x6d2b79f5;
    return this.fxRngState / 0x100000000;
  }

  private configurePlayer(phase: GamePhase): void {
    if (this.playerPhase === phase) return;
    const groups = phasePlayerGroups(phase);
    this.playerColliders.forEach((collider) => collider.setCollisionGroups(groups));
    this.playerPhase = phase;
  }

  private syncShadow(
    simulation: Readonly<GameSimulation>,
    teleportAll: boolean,
  ): void {
    this.configurePlayer(simulation.phase);
    const playerPosition = {
      x: finite(simulation.player.position.x),
      y: finite(simulation.player.position.y),
      z: PLAYER_Z,
    };
    let propagated = false;
    if (teleportAll) {
      this.playerBody.setTranslation(playerPosition, false);
      this.playerBody.setNextKinematicTranslation(playerPosition);
      propagated = true;
    } else {
      this.playerBody.setNextKinematicTranslation(playerPosition);
    }

    const obstacleBySlot = new Map<number, Readonly<GameObstacle>>();
    simulation.obstacles.forEach((obstacle) => {
      if (
        Number.isInteger(obstacle.poolSlot) &&
        obstacle.poolSlot >= 0 &&
        obstacle.poolSlot < RAPIER_HAZARD_POOL_SIZE &&
        !obstacleBySlot.has(obstacle.poolSlot)
      ) {
        obstacleBySlot.set(obstacle.poolSlot, obstacle);
      }
    });

    const enableAfterPropagation: Array<{
      slot: HazardSlot;
      kind: GameObstacle['kind'];
    }> = [];

    this.hazardSlots.forEach((slot, slotIndex) => {
      const obstacle = obstacleBySlot.get(slotIndex);
      if (!obstacle) {
        slot.blockCollider.setEnabled(false);
        slot.membraneCollider.setEnabled(false);
        slot.body.setEnabled(false);
        slot.obstacleId = null;
        slot.kind = null;
        slot.enabled = false;
        return;
      }

      const bodyPosition = {
        x: finite(obstacle.x),
        y: finite(obstacle.y),
        z: finite(obstacle.z, DISABLED_Z),
      };
      const identityChanged =
        teleportAll ||
        slot.obstacleId !== obstacle.id ||
        slot.kind !== obstacle.kind ||
        !slot.enabled;

      slot.body.setEnabled(true);
      if (identityChanged) {
        // Disable before teleporting a recycled pool slot. Otherwise Rapier can
        // infer an enormous kinematic velocity from the old near-player body.
        slot.blockCollider.setEnabled(false);
        slot.membraneCollider.setEnabled(false);
        slot.body.setTranslation(bodyPosition, false);
        slot.body.setNextKinematicTranslation(bodyPosition);
        propagated = true;
      } else {
        slot.body.setNextKinematicTranslation(bodyPosition);
      }

      if (obstacle.kind === 'block') {
        const halfWidth = Math.max(0.01, finite(obstacle.width, 1) / 2);
        const halfHeight = Math.max(0.01, finite(obstacle.height, 1) / 2);
        const halfDepth = Math.max(0.01, finite(obstacle.depth, 1) / 2);
        if (
          slot.blockHalfWidth !== halfWidth ||
          slot.blockHalfHeight !== halfHeight ||
          slot.blockHalfDepth !== halfDepth
        ) {
          slot.blockCollider.setHalfExtents({
            x: halfWidth,
            y: halfHeight,
            z: halfDepth,
          });
          slot.blockHalfWidth = halfWidth;
          slot.blockHalfHeight = halfHeight;
          slot.blockHalfDepth = halfDepth;
        }
      } else {
        const radius = Math.max(
          0.01,
          finite(obstacle.radius, TUNNEL_RADIUS),
        );
        const halfDepth = Math.max(0.01, finite(obstacle.depth, 0.4) / 2);
        if (slot.membraneRadius !== radius) {
          slot.membraneCollider.setRadius(radius);
          slot.membraneRadius = radius;
        }
        if (slot.membraneHalfDepth !== halfDepth) {
          slot.membraneCollider.setHalfHeight(halfDepth);
          slot.membraneHalfDepth = halfDepth;
        }
        if (slot.membranePhase !== obstacle.phase) {
          slot.membraneCollider.setCollisionGroups(
            phaseMembraneGroups(obstacle.phase),
          );
          slot.membranePhase = obstacle.phase;
        }
      }

      slot.obstacleId = obstacle.id;
      slot.kind = obstacle.kind;
      slot.enabled = true;
      enableAfterPropagation.push({ slot, kind: obstacle.kind });
    });

    if (propagated) this.world.propagateModifiedBodyPositionsToColliders();
    enableAfterPropagation.forEach(({ slot, kind }) => {
      slot.blockCollider.setEnabled(kind === 'block');
      slot.membraneCollider.setEnabled(kind === 'membrane');
    });
  }

  private contactsForStep(
    simulation: Readonly<GameSimulation>,
  ): RapierShadowContact[] {
    const contacts = new Map<string, RapierShadowContact>();
    this.eventQueue.drainCollisionEvents((handle1, handle2, started) => {
      if (!started) return;
      const first = this.colliderTags.get(handle1);
      const second = this.colliderTags.get(handle2);
      const hazard = first?.role === 'hazard'
        ? first
        : second?.role === 'hazard'
          ? second
          : null;
      const playerPresent = first?.role === 'player' || second?.role === 'player';
      if (!hazard || !playerPresent) return;

      const slot = this.hazardSlots[hazard.slot];
      if (!slot?.enabled || slot.kind !== hazard.kind || !slot.obstacleId) return;
      const obstacle = simulation.obstacles.find(
        (candidate) =>
          candidate.poolSlot === hazard.slot &&
          candidate.id === slot.obstacleId &&
          candidate.kind === hazard.kind,
      );
      if (!obstacle) return;
      const key = `${obstacle.id}:${obstacle.kind}`;
      contacts.set(key, {
        obstacleId: obstacle.id,
        poolSlot: obstacle.poolSlot,
        kind: obstacle.kind,
        normal: shadowNormal(simulation, obstacle),
        authoritativeHit: obstacle.hit,
      });
    });
    return [...contacts.values()].sort((left, right) =>
      left.poolSlot - right.poolSlot || left.obstacleId.localeCompare(right.obstacleId),
    );
  }

  private deactivateDebris(piece: DebrisBody): void {
    piece.active = false;
    piece.expiresAt = 0;
    piece.body.setLinvel(EMPTY_VECTOR, false);
    piece.body.setAngvel(EMPTY_VECTOR, false);
    piece.body.setEnabled(false);
  }

  private expireDebris(): void {
    this.debris.forEach((piece) => {
      if (!piece.active) return;
      const position = piece.body.translation();
      if (
        this.physicsTime >= piece.expiresAt ||
        Math.hypot(position.x, position.y, position.z) > DEBRIS_DESPAWN_DISTANCE
      ) {
        this.deactivateDebris(piece);
      }
    });
  }

  private activateDebris(
    position: Readonly<RapierVector3>,
    direction: Readonly<RapierVector3>,
    strength: number,
  ): DebrisBody {
    const piece = this.debris[this.nextDebrisIndex % this.debris.length];
    this.nextDebrisIndex = (this.nextDebrisIndex + 1) % this.debris.length;
    const safePosition = {
      x: finite(position.x) + (this.nextRandom() - 0.5) * 0.32,
      y: finite(position.y) + (this.nextRandom() - 0.5) * 0.32,
      z: finite(position.z) + (this.nextRandom() - 0.5) * 0.24,
    };
    const normal = normalizedVector({ ...direction });
    const tangentX = (this.nextRandom() - 0.5) * 5;
    const tangentY = (this.nextRandom() - 0.5) * 5;
    const tangentZ = (this.nextRandom() - 0.5) * 2.4;
    const launchSpeed = (4.8 + this.nextRandom() * 4.2) * strength;

    piece.body.setEnabled(true);
    piece.body.setTranslation(safePosition, true);
    piece.body.setRotation(IDENTITY_ROTATION, true);
    piece.body.setLinvel({ x: 0, y: 0, z: this.lastSpeed * 0.12 }, true);
    piece.body.setAngvel(
      {
        x: (this.nextRandom() - 0.5) * 15,
        y: (this.nextRandom() - 0.5) * 15,
        z: (this.nextRandom() - 0.5) * 15,
      },
      true,
    );
    const mass = Math.max(0.0001, piece.body.mass());
    piece.body.applyImpulse(
      {
        x: mass * (normal.x * launchSpeed + tangentX),
        y: mass * (normal.y * launchSpeed + tangentY),
        z: mass * (normal.z * launchSpeed + tangentZ),
      },
      true,
    );
    piece.active = true;
    piece.expiresAt =
      this.physicsTime +
      DEBRIS_MIN_LIFETIME_SECONDS +
      this.nextRandom() * DEBRIS_LIFETIME_VARIANCE_SECONDS;
    return piece;
  }

  reset(simulation: Readonly<GameSimulation>): void {
    if (this.disposed) return;
    this.paused = false;
    this.physicsSteps = 0;
    this.physicsTime = 0;
    this.lastSpeed = finite(simulation.speed);
    this.fxRngState = ((simulation.seed >>> 0) ^ 0xa341316c) || 0x6d2b79f5;
    this.nextDebrisIndex = 0;
    this.playerPhase = null;
    this.eventQueue.clear();
    this.debris.forEach((piece) => this.deactivateDebris(piece));
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
  }

  fixedStep(
    simulation: Readonly<GameSimulation>,
  ): RapierFixedStepResult {
    if (this.disposed || this.paused) return { contacts: [] };
    this.world.timestep = FIXED_STEP_SECONDS;
    this.lastSpeed = finite(simulation.speed);
    this.syncShadow(simulation, false);
    this.physicsTime += FIXED_STEP_SECONDS;
    this.expireDebris();
    this.world.step(this.eventQueue);
    this.physicsSteps += 1;
    return { contacts: this.contactsForStep(simulation) };
  }

  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
    this.eventQueue.clear();
  }

  resume(simulation: Readonly<GameSimulation>): void {
    if (this.disposed) return;
    this.eventQueue.clear();
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
    this.paused = false;
  }

  emitImpact(
    position: Readonly<RapierVector3>,
    normal: Readonly<RapierVector3>,
    strength = 1,
  ): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    const safeStrength = clamp(finite(strength, 1), 0.25, 3);
    const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 4 : 6);
    for (let index = 0; index < count; index += 1) {
      this.activateDebris(position, normal, safeStrength);
    }
  }

  emitResonance(position: Readonly<RapierVector3>): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    if (!this.debris.some((piece) => piece.active)) {
      const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 6 : 9);
      for (let index = 0; index < count; index += 1) {
        const angle = (index / count) * Math.PI * 2;
        this.activateDebris(
          {
            x: finite(position.x) + Math.cos(angle) * 0.5,
            y: finite(position.y) + Math.sin(angle) * 0.5,
            z: finite(position.z),
          },
          { x: Math.cos(angle), y: Math.sin(angle), z: 0.2 },
          0.65,
        );
      }
    }

    this.debris.forEach((piece) => {
      if (!piece.active) return;
      const current = piece.body.translation();
      const radial = normalizedVector({
        x: current.x - finite(position.x),
        y: current.y - finite(position.y),
        z: current.z - finite(position.z) + 0.12,
      });
      const distance = Math.hypot(
        current.x - finite(position.x),
        current.y - finite(position.y),
        current.z - finite(position.z),
      );
      const impulseSpeed = clamp(8 - distance * 0.35, 2.5, 8);
      const mass = Math.max(0.0001, piece.body.mass());
      piece.body.applyImpulse(
        {
          x: radial.x * mass * impulseSpeed,
          y: radial.y * mass * impulseSpeed,
          z: radial.z * mass * impulseSpeed,
        },
        true,
      );
      piece.expiresAt = Math.max(piece.expiresAt, this.physicsTime + 2.4);
    });
  }

  forEachActiveDebrisPose(
    callback: (pose: Readonly<RapierDebrisPose>) => void,
  ): void {
    if (this.disposed) return;
    this.debris.forEach((piece) => {
      if (!piece.active) return;
      const position = piece.body.translation();
      const rotation = piece.body.rotation();
      callback({
        id: piece.id,
        position: { x: position.x, y: position.y, z: position.z },
        rotation: {
          x: rotation.x,
          y: rotation.y,
          z: rotation.z,
          w: rotation.w,
        },
        sleeping: piece.body.isSleeping(),
      });
    });
  }

  getDiagnostics(): RapierPhysicsDiagnostics {
    const activeDebris = this.debris.reduce(
      (count, piece) => count + Number(piece.active),
      0,
    );
    return {
      bodyCount: this.disposed ? 0 : this.world.bodies.len(),
      colliderCount: this.disposed ? 0 : this.world.colliders.len(),
      hazardCapacity: RAPIER_HAZARD_POOL_SIZE,
      debrisCapacity: this.debrisCapacity,
      activeDebris,
      physicsSteps: this.physicsSteps,
      timestep: FIXED_STEP_SECONDS,
      paused: this.paused,
      disposed: this.disposed,
    };
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.paused = true;
    this.colliderTags.clear();
    this.playerColliders.length = 0;
    this.hazardSlots.length = 0;
    this.debris.length = 0;
    this.eventQueue.free();
    this.world.free();
  }
}
