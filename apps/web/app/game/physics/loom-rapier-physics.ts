import type {
  Collider,
  ColliderHandle,
  EventQueue,
  RigidBody,
  World,
} from '@dimforge/rapier3d-compat';
import {
  LOOM_ANCHOR_POOL_SIZE,
  LOOM_FIXED_STEP_SECONDS,
  LOOM_FLIGHT_BOUNDARY,
  LOOM_IRIS_BLADE_COUNT,
  LOOM_IRIS_ECHO_RADIUS,
  LOOM_IRIS_NEEDLE_RADIUS,
  LOOM_IRIS_THREAD_RADIUS,
  type LoomAnchor,
  type LoomAnchorRoute,
  type LoomIrisOutcome,
  type LoomIrisStage,
  type LoomPhase,
  type LoomSimulation,
} from '../loom-simulation';
import { loadRapier, type RapierApi } from './rapier-loader';

export const LOOM_RAPIER_TOUCH_DEBRIS_CAP = 10;
export const LOOM_RAPIER_DESKTOP_DEBRIS_CAP = 18;
export const LOOM_RAPIER_IRIS_BLADE_COUNT = LOOM_IRIS_BLADE_COUNT;

const SHADOW_Z = 0;
const DISABLED_Z = -1_000;
const ENDPOINT_PROXY_RADIUS = 0.08;
const THREAD_PROXY_RADIUS = LOOM_IRIS_THREAD_RADIUS;
const ANCHOR_PROXY_RADIUS = 0.26;
const ANCHOR_PROXY_HALF_DEPTH = 0.74;
const IRIS_BLADE_RADIAL_HALF = 2.15;
const IRIS_BLADE_TANGENTIAL_HALF = 1.55;
const IRIS_BLADE_DEPTH_HALF = 0.46;
const DEBRIS_MIN_LIFETIME_SECONDS = 2.2;
const DEBRIS_LIFETIME_VARIANCE_SECONDS = 1.2;
const DEBRIS_DESPAWN_DISTANCE = 170;

const LAYER_NEEDLE = 1 << 0;
const LAYER_ECHO = 1 << 1;
const LAYER_THREAD_EMBER = 1 << 2;
const LAYER_THREAD_COBALT = 1 << 3;
const LAYER_ANCHOR_EMBER = 1 << 4;
const LAYER_ANCHOR_COBALT = 1 << 5;
const LAYER_FX_DEBRIS = 1 << 6;
const LAYER_IRIS = 1 << 7;

const EMPTY_VECTOR = Object.freeze({ x: 0, y: 0, z: 0 });
const IDENTITY_ROTATION = Object.freeze({ x: 0, y: 0, z: 0, w: 1 });
const QUARTER_TURN_X = Object.freeze({
  x: Math.SQRT1_2,
  y: 0,
  z: 0,
  w: Math.SQRT1_2,
});

export interface LoomRapierVector3 {
  x: number;
  y: number;
  z: number;
}

export interface LoomRapierQuaternion {
  x: number;
  y: number;
  z: number;
  w: number;
}

export type LoomRapierContactActor = 'needle' | 'echo' | 'thread';
export type LoomRapierDebrisKind =
  | 'thread-break'
  | 'stitch'
  | 'resonance';

export interface LoomRapierContact {
  anchorId: string;
  poolSlot: number;
  actor: LoomRapierContactActor;
  anchorPhase: LoomPhase;
  route: LoomAnchorRoute;
  phaseMatches: boolean;
  authoritativeHit: boolean;
  authoritativeLatched: boolean;
  authoritativeResolved: boolean;
}

export interface LoomRapierFixedStepResult {
  contacts: readonly LoomRapierContact[];
  irisContacts: readonly LoomRapierIrisContact[];
}

export interface LoomRapierIrisContact {
  cycle: number;
  blade: number;
  actor: LoomRapierContactActor;
  authoritativeStage: LoomIrisStage;
  authoritativeResolved: boolean;
  authoritativeOutcome: LoomIrisOutcome;
}

export interface LoomRapierDebrisPose {
  id: number;
  kind: LoomRapierDebrisKind;
  position: LoomRapierVector3;
  rotation: LoomRapierQuaternion;
  sleeping: boolean;
}

export interface LoomRapierDiagnostics {
  bodyCount: number;
  colliderCount: number;
  anchorCapacity: number;
  activeAnchors: number;
  irisSensorCapacity: number;
  activeIrisSensors: number;
  irisCycle: number;
  debrisCapacity: number;
  activeDebris: number;
  physicsSteps: number;
  timestep: number;
  paused: boolean;
  disposed: boolean;
}

export interface LoomRapierPhysicsOptions {
  touchFirst: boolean;
}

type ColliderTag =
  | { role: LoomRapierContactActor }
  | { role: 'anchor'; slot: number }
  | { role: 'iris'; blade: number };

interface AnchorSlot {
  body: RigidBody;
  collider: Collider;
  anchorId: string | null;
  phase: LoomPhase | null;
  enabled: boolean;
}

interface IrisBladeSlot {
  body: RigidBody;
  collider: Collider;
  cycle: number;
  enabled: boolean;
}

interface DebrisBody {
  id: number;
  body: RigidBody;
  active: boolean;
  expiresAt: number;
  kind: LoomRapierDebrisKind;
}

function interactionGroups(membership: number, filter: number): number {
  return (((membership & 0xffff) << 16) | (filter & 0xffff)) >>> 0;
}

const ANCHOR_FILTER = LAYER_ANCHOR_EMBER | LAYER_ANCHOR_COBALT;
const NEEDLE_ANCHOR_GROUPS = interactionGroups(LAYER_NEEDLE, ANCHOR_FILTER);
const ECHO_ANCHOR_GROUPS = interactionGroups(LAYER_ECHO, ANCHOR_FILTER);
const NEEDLE_IRIS_GROUPS = interactionGroups(LAYER_NEEDLE, LAYER_IRIS);
const ECHO_IRIS_GROUPS = interactionGroups(LAYER_ECHO, LAYER_IRIS);
const THREAD_EMBER_GROUPS = interactionGroups(
  LAYER_THREAD_EMBER,
  LAYER_ANCHOR_EMBER | LAYER_IRIS,
);
const THREAD_COBALT_GROUPS = interactionGroups(
  LAYER_THREAD_COBALT,
  LAYER_ANCHOR_COBALT | LAYER_IRIS,
);
const ANCHOR_EMBER_GROUPS = interactionGroups(
  LAYER_ANCHOR_EMBER,
  LAYER_NEEDLE | LAYER_ECHO | LAYER_THREAD_EMBER,
);
const ANCHOR_COBALT_GROUPS = interactionGroups(
  LAYER_ANCHOR_COBALT,
  LAYER_NEEDLE | LAYER_ECHO | LAYER_THREAD_COBALT,
);
const IRIS_GROUPS = interactionGroups(
  LAYER_IRIS,
  LAYER_NEEDLE | LAYER_ECHO | LAYER_THREAD_EMBER | LAYER_THREAD_COBALT,
);
const DEBRIS_GROUPS = interactionGroups(LAYER_FX_DEBRIS, 0);
const NO_SOLVER_GROUPS = interactionGroups(0, 0);

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function normalizedVector(
  vector: Readonly<LoomRapierVector3>,
): LoomRapierVector3 {
  const x = finite(vector.x);
  const y = finite(vector.y);
  const z = finite(vector.z);
  const length = Math.hypot(x, y, z);
  if (length < 1e-6) return { x: 0, y: 0, z: 1 };
  return { x: x / length, y: y / length, z: z / length };
}

function anchorGroups(phase: LoomPhase): number {
  return phase === 'ember' ? ANCHOR_EMBER_GROUPS : ANCHOR_COBALT_GROUPS;
}

function threadGroups(phase: LoomPhase): number {
  return phase === 'ember' ? THREAD_EMBER_GROUPS : THREAD_COBALT_GROUPS;
}

function actorRank(actor: LoomRapierContactActor): number {
  if (actor === 'needle') return 0;
  if (actor === 'echo') return 1;
  return 2;
}

function contactActor(
  tag: ColliderTag | undefined,
): LoomRapierContactActor | null {
  if (
    tag?.role === 'needle' ||
    tag?.role === 'echo' ||
    tag?.role === 'thread'
  ) return tag.role;
  return null;
}

/**
 * A bounded Rapier presentation sidecar for Signal Loom.
 *
 * LoomSimulation remains the sole authority for movement, phase eligibility,
 * hits, latches, thread breaks, score, and extraction. Rapier only supplies
 * contact metadata and dynamic presentation particles.
 */
export class LoomRapierPhysics {
  private readonly RAPIER: RapierApi;
  private readonly world: World;
  private readonly eventQueue: EventQueue;
  private readonly needleBody: RigidBody;
  private readonly echoBody: RigidBody;
  private readonly threadBody: RigidBody;
  private readonly threadCollider: Collider;
  private readonly anchorSlots: AnchorSlot[];
  private readonly irisBlades: IrisBladeSlot[];
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
  private threadPhase: LoomPhase | null = null;
  private threadHalfLength = Number.NaN;
  private irisCycle = 0;

  static async create(
    options: LoomRapierPhysicsOptions,
  ): Promise<LoomRapierPhysics> {
    const RAPIER = await loadRapier();
    return new LoomRapierPhysics(RAPIER, options);
  }

  private constructor(RAPIER: RapierApi, options: LoomRapierPhysicsOptions) {
    this.RAPIER = RAPIER;
    this.debrisCapacity = options.touchFirst
      ? LOOM_RAPIER_TOUCH_DEBRIS_CAP
      : LOOM_RAPIER_DESKTOP_DEBRIS_CAP;
    this.world = new RAPIER.World({ x: 0, y: 0, z: 0 });
    this.world.timestep = LOOM_FIXED_STEP_SECONDS;
    this.world.lengthUnit = 1;
    this.world.maxCcdSubsteps = 1;
    this.eventQueue = new RAPIER.EventQueue(true);

    const activeCollisionTypes =
      RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC;
    this.needleBody = this.createKinematicBody();
    const needleCollider = this.world.createCollider(
      RAPIER.ColliderDesc.ball(ENDPOINT_PROXY_RADIUS)
        .setSensor(true)
        .setCollisionGroups(NEEDLE_ANCHOR_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes),
      this.needleBody,
    );
    this.colliderTags.set(needleCollider.handle, { role: 'needle' });
    const needleIrisCollider = this.world.createCollider(
      RAPIER.ColliderDesc.ball(LOOM_IRIS_NEEDLE_RADIUS)
        .setSensor(true)
        .setCollisionGroups(NEEDLE_IRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes),
      this.needleBody,
    );
    this.colliderTags.set(needleIrisCollider.handle, { role: 'needle' });

    this.echoBody = this.createKinematicBody();
    const echoCollider = this.world.createCollider(
      RAPIER.ColliderDesc.ball(ENDPOINT_PROXY_RADIUS)
        .setSensor(true)
        .setCollisionGroups(ECHO_ANCHOR_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes),
      this.echoBody,
    );
    this.colliderTags.set(echoCollider.handle, { role: 'echo' });
    const echoIrisCollider = this.world.createCollider(
      RAPIER.ColliderDesc.ball(LOOM_IRIS_ECHO_RADIUS)
        .setSensor(true)
        .setCollisionGroups(ECHO_IRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes),
      this.echoBody,
    );
    this.colliderTags.set(echoIrisCollider.handle, { role: 'echo' });

    this.threadBody = this.createKinematicBody();
    this.threadCollider = this.world.createCollider(
      RAPIER.ColliderDesc.capsule(0.01, THREAD_PROXY_RADIUS)
        .setSensor(true)
        .setCollisionGroups(THREAD_EMBER_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(activeCollisionTypes),
      this.threadBody,
    );
    this.colliderTags.set(this.threadCollider.handle, { role: 'thread' });

    this.anchorSlots = Array.from(
      { length: LOOM_ANCHOR_POOL_SIZE },
      (_, slot) => this.createAnchorSlot(slot),
    );
    this.irisBlades = Array.from(
      { length: LOOM_RAPIER_IRIS_BLADE_COUNT },
      (_, blade) => this.createIrisBlade(blade),
    );
    this.debris = Array.from(
      { length: this.debrisCapacity },
      (_, id) => this.createDebrisBody(id),
    );
  }

  private createKinematicBody(): RigidBody {
    return this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, SHADOW_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
  }

  private createAnchorSlot(slot: number): AnchorSlot {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, DISABLED_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    const collider = this.world.createCollider(
      this.RAPIER.ColliderDesc.cylinder(
        ANCHOR_PROXY_HALF_DEPTH,
        ANCHOR_PROXY_RADIUS,
      )
        .setRotation(QUARTER_TURN_X)
        .setSensor(true)
        .setEnabled(false)
        .setCollisionGroups(ANCHOR_EMBER_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(
          this.RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC,
        )
        .setActiveEvents(this.RAPIER.ActiveEvents.COLLISION_EVENTS),
      body,
    );
    body.setEnabled(false);
    this.colliderTags.set(collider.handle, { role: 'anchor', slot });
    return {
      body,
      collider,
      anchorId: null,
      phase: null,
      enabled: false,
    };
  }

  private createIrisBlade(blade: number): IrisBladeSlot {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, DISABLED_Z)
        .setCanSleep(false)
        .setCcdEnabled(false),
    );
    const collider = this.world.createCollider(
      this.RAPIER.ColliderDesc.cuboid(
        IRIS_BLADE_RADIAL_HALF,
        IRIS_BLADE_TANGENTIAL_HALF,
        IRIS_BLADE_DEPTH_HALF,
      )
        .setSensor(true)
        .setEnabled(false)
        .setCollisionGroups(IRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS)
        .setActiveCollisionTypes(
          this.RAPIER.ActiveCollisionTypes.KINEMATIC_KINEMATIC,
        )
        .setActiveEvents(this.RAPIER.ActiveEvents.COLLISION_EVENTS),
      body,
    );
    body.setEnabled(false);
    this.colliderTags.set(collider.handle, { role: 'iris', blade });
    return { body, collider, cycle: 0, enabled: false };
  }

  private createDebrisBody(id: number): DebrisBody {
    const body = this.world.createRigidBody(
      this.RAPIER.RigidBodyDesc.dynamic()
        .setTranslation(0, 0, DISABLED_Z)
        .setGravityScale(0)
        .setLinearDamping(1.75)
        .setAngularDamping(2.15)
        .setCanSleep(true)
        .setCcdEnabled(false),
    );
    this.world.createCollider(
      this.RAPIER.ColliderDesc.ball(0.085 + (id % 3) * 0.022)
        .setSensor(true)
        .setDensity(0.6)
        .setCollisionGroups(DEBRIS_GROUPS)
        .setSolverGroups(NO_SOLVER_GROUPS),
      body,
    );
    body.setEnabled(false);
    return {
      id,
      body,
      active: false,
      expiresAt: 0,
      kind: 'stitch',
    };
  }

  private nextRandom(): number {
    let state = this.fxRngState >>> 0;
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    this.fxRngState = state >>> 0 || 0x6d2b79f5;
    return this.fxRngState / 0x100000000;
  }

  private configureThreadPhase(phase: LoomPhase): void {
    if (this.threadPhase === phase) return;
    this.threadCollider.setCollisionGroups(threadGroups(phase));
    this.threadPhase = phase;
  }

  private anchorAtSlot(
    simulation: Readonly<LoomSimulation>,
    slot: number,
  ): Readonly<LoomAnchor> | undefined {
    const direct = simulation.anchors[slot];
    if (direct?.poolSlot === slot) return direct;
    return simulation.anchors.find((candidate) => candidate.poolSlot === slot);
  }

  private setBodyPose(
    body: RigidBody,
    position: Readonly<LoomRapierVector3>,
    rotation: Readonly<LoomRapierQuaternion> | null,
    teleport: boolean,
  ): boolean {
    if (teleport) {
      body.setTranslation(position, false);
      body.setNextKinematicTranslation(position);
      if (rotation) {
        body.setRotation(rotation, false);
        body.setNextKinematicRotation(rotation);
      }
      return true;
    }
    body.setNextKinematicTranslation(position);
    if (rotation) body.setNextKinematicRotation(rotation);
    return false;
  }

  private syncIrisShadow(
    simulation: Readonly<LoomSimulation>,
    teleportAll: boolean,
  ): { propagated: boolean; enableAfterPropagation: IrisBladeSlot[] } {
    const iris = simulation.iris;
    const enabled = iris.active && iris.stage === 'contact';
    const enableAfterPropagation: IrisBladeSlot[] = [];
    let propagated = false;
    this.irisCycle = iris.cycle;

    this.irisBlades.forEach((slot, blade) => {
      if (!enabled) {
        if (slot.enabled) {
          slot.collider.setEnabled(false);
          slot.body.setEnabled(false);
        }
        slot.enabled = false;
        slot.cycle = iris.cycle;
        return;
      }

      const angle =
        (blade / LOOM_RAPIER_IRIS_BLADE_COUNT) * Math.PI * 2 +
        iris.cycle * 0.071;
      const bladeCenterRadius = Math.min(
        iris.gapRadius + IRIS_BLADE_RADIAL_HALF,
        LOOM_FLIGHT_BOUNDARY + 0.25,
      );
      const position = {
        x: iris.gapCenter.x + Math.cos(angle) * bladeCenterRadius,
        y: iris.gapCenter.y + Math.sin(angle) * bladeCenterRadius,
        z: iris.z,
      };
      const rotation = {
        x: 0,
        y: 0,
        z: Math.sin(angle / 2),
        w: Math.cos(angle / 2),
      };
      const identityChanged =
        teleportAll || slot.cycle !== iris.cycle || !slot.enabled;
      if (identityChanged) {
        if (slot.enabled) slot.collider.setEnabled(false);
        slot.body.setEnabled(true);
        propagated =
          this.setBodyPose(slot.body, position, rotation, true) || propagated;
        enableAfterPropagation.push(slot);
      } else {
        this.setBodyPose(slot.body, position, rotation, false);
      }
      slot.cycle = iris.cycle;
      slot.enabled = true;
    });

    return { propagated, enableAfterPropagation };
  }

  private syncShadow(
    simulation: Readonly<LoomSimulation>,
    teleportAll: boolean,
  ): void {
    this.configureThreadPhase(simulation.phase);
    let propagated = false;

    const needlePosition = {
      x: finite(simulation.needle.position.x),
      y: finite(simulation.needle.position.y),
      z: SHADOW_Z,
    };
    const echoPosition = {
      x: finite(simulation.echo.position.x),
      y: finite(simulation.echo.position.y),
      z: SHADOW_Z,
    };
    propagated =
      this.setBodyPose(this.needleBody, needlePosition, null, teleportAll) ||
      propagated;
    propagated =
      this.setBodyPose(this.echoBody, echoPosition, null, teleportAll) ||
      propagated;

    const threadX = echoPosition.x - needlePosition.x;
    const threadY = echoPosition.y - needlePosition.y;
    const threadLength = Math.hypot(threadX, threadY);
    const halfLength = Math.max(0.01, threadLength / 2);
    if (this.threadHalfLength !== halfLength) {
      this.threadCollider.setHalfHeight(halfLength);
      this.threadHalfLength = halfLength;
    }
    const angle = threadLength > 1e-6
      ? Math.atan2(threadY, threadX) - Math.PI / 2
      : 0;
    const threadRotation = {
      x: 0,
      y: 0,
      z: Math.sin(angle / 2),
      w: Math.cos(angle / 2),
    };
    propagated =
      this.setBodyPose(
        this.threadBody,
        {
          x: (needlePosition.x + echoPosition.x) / 2,
          y: (needlePosition.y + echoPosition.y) / 2,
          z: SHADOW_Z,
        },
        threadRotation,
        teleportAll,
      ) || propagated;

    const enableAfterPropagation: AnchorSlot[] = [];
    this.anchorSlots.forEach((slot, slotIndex) => {
      const anchor = this.anchorAtSlot(simulation, slotIndex);
      if (!anchor?.active) {
        if (slot.enabled) {
          slot.collider.setEnabled(false);
          slot.body.setEnabled(false);
        }
        slot.anchorId = null;
        slot.phase = null;
        slot.enabled = false;
        return;
      }

      const position = {
        x: finite(anchor.x),
        y: finite(anchor.y),
        z: finite(anchor.z, DISABLED_Z),
      };
      const identityChanged =
        teleportAll || slot.anchorId !== anchor.id || !slot.enabled;
      if (identityChanged) {
        if (slot.enabled) slot.collider.setEnabled(false);
        slot.body.setEnabled(true);
        propagated = this.setBodyPose(slot.body, position, null, true) || propagated;
        enableAfterPropagation.push(slot);
      } else {
        this.setBodyPose(slot.body, position, null, false);
      }
      if (slot.phase !== anchor.phase) {
        slot.collider.setCollisionGroups(anchorGroups(anchor.phase));
        slot.phase = anchor.phase;
      }
      slot.anchorId = anchor.id;
      slot.enabled = true;
    });

    const irisSync = this.syncIrisShadow(simulation, teleportAll);
    propagated = irisSync.propagated || propagated;
    if (propagated) this.world.propagateModifiedBodyPositionsToColliders();
    enableAfterPropagation.forEach((slot) => slot.collider.setEnabled(true));
    irisSync.enableAfterPropagation.forEach((slot) =>
      slot.collider.setEnabled(true),
    );
  }

  private contactsForStep(
    simulation: Readonly<LoomSimulation>,
  ): LoomRapierFixedStepResult {
    const contacts = new Map<string, LoomRapierContact>();
    const irisContacts = new Map<string, LoomRapierIrisContact>();
    this.eventQueue.drainCollisionEvents((handle1, handle2, started) => {
      if (!started) return;
      const first = this.colliderTags.get(handle1);
      const second = this.colliderTags.get(handle2);
      const anchorTag = first?.role === 'anchor'
        ? first
        : second?.role === 'anchor'
          ? second
          : null;
      const irisTag = first?.role === 'iris'
        ? first
        : second?.role === 'iris'
          ? second
          : null;
      const actor = contactActor(first) ?? contactActor(second);
      if (!actor) return;

      if (anchorTag) {
        const slot = this.anchorSlots[anchorTag.slot];
        if (!slot?.enabled || !slot.anchorId) return;
        const anchor = this.anchorAtSlot(simulation, anchorTag.slot);
        if (!anchor?.active || anchor.id !== slot.anchorId) return;
        const key = `${anchor.id}:${actor}`;
        contacts.set(key, {
          anchorId: anchor.id,
          poolSlot: anchor.poolSlot,
          actor,
          anchorPhase: anchor.phase,
          route: anchor.route,
          phaseMatches: anchor.phase === simulation.phase,
          authoritativeHit: anchor.hit,
          authoritativeLatched: anchor.latched,
          authoritativeResolved: anchor.resolved,
        });
        return;
      }

      if (irisTag) {
        const slot = this.irisBlades[irisTag.blade];
        if (!slot?.enabled || slot.cycle !== simulation.iris.cycle) return;
        const key = `${simulation.iris.cycle}:${irisTag.blade}:${actor}`;
        irisContacts.set(key, {
          cycle: simulation.iris.cycle,
          blade: irisTag.blade,
          actor,
          authoritativeStage: simulation.iris.stage,
          authoritativeResolved: simulation.iris.resolved,
          authoritativeOutcome: simulation.iris.outcome,
        });
      }
    });
    const sortedContacts = [...contacts.values()].sort(
      (left, right) =>
        left.poolSlot - right.poolSlot ||
        actorRank(left.actor) - actorRank(right.actor) ||
        left.anchorId.localeCompare(right.anchorId),
    );
    const sortedIrisContacts = [...irisContacts.values()].sort(
      (left, right) =>
        left.blade - right.blade || actorRank(left.actor) - actorRank(right.actor),
    );
    return { contacts: sortedContacts, irisContacts: sortedIrisContacts };
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
        Math.hypot(position.x, position.y, position.z) >
          DEBRIS_DESPAWN_DISTANCE
      ) {
        this.deactivateDebris(piece);
      }
    });
  }

  private activateDebris(
    kind: LoomRapierDebrisKind,
    position: Readonly<LoomRapierVector3>,
    direction: Readonly<LoomRapierVector3>,
    strength: number,
  ): void {
    const piece = this.debris[this.nextDebrisIndex % this.debris.length];
    this.nextDebrisIndex = (this.nextDebrisIndex + 1) % this.debris.length;
    const safePosition = {
      x: finite(position.x) + (this.nextRandom() - 0.5) * 0.3,
      y: finite(position.y) + (this.nextRandom() - 0.5) * 0.3,
      z: finite(position.z) + (this.nextRandom() - 0.5) * 0.22,
    };
    const launchDirection = normalizedVector(direction);
    const launchSpeed = (4.4 + this.nextRandom() * 4.6) * strength;
    const tangentX = (this.nextRandom() - 0.5) * 4.6;
    const tangentY = (this.nextRandom() - 0.5) * 4.6;
    const tangentZ = (this.nextRandom() - 0.5) * 2.2;

    piece.body.setEnabled(true);
    piece.body.setTranslation(safePosition, true);
    piece.body.setRotation(IDENTITY_ROTATION, true);
    piece.body.setLinvel({ x: 0, y: 0, z: this.lastForwardSpeed * 0.08 }, true);
    piece.body.setAngvel(
      {
        x: (this.nextRandom() - 0.5) * 16,
        y: (this.nextRandom() - 0.5) * 16,
        z: (this.nextRandom() - 0.5) * 16,
      },
      true,
    );
    const mass = Math.max(0.0001, piece.body.mass());
    piece.body.applyImpulse(
      {
        x: mass * (launchDirection.x * launchSpeed + tangentX),
        y: mass * (launchDirection.y * launchSpeed + tangentY),
        z: mass * (launchDirection.z * launchSpeed + tangentZ),
      },
      true,
    );
    piece.kind = kind;
    piece.active = true;
    piece.expiresAt =
      this.physicsTime +
      DEBRIS_MIN_LIFETIME_SECONDS +
      this.nextRandom() * DEBRIS_LIFETIME_VARIANCE_SECONDS;
  }

  reset(simulation: Readonly<LoomSimulation>): void {
    if (this.disposed) return;
    this.paused = false;
    this.physicsSteps = 0;
    this.physicsTime = 0;
    this.lastForwardSpeed = finite(simulation.forwardSpeed);
    this.fxRngState = ((simulation.seed >>> 0) ^ 0xc8013ea4) || 0x6d2b79f5;
    this.nextDebrisIndex = 0;
    this.threadPhase = null;
    this.threadHalfLength = Number.NaN;
    this.irisCycle = simulation.iris.cycle;
    this.eventQueue.clear();
    this.debris.forEach((piece) => this.deactivateDebris(piece));
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
  }

  fixedStep(
    simulation: Readonly<LoomSimulation>,
  ): LoomRapierFixedStepResult {
    if (this.disposed || this.paused) {
      return { contacts: [], irisContacts: [] };
    }
    this.world.timestep = LOOM_FIXED_STEP_SECONDS;
    this.lastForwardSpeed = finite(simulation.forwardSpeed);
    this.syncShadow(simulation, false);
    this.physicsTime += LOOM_FIXED_STEP_SECONDS;
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

  resume(simulation: Readonly<LoomSimulation>): void {
    if (this.disposed) return;
    this.eventQueue.clear();
    this.syncShadow(simulation, true);
    this.eventQueue.clear();
    this.paused = false;
  }

  emitThreadBreak(
    position: Readonly<LoomRapierVector3>,
    normal: Readonly<LoomRapierVector3> = { x: 0, y: 0, z: 1 },
    strength = 1,
  ): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 5 : 7);
    const safeStrength = clamp(finite(strength, 1), 0.3, 3);
    for (let index = 0; index < count; index += 1) {
      this.activateDebris('thread-break', position, normal, safeStrength);
    }
  }

  emitStitch(
    position: Readonly<LoomRapierVector3>,
    tangent: Readonly<LoomRapierVector3> = { x: 1, y: 0, z: 0.15 },
    strength = 1,
  ): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 3 : 4);
    const safeStrength = clamp(finite(strength, 1), 0.2, 2) * 0.62;
    for (let index = 0; index < count; index += 1) {
      this.activateDebris('stitch', position, tangent, safeStrength);
    }
  }

  emitResonance(position: Readonly<LoomRapierVector3>): void {
    if (this.disposed || this.paused || this.debris.length === 0) return;
    if (!this.debris.some((piece) => piece.active)) {
      const count = Math.min(this.debris.length, this.debrisCapacity <= 10 ? 6 : 9);
      for (let index = 0; index < count; index += 1) {
        const angle = (index / count) * Math.PI * 2;
        this.activateDebris(
          'resonance',
          {
            x: finite(position.x) + Math.cos(angle) * 0.5,
            y: finite(position.y) + Math.sin(angle) * 0.5,
            z: finite(position.z),
          },
          { x: Math.cos(angle), y: Math.sin(angle), z: 0.22 },
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
      piece.kind = 'resonance';
      piece.expiresAt = Math.max(piece.expiresAt, this.physicsTime + 2.4);
    });
  }

  forEachActiveDebrisPose(
    callback: (pose: Readonly<LoomRapierDebrisPose>) => void,
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

  getDiagnostics(): LoomRapierDiagnostics {
    const activeAnchors = this.anchorSlots.reduce(
      (count, slot) => count + Number(slot.enabled),
      0,
    );
    const activeDebris = this.debris.reduce(
      (count, piece) => count + Number(piece.active),
      0,
    );
    const activeIrisSensors = this.irisBlades.reduce(
      (count, slot) => count + Number(slot.enabled),
      0,
    );
    return {
      bodyCount: this.disposed ? 0 : this.world.bodies.len(),
      colliderCount: this.disposed ? 0 : this.world.colliders.len(),
      anchorCapacity: LOOM_ANCHOR_POOL_SIZE,
      activeAnchors,
      irisSensorCapacity: LOOM_RAPIER_IRIS_BLADE_COUNT,
      activeIrisSensors,
      irisCycle: this.disposed ? 0 : this.irisCycle,
      debrisCapacity: this.debrisCapacity,
      activeDebris,
      physicsSteps: this.physicsSteps,
      timestep: LOOM_FIXED_STEP_SECONDS,
      paused: this.paused,
      disposed: this.disposed,
    };
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.paused = true;
    this.colliderTags.clear();
    this.anchorSlots.length = 0;
    this.irisBlades.length = 0;
    this.debris.length = 0;
    this.eventQueue.free();
    this.world.free();
  }
}
