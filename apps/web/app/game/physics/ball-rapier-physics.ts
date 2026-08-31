import type {
  Collider,
  ColliderHandle,
  EventQueue,
  RigidBody,
  World,
} from '@dimforge/rapier3d-compat';
import {
  BALL_FIXED_STEP_SECONDS,
  BALL_OBSTACLE_POOL_SIZE,
  BALL_RADIUS,
  BALL_TUNNEL_RADIUS,
  ballImpactNormalForBlock,
  type BallGateEvent,
  type BallImpactEvent,
  type BallObstacle,
  type BallSimulation,
  type BallVector3,
} from '../ball-simulation';
import { loadRapier, type RapierApi } from './rapier-loader';

export const BALL_RAPIER_TOUCH_DEBRIS_CAP = 10;
export const BALL_RAPIER_DESKTOP_DEBRIS_CAP = 18;
export const BALL_RAPIER_GATE_SEGMENTS = 8;

const PLAYER_Z = 0;
const DISABLED_Z = -1_000;
const DEBRIS_MIN_LIFETIME_SECONDS = 2.1;
const DEBRIS_LIFETIME_VARIANCE_SECONDS = 1.15;
const DEBRIS_DESPAWN_DISTANCE = 170;

const LAYER_BALL = 1 << 0;
const LAYER_GATE = 1 << 1;
const LAYER_BLOCK = 1 << 2;
const LAYER_DEBRIS = 1 << 3;

const EMPTY_VECTOR = Object.freeze({ x: 0, y: 0, z: 0 });
const IDENTITY_ROTATION = Object.freeze({ x: 0, y: 0, z: 0, w: 1 });

export type BallRapierDebrisKind = 'impact' | 'gate' | 'overdrive';

export interface BallRapierQuaternion {
  x: number;
  y: number;
  z: number;
  w: number;
}

export interface BallRapierContact {
  obstacleId: string;
  poolSlot: number;
  kind: BallObstacle['kind'];
  normal: BallVector3;
  authoritativeHit: boolean;
  authoritativePassed: boolean;
}

export interface BallRapierFixedStepResult {
  contacts: readonly BallRapierContact[];
}

export interface BallRapierDebrisPose {
  id: number;
  kind: BallRapierDebrisKind;
  position: BallVector3;
  rotation: BallRapierQuaternion;
  sleeping: boolean;
}

export interface BallRapierDiagnostics {
  bodyCount: number;
  colliderCount: number;
  playerColliderRadius: number;
  hazardCapacity: number;
  activeHazards: number;
  gateSensorCapacity: number;
  activeGateSensors: number;
  blockColliderCapacity: number;
  activeBlockColliders: number;
  debrisCapacity: number;
  activeDebris: number;
  physicsSteps: number;
  timestep: number;
  paused: boolean;
  disposed: boolean;
}

export interface BallRapierPhysicsOptions {
  touchFirst: boolean;
}

type ColliderTag =
  | { role: 'ball' }
  | { role: 'gate'; slot: number; segment: number }
  | { role: 'block'; slot: number };

interface HazardSlot {
  body: RigidBody;
  blockCollider: Collider;
  gateColliders: Collider[];
  obstacleId: string | null;
  kind: BallObstacle['kind'] | null;
  enabled: boolean;
  gateOpeningRadius: number;
  gateHalfDepth: number;
  blockHalfWidth: number;
  blockHalfHeight: number;
  blockHalfDepth: number;
}

interface DebrisBody {
  id: number;
  body: RigidBody;
  active: boolean;
  expiresAt: number;
  kind: BallRapierDebrisKind;
}

function interactionGroups(membership: number, filter: number): number {
  return (((membership & 0xffff) << 16) | (filter & 0xffff)) >>> 0;
}

const BALL_GROUPS = interactionGroups(LAYER_BALL, LAYER_GATE | LAYER_BLOCK);
const GATE_GROUPS = interactionGroups(LAYER_GATE, LAYER_BALL);
const BLOCK_GROUPS = interactionGroups(LAYER_BLOCK, LAYER_BALL);
const DEBRIS_GROUPS = interactionGroups(LAYER_DEBRIS, 0);
const NO_SOLVER_GROUPS = interactionGroups(0, 0);

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function normalizedVector(vector: Readonly<BallVector3>): BallVector3 {
  const x = finite(vector.x);
  const y = finite(vector.y);
  const z = finite(vector.z);
  const length = Math.hypot(x, y, z);
  if (length < 1e-6) return { x: 0, y: 0, z: 1 };
  return {
    x: x === 0 ? 0 : x / length,
    y: y === 0 ? 0 : y / length,
    z: z === 0 ? 0 : z / length,
  };
}

function obstacleAtSlot(
  simulation: Readonly<BallSimulation>,
  slot: number,
): Readonly<BallObstacle> | undefined {
  const direct = simulation.obstacles[slot];
  if (direct?.poolSlot === slot) return direct;
  return simulation.obstacles.find((candidate) => candidate.poolSlot === slot);
}

/**
 * A bounded zero-gravity Rapier mirror for physical contacts and particles.
 * BallSimulation remains authoritative for position, shields, gate clearance,
 * score, Overdrive, crash state, and replay determinism.
 */
export class BallRapierPhysics {
  private readonly RAPIER: RapierApi;
  private readonly world: World;
  private readonly eventQueue: EventQueue;
  private readonly ballBody: RigidBody;
  private readonly hazardSlots: HazardSlot[];
  private readonly debris: DebrisBody[];
  private readonly colliderTags = new Map<ColliderHandle, ColliderTag>();
  private readonly debrisCapacity: number;

  private disposed = false;
  private paused = false;
  private physicsSteps = 0;
  private physicsTime = 0;
  private lastForwardSpeed = 0;
  private fxRngState = 0x6d2b79f5;
  private nextDebrisIndex = 0;

  static async create(options: BallRapierPhysicsOptions): Promise<BallRapierPhysics> {
    const RAPIER = await loadRapier();
    return new BallRapierPhysics(RAPIER, options);
  }

  private constructor(RAPIER: RapierApi, options: BallRapierPhysicsOptions) {
    this.RAPIER = RAPIER;
    this.debrisCapacity = options.touchFirst
      ? BALL_RAPIER_TOUCH_DEBRIS_CAP
      : BALL_RAPIER_DESKTOP_DEBRIS_CAP;
    this.world = new RAPIER.World({ x: 0, y: 0, z: 0 });
    this.world.timestep = BALL_FIXED_STEP_SECONDS;
    this.world.lengthUnit = 1;
    this.world.maxCcdSubsteps = 1;
    this.eventQueue = new RAPIER.EventQueue(true);

    this.ballBody = this.world.createRigidBody(
      RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, PLAYER_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    const ballCollider = this.world.createCollider(
      RAPIER.ColliderDesc.ball(BALL_RADIUS)
        .setSensor(true)
        .setCollisionGroups(BALL_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC),
      this.ballBody,
    );
    this.colliderTags.set(ballCollider.handle, { role: 'ball' });

    this.hazardSlots = Array.from(
      { length: BALL_OBSTACLE_POOL_SIZE },
      (_, slot) => this.createHazardSlot(slot),
    );
    this.debris = Array.from(
      { length: this.debrisCapacity },
      (_, id) => this.createDebrisBody(id),
    );
  }

  private createHazardSlot(slot: number): HazardSlot {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, DISABLED_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    const common = <T extends ReturnType<RapierApi['ColliderDesc']['cuboid']>>(
      descriptor: T,
    ): T => descriptor
      .setSensor(true)
      .setEnabled(false)
      .setSolverGroups(NO_SOLVER_GROUPS)
      .setActiveCollisionTypes(
        this.RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC,
      )
      .setActiveEvents(this.RAPIER.ActiveEvents.COLLISION_EVENTS) as T;

    const blockCollider = this.world.createCollider(
      common(this.RAPIER.ColliderDesc.cuboid(0.5, 0.5, 0.5))
        .setCollisionGroups(BLOCK_GROUPS),
      body,
    );
    this.colliderTags.set(blockCollider.handle, { role: 'block', slot });

    const gateColliders = Array.from(
      { length: BALL_RAPIER_GATE_SEGMENTS },
      (_, segment) => {
        const collider = this.world.createCollider(
          common(this.RAPIER.ColliderDesc.cuboid(0.5, 0.5, 0.5))
            .setCollisionGroups(GATE_GROUPS),
          body,
        );
        this.colliderTags.set(collider.handle, { role: 'gate', slot, segment });
        return collider;
      },
    );
    body.setEnabled(false);
    return {
      body,
      blockCollider,
      gateColliders,
      obstacleId: null,
      kind: null,
      enabled: false,
      gateOpeningRadius: Number.NaN,
      gateHalfDepth: Number.NaN,
      blockHalfWidth: Number.NaN,
      blockHalfHeight: Number.NaN,
      blockHalfDepth: Number.NaN,
    };
  }

  private createDebrisBody(id: number): DebrisBody {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.dynamic()
        .setTranslation(0, 0, DISABLED_Z)
        .setGravityScale(0)
        .setLinearDamping(1.7)
        .setAngularDamping(2.1)
        .setCanSleep(true)
        .setCcdEnabled(false),
    );
    this.world.createCollider(
      this.RAPIER.ColliderDesc.ball(0.085 + (id % 3) * 0.024)
        .setSensor(true)
        .setDensity(0.62)
        .setCollisionGroups(DEBRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS),
      body,
    );
    body.setEnabled(false);
    return { id, body, active: false, expiresAt: 0, kind: 'gate' };
  }

  private nextRandom(): number {
    let state = this.fxRngState >>> 0;
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    this.fxRngState = state >>> 0 || 0x6d2b79f5;
    return this.fxRngState / 0x100000000;
  }

  private configureGateColliders(
    slot: HazardSlot,
    openingRadius: number,
    halfDepth: number,
  ): void {
    if (
      slot.gateOpeningRadius === openingRadius &&
      slot.gateHalfDepth === halfDepth
    ) return;

    const safeOpening = clamp(openingRadius, BALL_RADIUS, BALL_TUNNEL_RADIUS - 0.2);
    const outerRadius = BALL_TUNNEL_RADIUS + BALL_RADIUS * 0.4;
    const radialHalf = Math.max(0.1, (outerRadius - safeOpening) / 2);
    const centerRadius = safeOpening + radialHalf;
    const tangentHalf = Math.max(
      0.18,
      Math.tan(Math.PI / BALL_RAPIER_GATE_SEGMENTS) * centerRadius * 1.12,
    );
    slot.gateColliders.forEach((collider, segment) => {
      const angle = (segment / BALL_RAPIER_GATE_SEGMENTS) * Math.PI * 2;
      collider.setHalfExtents({
        x: radialHalf,
        y: tangentHalf,
        z: halfDepth,
      });
      collider.setTranslationWrtParent({
        x: Math.cos(angle) * centerRadius,
        y: Math.sin(angle) * centerRadius,
        z: 0,
      });
      collider.setRotationWrtParent({
        x: 0,
        y: 0,
        z: Math.sin(angle / 2),
        w: Math.cos(angle / 2),
      });
    });
    slot.gateOpeningRadius = openingRadius;
    slot.gateHalfDepth = halfDepth;
  }

  private configureBlockCollider(
    slot: HazardSlot,
    halfWidth: number,
    halfHeight: number,
    halfDepth: number,
  ): void {
    if (
      slot.blockHalfWidth === halfWidth &&
      slot.blockHalfHeight === halfHeight &&
      slot.blockHalfDepth === halfDepth
    ) return;
    slot.blockCollider.setHalfExtents({
      x: halfWidth,
      y: halfHeight,
      z: halfDepth,
    });
    slot.blockHalfWidth = halfWidth;
    slot.blockHalfHeight = halfHeight;
    slot.blockHalfDepth = halfDepth;
  }

  private disableSlot(slot: HazardSlot): void {
    slot.blockCollider.setEnabled(false);
    slot.gateColliders.forEach((collider) => collider.setEnabled(false));
    slot.body.setEnabled(false);
    slot.obstacleId = null;
    slot.kind = null;
    slot.enabled = false;
  }

  private syncShadow(
    simulation: Readonly<BallSimulation>,
    teleportAll: boolean,
  ): void {
    const ballPosition = {
      x: finite(simulation.ball.position.x),
      y: finite(simulation.ball.position.y),
      z: PLAYER_Z,
    };
    let propagated = false;
    if (teleportAll) {
      this.ballBody.setTranslation(ballPosition, false);
      this.ballBody.setNextKinematicTranslation(ballPosition);
      propagated = true;
    } else {
      this.ballBody.setNextKinematicTranslation(ballPosition);
    }

    const enableAfterPropagation: Array<{
      slot: HazardSlot;
      kind: BallObstacle['kind'];
    }> = [];
    this.hazardSlots.forEach((slot, slotIndex) => {
      const obstacle = obstacleAtSlot(simulation, slotIndex);
      if (!obstacle?.active) {
        if (slot.enabled) this.disableSlot(slot);
        return;
      }

      const position = {
        x: finite(obstacle.x),
        y: finite(obstacle.y),
        z: finite(obstacle.z, DISABLED_Z),
      };
      const identityChanged =
        teleportAll ||
        !slot.enabled ||
        slot.obstacleId !== obstacle.id ||
        slot.kind !== obstacle.kind;
      slot.body.setEnabled(true);
      if (identityChanged) {
        slot.blockCollider.setEnabled(false);
        slot.gateColliders.forEach((collider) => collider.setEnabled(false));
        slot.body.setTranslation(position, false);
        slot.body.setNextKinematicTranslation(position);
        propagated = true;
      } else {
        slot.body.setNextKinematicTranslation(position);
      }

      if (obstacle.kind === 'gate') {
        this.configureGateColliders(
          slot,
          Math.max(BALL_RADIUS, finite(obstacle.openingRadius, 3)),
          Math.max(0.01, finite(obstacle.depth, 0.5) / 2),
        );
      } else {
        this.configureBlockCollider(
          slot,
          Math.max(0.01, finite(obstacle.width, 1) / 2),
          Math.max(0.01, finite(obstacle.height, 1) / 2),
          Math.max(0.01, finite(obstacle.depth, 1) / 2),
        );
      }

      slot.obstacleId = obstacle.id;
      slot.kind = obstacle.kind;
      slot.enabled = true;
      enableAfterPropagation.push({ slot, kind: obstacle.kind });
    });

    if (propagated) this.world.propagateModifiedBodyPositionsToColliders();
    enableAfterPropagation.forEach(({ slot, kind }) => {
      slot.blockCollider.setEnabled(kind === 'block');
      slot.gateColliders.forEach((collider) =>
        collider.setEnabled(kind === 'gate'),
      );
    });
  }

  private contactNormal(
    simulation: Readonly<BallSimulation>,
    obstacle: Readonly<BallObstacle>,
  ): BallVector3 {
    if (
      simulation.lastImpactEvent?.obstacleId === obstacle.id &&
      simulation.lastImpactEvent.sequence === simulation.impactEventSequence
    ) return { ...simulation.lastImpactEvent.normal };
    if (obstacle.kind === 'block') {
      return ballImpactNormalForBlock(simulation.ball, obstacle);
    }
    return normalizedVector({
      x: simulation.ball.position.x - obstacle.x,
      y: simulation.ball.position.y - obstacle.y,
      z: -obstacle.z + 0.08,
    });
  }

  private contactsForStep(
    simulation: Readonly<BallSimulation>,
  ): BallRapierFixedStepResult {
    const contacts = new Map<string, BallRapierContact>();
    this.eventQueue.drainCollisionEvents((handle1, handle2, started) => {
      if (!started) return;
      const first = this.colliderTags.get(handle1);
      const second = this.colliderTags.get(handle2);
      const ballPresent = first?.role === 'ball' || second?.role === 'ball';
      const hazard = first?.role === 'gate' || first?.role === 'block'
        ? first
        : second?.role === 'gate' || second?.role === 'block'
          ? second
          : null;
      if (!ballPresent || !hazard) return;
      const slot = this.hazardSlots[hazard.slot];
      if (!slot?.enabled || slot.kind !== hazard.role || !slot.obstacleId) return;
      const obstacle = obstacleAtSlot(simulation, hazard.slot);
      if (
        !obstacle?.active ||
        obstacle.id !== slot.obstacleId ||
        obstacle.kind !== hazard.role
      ) return;
      const key = `${obstacle.poolSlot}:${obstacle.id}`;
      contacts.set(key, {
        obstacleId: obstacle.id,
        poolSlot: obstacle.poolSlot,
        kind: obstacle.kind,
        normal: this.contactNormal(simulation, obstacle),
        authoritativeHit: obstacle.hit,
        authoritativePassed: obstacle.passed,
      });
    });
    return {
      contacts: [...contacts.values()].sort(
        (left, right) =>
          left.poolSlot - right.poolSlot ||
          left.obstacleId.localeCompare(right.obstacleId),
      ),
    };
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
      ) this.deactivateDebris(piece);
    });
  }

  private activateDebris(
    kind: BallRapierDebrisKind,
    position: Readonly<BallVector3>,
    direction: Readonly<BallVector3>,
    strength: number,
  ): void {
    const piece = this.debris[this.nextDebrisIndex % this.debris.length];
    this.nextDebrisIndex = (this.nextDebrisIndex + 1) % this.debris.length;
    const safePosition = {
      x: finite(position.x) + (this.nextRandom() - 0.5) * 0.32,
      y: finite(position.y) + (this.nextRandom() - 0.5) * 0.32,
      z: finite(position.z) + (this.nextRandom() - 0.5) * 0.24,
    };
    const launchDirection = normalizedVector(direction);
    const launchSpeed = (4.6 + this.nextRandom() * 4.8) * strength;
    const tangentX = (this.nextRandom() - 0.5) * 4.8;
    const tangentY = (this.nextRandom() - 0.5) * 4.8;
    const tangentZ = (this.nextRandom() - 0.5) * 2.4;

    piece.body.setEnabled(true);
    piece.body.setTranslation(safePosition, true);
    piece.body.setRotation(IDENTITY_ROTATION, true);
    piece.body.setLinvel({ x: 0, y: 0, z: this.lastForwardSpeed * 0.1 }, true);
    piece.body.setAngvel({
      x: (this.nextRandom() - 0.5) * 16,
      y: (this.nextRandom() - 0.5) * 16,
      z: (this.nextRandom() - 0.5) * 16,
    }, true);
    const mass = Math.max(0.0001, piece.body.mass());
    piece.body.applyImpulse({
      x: mass * (launchDirection.x * launchSpeed + tangentX),
      y: mass * (launchDirection.y * launchSpeed + tangentY),
      z: mass * (launchDirection.z * launchSpeed + tangentZ),
    }, true);
    piece.kind = kind;
    piece.active = true;
    piece.expiresAt = this.physicsTime +
      DEBRIS_MIN_LIFETIME_SECONDS +
      this.nextRandom() * DEBRIS_LIFETIME_VARIANCE_SECONDS;
  }

  reset(simulation: Readonly<BallSimulation>): void {
    if (this.disposed) return;
    this.paused = false;
    this.physicsSteps = 0;
    this.physicsTime = 0;
    this.lastForwardSpeed = finite(simulation.speed);
    this.fxRngState = ((simulation.seed >>> 0) ^ 0xc8013ea4) || 0x6d2b79f5;
    this.nextDebrisIndex = 0;
    this.eventQueue.clear();
    this.debris.forEach((piece) => this.deactivateDebris(piece));
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
  }

  fixedStep(
    simulation: Readonly<BallSimulation>,
  ): BallRapierFixedStepResult {
    if (this.disposed || this.paused) return { contacts: [] };
    this.world.timestep = BALL_FIXED_STEP_SECONDS;
    this.lastForwardSpeed = finite(simulation.speed);
    this.syncShadow(simulation, false);
    this.physicsTime += BALL_FIXED_STEP_SECONDS;
    this.expireDebris();
    this.world.step(this.eventQueue);
    this.physicsSteps += 1;
    return this.contactsForStep(simulation);
  }

  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
    this.eventQueue.clear();
  }

  resume(simulation: Readonly<BallSimulation>): void {
    if (this.disposed) return;
    this.eventQueue.clear();
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
    this.paused = false;
  }

  emitImpact(event: Readonly<BallImpactEvent>, strength = 1): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 5 : 7);
    const safeStrength = clamp(finite(strength, 1), 0.3, 3);
    for (let index = 0; index < count; index += 1) {
      this.activateDebris('impact', event.position, event.normal, safeStrength);
    }
  }

  emitGate(event: Readonly<BallGateEvent>, strength = 1): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    const count = Math.min(
      this.debris.length,
      this.debrisCapacity <= 10 ? (event.nearMiss ? 4 : 3) : (event.nearMiss ? 6 : 4),
    );
    const safeStrength = clamp(finite(strength, 1), 0.2, 2) *
      (event.nearMiss ? 0.85 : 0.64);
    for (let index = 0; index < count; index += 1) {
      const angle = (index / Math.max(1, count)) * Math.PI * 2;
      this.activateDebris(
        'gate',
        event.position,
        { x: Math.cos(angle), y: Math.sin(angle), z: 0.2 },
        safeStrength,
      );
    }
  }

  emitOverdrive(position: Readonly<BallVector3>): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    if (!this.debris.some((piece) => piece.active)) {
      const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 6 : 9);
      for (let index = 0; index < count; index += 1) {
        const angle = (index / count) * Math.PI * 2;
        this.activateDebris(
          'overdrive',
          {
            x: finite(position.x) + Math.cos(angle) * 0.5,
            y: finite(position.y) + Math.sin(angle) * 0.5,
            z: finite(position.z),
          },
          { x: Math.cos(angle), y: Math.sin(angle), z: 0.24 },
          0.72,
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
      const impulseSpeed = clamp(8.5 - distance * 0.35, 2.8, 8.5);
      const mass = Math.max(0.0001, piece.body.mass());
      piece.body.applyImpulse({
        x: radial.x * mass * impulseSpeed,
        y: radial.y * mass * impulseSpeed,
        z: radial.z * mass * impulseSpeed,
      }, true);
      piece.kind = 'overdrive';
      piece.expiresAt = Math.max(piece.expiresAt, this.physicsTime + 2.5);
    });
  }

  forEachActiveDebrisPose(
    callback: (pose: Readonly<BallRapierDebrisPose>) => void,
  ): void {
    if (this.disposed) return;
    this.debris.forEach((piece) => {
      if (!piece.active) return;
      const position = piece.body.translation();
      const rotation = piece.body.rotation();
      callback({
        id: piece.id,
        kind: piece.kind,
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

  getDiagnostics(): BallRapierDiagnostics {
    const activeHazards = this.hazardSlots.reduce(
      (count, slot) => count + Number(slot.enabled),
      0,
    );
    const activeGateSensors = this.hazardSlots.reduce(
      (count, slot) => count + (slot.enabled && slot.kind === 'gate'
        ? BALL_RAPIER_GATE_SEGMENTS
        : 0),
      0,
    );
    const activeBlockColliders = this.hazardSlots.reduce(
      (count, slot) => count + Number(slot.enabled && slot.kind === 'block'),
      0,
    );
    const activeDebris = this.debris.reduce(
      (count, piece) => count + Number(piece.active),
      0,
    );
    return {
      bodyCount: this.disposed ? 0 : this.world.bodies.len(),
      colliderCount: this.disposed ? 0 : this.world.colliders.len(),
      playerColliderRadius: BALL_RADIUS,
      hazardCapacity: BALL_OBSTACLE_POOL_SIZE,
      activeHazards,
      gateSensorCapacity: BALL_OBSTACLE_POOL_SIZE * BALL_RAPIER_GATE_SEGMENTS,
      activeGateSensors,
      blockColliderCapacity: BALL_OBSTACLE_POOL_SIZE,
      activeBlockColliders,
      debrisCapacity: this.debrisCapacity,
      activeDebris,
      physicsSteps: this.physicsSteps,
      timestep: BALL_FIXED_STEP_SECONDS,
      paused: this.paused,
      disposed: this.disposed,
    };
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.paused = true;
    this.colliderTags.clear();
    this.hazardSlots.length = 0;
    this.debris.length = 0;
    this.eventQueue.free();
    this.world.free();
  }
}
