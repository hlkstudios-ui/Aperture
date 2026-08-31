import { Camera } from '@babylonjs/core/Cameras/camera.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { Constants } from '@babylonjs/core/Engines/constants.js';
import type { Engine } from '@babylonjs/core/Engines/engine.js';
import type { WebGPUEngine } from '@babylonjs/core/Engines/webgpuEngine.js';
import { GlowLayer } from '@babylonjs/core/Layers/glowLayer.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { PointLight } from '@babylonjs/core/Lights/pointLight.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import { Matrix, Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { ImageProcessingConfiguration } from '@babylonjs/core/Materials/imageProcessingConfiguration.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { Texture } from '@babylonjs/core/Materials/Textures/texture.js';
import { CreateBox } from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import { CreateCylinder } from '@babylonjs/core/Meshes/Builders/cylinderBuilder.js';
import { CreatePolyhedron } from '@babylonjs/core/Meshes/Builders/polyhedronBuilder.js';
import { CreateSphere } from '@babylonjs/core/Meshes/Builders/sphereBuilder.js';
import { CreateTorus } from '@babylonjs/core/Meshes/Builders/torusBuilder.js';
import { CreateTube } from '@babylonjs/core/Meshes/Builders/tubeBuilder.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode.js';
import { FxaaPostProcess } from '@babylonjs/core/PostProcesses/fxaaPostProcess.js';
import { Scene } from '@babylonjs/core/scene.js';

import {
  BALL_TUNNEL_RADIUS,
  BALL_RADIUS,
  type BallGateEvent,
  type BallImpactEvent,
  type BallObstacle,
  type BallSimulation,
} from '../ball-simulation';
import {
  createBabylonEngine,
  type BabylonEngineFactoryOptions,
  type BabylonRenderBackend,
} from './babylon-engine-factory';
import {
  hardwareScalingLevelForPixelRatio,
  initialQualityTier,
  QualityGovernor,
  renderPixelRatioForQuality,
  type QualityProfile,
  type QualityTier,
} from './quality-governor';

export const SIGNAL_RUN_ASSETS = Object.freeze({
  panelAlbedo: '/game/loom-panels-albedo.webp',
  veinMask: '/game/loom-veins-mask.webp',
} as const);

export const SIGNAL_RUN_BALL_DIAMETER = BALL_RADIUS * 2;
export const SIGNAL_RUN_GATE_VISUAL_CAPACITY = 16;
export const SIGNAL_RUN_BLOCK_VISUAL_CAPACITY = 16;
export const SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY = 32;

const PLAYER_Z = 0;
const TUNNEL_RADIUS = BALL_TUNNEL_RADIUS;
const TUNNEL_LENGTH = 390;
const RIB_CAPACITY = 12;
const PERFORMANCE_RIB_COUNT = 6;
const RIB_SPACING = 24;
const RIB_LOOP_LENGTH = RIB_CAPACITY * RIB_SPACING;
const RAIL_CAPACITY = 12;
const PERFORMANCE_RAIL_COUNT = 6;
const RAIL_SEGMENT_LENGTH = RIB_LOOP_LENGTH / 3;
const OBSTACLE_NEAR_Z = 18;
const OBSTACLE_FAR_Z = -175;
const TRAIL_POINT_COUNT = 9;
const MAX_VISUAL_DELTA_SECONDS = 0.05;
const MAX_FEEDBACK_STRENGTH = 2;

const SIGNAL = Color3.FromHexString('#ff6a45');
const SIGNAL_HOT = Color3.FromHexString('#ffe2c9');
const SIGNAL_DARK = Color3.FromHexString('#42150f');
const GATE_SIGNAL = Color3.FromHexString('#72e1ff');
const BLOCK_WARNING = Color3.FromHexString('#ff9b55');
const BLOCK_SAFE_SIGNAL = Color3.FromHexString('#a8ffc4');
const BLACK = Color3.Black();
const TELEGRAPH_MIN_STRENGTH = 0.12;
// The solid-route marker is an in-world HUD cue: it keeps the authored X/Y,
// but sits camera-side of the player plane so small portrait projections do
// not collapse it into the ball's corona.
const BLOCK_TELEGRAPH_GUIDE_Z = 4.5;
const TELEGRAPH_HAZARD_OFFSET = 0.72;
const TELEGRAPH_BALL_CLEAR_Z = -1.45;

export type SignalRunPhysicsBackend = 'rapier' | 'none';

export interface SignalRunEngineSelection {
  engine: AbstractEngine;
  backend: BabylonRenderBackend;
}

export type SignalRunEngineFactory = (
  canvas: HTMLCanvasElement,
  options?: BabylonEngineFactoryOptions,
) => Promise<SignalRunEngineSelection>;

export interface SignalRunResizeObserver {
  observe(target: Element): void;
  disconnect(): void;
}

export type SignalRunResizeObserverFactory = (
  callback: ResizeObserverCallback,
) => SignalRunResizeObserver;

export interface SignalRunBabylonSceneOptions {
  signal?: AbortSignal;
  touchFirst?: boolean;
  comfortMode?: boolean;
  physicsBackend?: SignalRunPhysicsBackend;
  /** Kept as a narrow construction seam for NullEngine lifecycle tests. */
  engineFactory?: SignalRunEngineFactory;
  resizeObserverFactory?: SignalRunResizeObserverFactory;
}

export interface SignalRunBabylonDiagnostics {
  renderBackend: BabylonRenderBackend;
  physicsBackend: SignalRunPhysicsBackend;
  qualityTier: QualityTier;
  pixelRatio: number;
  renderWidth: number;
  renderHeight: number;
  ballDiameter: number;
  gateCapacity: number;
  blockCapacity: number;
  debrisCapacity: number;
  activeGates: number;
  activeBlocks: number;
  activeDebris: number;
  paused: boolean;
  disposed: boolean;
}

export interface SignalRunDebrisPose {
  id: number;
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number; w: number };
  sleeping: boolean;
}

export type SignalRunDebrisSource =
  | Iterable<Readonly<SignalRunDebrisPose>>
  | ((visit: (pose: Readonly<SignalRunDebrisPose>) => void) => void);

interface ThinPool {
  mesh: Mesh;
  matrices: Float32Array;
}

interface BallVisual {
  root: TransformNode;
  shell: Mesh;
  outline: Mesh;
  corona: Mesh;
  trail: Mesh;
  trailPath: Vector3[];
}

interface EnvironmentVisual {
  tunnel: Mesh;
  veins: Mesh;
  ribs: ThinPool;
  rails: ThinPool;
  panelTexture: Texture;
  veinTexture: Texture;
  panelMaterial: PBRMaterial;
  ribMaterial: PBRMaterial;
  performancePanelMaterial: StandardMaterial;
  performanceRibMaterial: StandardMaterial;
  veinMaterial: StandardMaterial;
  railMaterial: StandardMaterial;
}

interface ObstacleVisuals {
  gates: ThinPool;
  gateCores: ThinPool;
  blocks: ThinPool;
  blockEdges: ThinPool;
}

interface TelegraphVisuals {
  gateReticle: Mesh;
  blockReticle: Mesh;
  gateMaterial: StandardMaterial;
  blockMaterial: StandardMaterial;
}

interface AdaptedBody {
  position: { x: number; y: number };
  velocity: { x: number; y: number };
}

interface AdaptedFrame {
  ball: AdaptedBody;
  obstacles: readonly BallObstacle[];
  accumulator: number;
  distance: number;
  elapsed: number;
  overdriveRemaining: number;
  speed: number;
}

interface ObstacleShape {
  active?: boolean;
  depth?: number;
  height?: number;
  hit?: boolean;
  id?: string;
  kind: string;
  openingRadius?: number;
  passed?: boolean;
  radius?: number;
  safePoint?: { x?: number; y?: number };
  telegraphSeconds?: number;
  width?: number;
  x?: number;
  y?: number;
  z?: number;
}

const defaultEngineFactory: SignalRunEngineFactory = async (canvas, options) =>
  createBabylonEngine<WebGPUEngine, Engine>(canvas, options);

function defaultTouchFirst(): boolean {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
    ? window.matchMedia('(hover: none), (pointer: coarse)').matches
    : false;
}

function createAbortError() {
  if (typeof DOMException === 'function') {
    return new DOMException(
      'Signal Run Babylon scene creation was aborted.',
      'AbortError',
    );
  }
  const error = new Error('Signal Run Babylon scene creation was aborted.');
  error.name = 'AbortError';
  return error;
}

function finite(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function positiveModulo(value: number, modulus: number) {
  return ((value % modulus) + modulus) % modulus;
}

function setColorScaled(target: Color3, source: Color3, scale: number) {
  target.set(source.r * scale, source.g * scale, source.b * scale);
}

function writeHiddenMatrix(buffer: Float32Array, index: number) {
  const offset = index * 16;
  buffer.fill(0, offset, offset + 16);
  buffer[offset + 14] = 1_000;
  buffer[offset + 15] = 1;
}

function makeThinPool(mesh: Mesh, capacity: number): ThinPool {
  const matrices = new Float32Array(capacity * 16);
  for (let index = 0; index < capacity; index += 1) {
    writeHiddenMatrix(matrices, index);
  }
  mesh.alwaysSelectAsActiveMesh = true;
  mesh.thinInstanceSetBuffer('matrix', matrices, 16, false);
  mesh.thinInstanceCount = 0;
  return { mesh, matrices };
}

function updateThinPool(pool: ThinPool, activeCount: number) {
  pool.mesh.thinInstanceCount = clamp(
    Math.trunc(activeCount),
    0,
    pool.matrices.length / 16,
  );
  pool.mesh.thinInstanceBufferUpdated('matrix');
}

function hideUnusedThinInstances(pool: ThinPool, from: number) {
  for (
    let index = Math.max(0, from);
    index < pool.matrices.length / 16;
    index += 1
  ) {
    writeHiddenMatrix(pool.matrices, index);
  }
}

function adaptSimulation(simulation: Readonly<BallSimulation>): AdaptedFrame {
  const frame = simulation as unknown as {
    accumulator?: number;
    ball?: AdaptedBody;
    distance?: number;
    elapsed?: number;
    forwardSpeed?: number;
    obstacles?: readonly BallObstacle[];
    overdriveRemaining?: number;
    player?: AdaptedBody;
    speed?: number;
  };
  const fallbackBody: AdaptedBody = {
    position: { x: 0, y: 0 },
    velocity: { x: 0, y: 0 },
  };
  const sourceBody = frame.ball ?? frame.player ?? fallbackBody;
  return {
    ball: {
      position: {
        x: finite(sourceBody.position?.x),
        y: finite(sourceBody.position?.y),
      },
      velocity: {
        x: finite(sourceBody.velocity?.x),
        y: finite(sourceBody.velocity?.y),
      },
    },
    obstacles: frame.obstacles ?? [],
    accumulator: clamp(finite(frame.accumulator), 0, 0.25),
    distance: Math.max(0, finite(frame.distance)),
    elapsed: Math.max(0, finite(frame.elapsed)),
    overdriveRemaining: Math.max(0, finite(frame.overdriveRemaining)),
    speed: Math.max(0, finite(frame.speed ?? frame.forwardSpeed, 9.5)),
  };
}

function obstacleShape(obstacle: Readonly<BallObstacle>): ObstacleShape {
  return obstacle as unknown as ObstacleShape;
}

function feedbackStrength(event: unknown, fallback: number): number {
  if (typeof event === 'number') {
    return clamp(finite(event, fallback), 0, MAX_FEEDBACK_STRENGTH);
  }
  if (event && typeof event === 'object' && 'strength' in event) {
    return clamp(
      finite((event as { strength?: unknown }).strength, fallback),
      0,
      MAX_FEEDBACK_STRENGTH,
    );
  }
  return fallback;
}

export function signalRunRendererIsSoftware(renderer: string): boolean {
  return /swiftshader|llvmpipe|software raster|software renderer/i.test(renderer);
}

export function signalRunCameraFovAxis(
  width: number,
  height: number,
): 'horizontal' | 'vertical' {
  const safeWidth = Number.isFinite(width) ? Math.max(1, width) : 1;
  const safeHeight = Number.isFinite(height) ? Math.max(1, height) : 1;
  return safeHeight > safeWidth ? 'horizontal' : 'vertical';
}

export function sanitizeSignalRunVisualDelta(deltaSeconds: number): number {
  if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return 0;
  return Math.min(deltaSeconds, MAX_VISUAL_DELTA_SECONDS);
}

export function signalRunVisualLead(
  value: number,
  velocity: number,
  accumulator: number,
): number {
  return finite(value) + finite(velocity) * clamp(finite(accumulator), 0, 0.25);
}

export function signalRunWrappedTunnelZ(
  baseZ: number,
  distance: number,
  loopLength = RIB_LOOP_LENGTH,
): number {
  if (!Number.isFinite(loopLength) || loopLength <= 0) return finite(baseZ);
  return -positiveModulo(-(finite(baseZ) + finite(distance)), loopLength);
}

export function signalRunRibCountForQuality(tier: QualityTier): number {
  return tier === 'performance' ? PERFORMANCE_RIB_COUNT : RIB_CAPACITY;
}

export function signalRunRailCountForQuality(tier: QualityTier): number {
  return tier === 'performance' ? PERFORMANCE_RAIL_COUNT : RAIL_CAPACITY;
}

export function signalRunObstacleVisibleAtZ(z: number): boolean {
  return Number.isFinite(z) && z >= OBSTACLE_FAR_Z && z <= OBSTACLE_NEAR_Z;
}

/**
 * Time until the obstacle's player-facing collision plane reaches the ball.
 * A non-finite result means it is stationary, already at the plane, or behind
 * it. The visual lead mirrors the renderer's fixed-step interpolation only;
 * gameplay collision geometry remains wholly owned by the simulation.
 */
export function signalRunObstacleTimeToContact(
  obstacle: Readonly<BallObstacle>,
  speed: number,
  accumulator = 0,
): number {
  const shape = obstacleShape(obstacle);
  const approachSpeed = Math.max(0, finite(speed));
  if (approachSpeed <= 0) return Number.POSITIVE_INFINITY;
  const visualZ = finite(shape.z) +
    approachSpeed * clamp(finite(accumulator), 0, 0.25);
  const halfDepth = Math.max(0, finite(shape.depth)) * 0.5;
  const ballReach = shape.kind === 'block' ? BALL_RADIUS : 0;
  const remaining = -visualZ - halfDepth - ballReach;
  return remaining > 0
    ? remaining / approachSpeed
    : Number.POSITIVE_INFINITY;
}

/** Selects one nearest active, unresolved obstacle without allocating. */
export function signalRunNearestUpcomingObstacleIndex(
  obstacles: readonly BallObstacle[],
  speed: number,
  accumulator = 0,
): number {
  let selectedIndex = -1;
  let selectedTime = Number.POSITIVE_INFINITY;
  for (let index = 0; index < obstacles.length; index += 1) {
    const obstacle = obstacleShape(obstacles[index]);
    if (
      obstacle.active === false ||
      obstacle.passed === true ||
      obstacle.hit === true ||
      (obstacle.kind !== 'gate' && obstacle.kind !== 'block')
    ) {
      continue;
    }
    const timeToContact = signalRunObstacleTimeToContact(
      obstacles[index],
      speed,
      accumulator,
    );
    if (timeToContact < selectedTime) {
      selectedIndex = index;
      selectedTime = timeToContact;
    }
  }
  return selectedIndex;
}

/** Smoothly grows a cue across its authored warning window. */
export function signalRunTelegraphStrength(
  timeToContact: number,
  telegraphSeconds: number,
): number {
  if (
    !Number.isFinite(timeToContact) ||
    timeToContact < 0 ||
    !Number.isFinite(telegraphSeconds) ||
    telegraphSeconds <= 0 ||
    timeToContact > telegraphSeconds
  ) {
    return 0;
  }
  const progress = clamp(1 - timeToContact / telegraphSeconds, 0, 1);
  const eased = progress * progress * (3 - 2 * progress);
  return TELEGRAPH_MIN_STRENGTH + (1 - TELEGRAPH_MIN_STRENGTH) * eased;
}

/**
 * Solid-route diamonds live on a protected player-side guide plane. Keeping
 * their authored X/Y at a stable depth prevents phone perspective from
 * collapsing an early warning into the ball corona. Gates remain attached to
 * their real aperture because their full ring is already readable at depth.
 */
export function signalRunTelegraphCueZ(
  kind: BallObstacle['kind'],
  obstacleZ: number,
  depth: number,
): number {
  if (kind === 'block') return BLOCK_TELEGRAPH_GUIDE_Z;
  const playerFacingZ = finite(obstacleZ) +
    Math.max(0, finite(depth)) * 0.5 +
    TELEGRAPH_HAZARD_OFFSET;
  return Math.min(TELEGRAPH_BALL_CLEAR_Z, playerFacingZ);
}

export function signalRunDebrisPoolSlot(id: number, capacity: number): number {
  if (!Number.isFinite(id) || !Number.isFinite(capacity) || capacity < 1) {
    return -1;
  }
  return positiveModulo(Math.trunc(id), Math.trunc(capacity));
}

export class SignalRunBabylonScene {
  private readonly host: HTMLElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly engine: AbstractEngine;
  private readonly backend: BabylonRenderBackend;
  private readonly physicsBackend: SignalRunPhysicsBackend;
  private readonly touchFirst: boolean;
  private readonly softwareRenderer: boolean;
  private readonly scene: Scene;
  private readonly camera: FreeCamera;
  private readonly qualityGovernor: QualityGovernor;
  private readonly resizeObserver: SignalRunResizeObserver | null;
  private readonly signal: AbortSignal | undefined;

  private readonly environment: EnvironmentVisual;
  private readonly ball: BallVisual;
  private readonly obstacles: ObstacleVisuals;
  private readonly telegraph: TelegraphVisuals;
  private readonly debris: ThinPool;
  private readonly ballMaterial: PBRMaterial;
  private readonly outlineMaterial: StandardMaterial;
  private readonly coronaMaterial: StandardMaterial;
  private readonly trailMaterial: StandardMaterial;
  private readonly gateMaterial: StandardMaterial;
  private readonly gateCoreMaterial: StandardMaterial;
  private readonly blockMaterial: PBRMaterial;
  private readonly performanceBlockMaterial: StandardMaterial;
  private readonly blockEdgeMaterial: StandardMaterial;
  private readonly debrisMaterial: PBRMaterial;
  private readonly playerLight: PointLight;
  private readonly fxaa: FxaaPostProcess;

  private glowLayer: GlowLayer | null = null;
  private fxaaAttached = true;
  private qualityProfile: QualityProfile;
  private comfortMode: boolean;
  private paused = false;
  private disposed = false;
  private overdriveActive = false;
  private overdrivePulse = 0;
  private impactPulse = 0;
  private gatePulse = 0;
  private visualTime = 0;
  private pixelRatio = 1;
  private activeGates = 0;
  private activeBlocks = 0;
  private activeDebris = 0;

  private readonly matrixScratch = Matrix.Identity();
  private readonly quaternionScratch = Quaternion.Identity();
  private readonly scaleScratch = Vector3.One();
  private readonly positionScratch = Vector3.Zero();
  private readonly cameraTarget = new Vector3(0, 0, -28);
  private readonly cameraFocus = Vector3.Zero();
  private readonly debrisSeen = new Uint8Array(
    SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY,
  );

  static async create(
    host: HTMLElement,
    options: SignalRunBabylonSceneOptions = {},
  ): Promise<SignalRunBabylonScene> {
    if (options.signal?.aborted) throw createAbortError();

    const canvas = host.ownerDocument.createElement('canvas');
    canvas.className = 'signal-run__canvas';
    canvas.style.display = 'block';
    canvas.style.height = '100%';
    canvas.style.touchAction = 'none';
    canvas.style.width = '100%';
    canvas.setAttribute('role', 'application');
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('aria-label', 'Signal Run interactive ball canvas');
    canvas.setAttribute(
      'aria-description',
      'Steer the luminous ball through bright gates and around solid blocks.',
    );
    host.appendChild(canvas);

    let engine: AbstractEngine | null = null;
    let instance: SignalRunBabylonScene | null = null;
    try {
      const selection = await (options.engineFactory ?? defaultEngineFactory)(
        canvas,
        {
          antialias: false,
          powerPreference: 'high-performance',
          stencil: false,
        },
      );
      engine = selection.engine;
      if (options.signal?.aborted) throw createAbortError();
      instance = new SignalRunBabylonScene(host, canvas, selection, options);
      if (options.signal?.aborted) throw createAbortError();
      return instance;
    } catch (error) {
      if (instance) instance.dispose();
      else {
        engine?.dispose();
        canvas.remove();
      }
      throw error;
    }
  }

  private constructor(
    host: HTMLElement,
    canvas: HTMLCanvasElement,
    selection: SignalRunEngineSelection,
    options: SignalRunBabylonSceneOptions,
  ) {
    this.host = host;
    this.canvas = canvas;
    this.engine = selection.engine;
    this.backend = selection.backend;
    this.physicsBackend = options.physicsBackend ?? 'none';
    this.touchFirst = options.touchFirst ?? defaultTouchFirst();
    this.comfortMode = options.comfortMode ?? false;
    this.signal = options.signal;

    let rendererLabel = '';
    if (this.backend === 'webgl') {
      try {
        rendererLabel = (this.engine as Engine).getGlInfo().renderer ?? '';
      } catch {
        // NullEngine and privacy-hardened browsers need no special label.
      }
    }
    this.softwareRenderer = signalRunRendererIsSoftware(rendererLabel);
    this.qualityGovernor = new QualityGovernor(
      this.softwareRenderer
        ? 'performance'
        : initialQualityTier(this.touchFirst),
    );
    this.qualityProfile = this.qualityGovernor.getProfile();

    this.canvas.dataset.playerAvatar = 'ball';
    this.canvas.dataset.ballRadius = BALL_RADIUS.toFixed(3);
    this.canvas.dataset.ballDiameter = SIGNAL_RUN_BALL_DIAMETER.toFixed(3);
    this.canvas.dataset.renderBackend = this.backend;
    this.canvas.dataset.physicsBackend = this.physicsBackend;
    this.canvas.dataset.softwareRenderer = String(this.softwareRenderer);
    this.canvas.dataset.activeGates = '0';
    this.canvas.dataset.activeBlocks = '0';
    this.canvas.dataset.activeDebris = '0';
    this.canvas.dataset.telegraphKind = 'none';
    this.canvas.dataset.telegraphTti = '-1.000';
    this.canvas.dataset.telegraphStrength = '0.000';
    this.canvas.dataset.telegraphGuideZ = '0.000';
    this.canvas.dataset.telegraphScale = '0.000';

    this.scene = new Scene(this.engine);
    this.scene.useRightHandedSystem = true;
    this.scene.clearColor = new Color4(0.004, 0.007, 0.011, 1);
    this.scene.ambientColor = new Color3(0.045, 0.055, 0.065);
    this.scene.fogMode = Scene.FOGMODE_EXP2;
    this.scene.fogDensity = 0.0125;
    this.scene.fogColor = new Color3(0.006, 0.011, 0.017);
    this.scene.skipPointerMovePicking = true;

    this.camera = new FreeCamera(
      'signal-run-camera',
      new Vector3(0, 1.05, 13.5),
      this.scene,
    );
    this.camera.minZ = 0.12;
    this.camera.maxZ = 430;
    this.camera.fov = 1.12;
    this.camera.setTarget(this.cameraTarget);
    this.scene.activeCamera = this.camera;

    const imageProcessing = this.scene.imageProcessingConfiguration;
    imageProcessing.toneMappingEnabled = true;
    imageProcessing.toneMappingType =
      ImageProcessingConfiguration.TONEMAPPING_ACES;
    imageProcessing.exposure = 1.04;
    imageProcessing.contrast = 1.12;
    imageProcessing.vignetteEnabled = true;
    imageProcessing.vignetteStretch = 0.2;
    imageProcessing.vignetteWeight = this.comfortMode ? 1.05 : 1.22;
    imageProcessing.vignetteColor = new Color4(0.002, 0.004, 0.008, 1);

    const ambient = new HemisphericLight(
      'signal-run-ambient',
      new Vector3(0.2, 1, 0.35),
      this.scene,
    );
    ambient.intensity = 0.68;
    ambient.diffuse = new Color3(0.52, 0.66, 0.76);
    ambient.groundColor = new Color3(0.075, 0.022, 0.014);

    this.playerLight = new PointLight(
      'signal-run-ball-light',
      new Vector3(0, 0, 1.35),
      this.scene,
    );
    this.playerLight.diffuse = SIGNAL.clone();
    this.playerLight.specular = SIGNAL_HOT.clone();
    this.playerLight.intensity = 24;
    this.playerLight.range = 22;

    this.environment = this.buildEnvironment();
    const player = this.buildBall();
    this.ball = player.visual;
    this.ballMaterial = player.ballMaterial;
    this.outlineMaterial = player.outlineMaterial;
    this.coronaMaterial = player.coronaMaterial;
    this.trailMaterial = player.trailMaterial;

    const obstacles = this.buildObstacles();
    this.obstacles = obstacles.visuals;
    this.gateMaterial = obstacles.gateMaterial;
    this.gateCoreMaterial = obstacles.gateCoreMaterial;
    this.blockMaterial = obstacles.blockMaterial;
    this.performanceBlockMaterial = obstacles.performanceBlockMaterial;
    this.blockEdgeMaterial = obstacles.blockEdgeMaterial;

    this.telegraph = this.buildTelegraph();

    const debris = this.buildDebris();
    this.debris = debris.pool;
    this.debrisMaterial = debris.material;

    this.fxaa = new FxaaPostProcess(
      'signal-run-fxaa',
      1,
      this.camera,
      Texture.BILINEAR_SAMPLINGMODE,
      this.engine,
      false,
    );

    this.applyQuality(this.qualityProfile);
    const resizeObserverFactory = options.resizeObserverFactory ??
      this.defaultResizeObserverFactory();
    this.resizeObserver = resizeObserverFactory
      ? resizeObserverFactory(() => this.resize())
      : null;
    this.resizeObserver?.observe(this.host);
    this.resize();

    this.signal?.addEventListener('abort', this.dispose, { once: true });
    if (this.signal?.aborted) this.dispose();
  }

  private defaultResizeObserverFactory(): SignalRunResizeObserverFactory | null {
    const ResizeObserverConstructor = this.host.ownerDocument.defaultView
      ?.ResizeObserver;
    if (!ResizeObserverConstructor) return null;
    return (callback) => new ResizeObserverConstructor(callback);
  }

  private buildEnvironment(): EnvironmentVisual {
    const panelTexture = new Texture(
      SIGNAL_RUN_ASSETS.panelAlbedo,
      this.scene,
      true,
      false,
      Texture.TRILINEAR_SAMPLINGMODE,
    );
    panelTexture.wrapU = Texture.WRAP_ADDRESSMODE;
    panelTexture.wrapV = Texture.WRAP_ADDRESSMODE;
    panelTexture.uScale = 3;
    panelTexture.vScale = 20;
    panelTexture.anisotropicFilteringLevel = this.touchFirst ? 2 : 6;

    const panelMaterial = new PBRMaterial('signal-run-panel-pbr', this.scene);
    panelMaterial.albedoTexture = panelTexture;
    panelMaterial.albedoColor = new Color3(0.42, 0.46, 0.48);
    panelMaterial.metallic = 0.74;
    panelMaterial.roughness = 0.42;
    panelMaterial.emissiveColor = new Color3(0.012, 0.018, 0.022);
    panelMaterial.backFaceCulling = false;

    const tunnel = CreateCylinder(
      'signal-run-panel-tunnel',
      {
        diameter: TUNNEL_RADIUS * 2,
        height: TUNNEL_LENGTH,
        tessellation: this.touchFirst ? 24 : 32,
        subdivisions: 1,
      },
      this.scene,
    );
    tunnel.rotation.x = Math.PI / 2;
    tunnel.position.z = -TUNNEL_LENGTH * 0.43;
    tunnel.material = panelMaterial;
    tunnel.isPickable = false;

    const veinTexture = new Texture(
      SIGNAL_RUN_ASSETS.veinMask,
      this.scene,
      true,
      false,
      Texture.BILINEAR_SAMPLINGMODE,
    );
    veinTexture.wrapU = Texture.WRAP_ADDRESSMODE;
    veinTexture.wrapV = Texture.WRAP_ADDRESSMODE;
    veinTexture.uScale = 3;
    veinTexture.vScale = 14;

    const veinMaterial = new StandardMaterial(
      'signal-run-vein-material',
      this.scene,
    );
    veinMaterial.diffuseColor = BLACK.clone();
    veinMaterial.emissiveColor = new Color3(0.18, 0.08, 0.045);
    veinMaterial.opacityTexture = veinTexture;
    veinMaterial.alpha = 0.28;
    veinMaterial.alphaMode = Constants.ALPHA_ADD;
    veinMaterial.backFaceCulling = false;
    veinMaterial.disableLighting = true;
    veinMaterial.disableDepthWrite = true;

    const veins = CreateCylinder(
      'signal-run-vein-shell',
      {
        diameter: TUNNEL_RADIUS * 2 - 0.16,
        height: TUNNEL_LENGTH - 1,
        tessellation: this.touchFirst ? 24 : 32,
        subdivisions: 1,
      },
      this.scene,
    );
    veins.rotation.x = Math.PI / 2;
    veins.position.z = tunnel.position.z;
    veins.material = veinMaterial;
    veins.isPickable = false;

    const ribMaterial = new PBRMaterial('signal-run-rib-pbr', this.scene);
    ribMaterial.albedoColor = new Color3(0.13, 0.14, 0.15);
    ribMaterial.metallic = 0.9;
    ribMaterial.roughness = 0.3;
    ribMaterial.emissiveColor = new Color3(0.035, 0.022, 0.018);
    const ribMesh = CreateTorus(
      'signal-run-rib-pool',
      {
        diameter: TUNNEL_RADIUS * 2 - 0.65,
        thickness: 0.17,
        tessellation: this.touchFirst ? 20 : 28,
      },
      this.scene,
    );
    ribMesh.material = ribMaterial;
    ribMesh.isPickable = false;
    const ribs = makeThinPool(ribMesh, RIB_CAPACITY);

    const railMaterial = new StandardMaterial(
      'signal-run-rail-material',
      this.scene,
    );
    railMaterial.diffuseColor = SIGNAL_DARK.clone();
    railMaterial.emissiveColor = new Color3(0.12, 0.045, 0.025);
    const railMesh = CreateBox(
      'signal-run-rail-pool',
      { width: 0.07, height: 0.07, depth: RAIL_SEGMENT_LENGTH * 0.72 },
      this.scene,
    );
    railMesh.material = railMaterial;
    railMesh.isPickable = false;
    const rails = makeThinPool(railMesh, RAIL_CAPACITY);

    const performancePanelMaterial = new StandardMaterial(
      'signal-run-panel-performance',
      this.scene,
    );
    performancePanelMaterial.emissiveTexture = panelTexture;
    performancePanelMaterial.diffuseColor = BLACK.clone();
    performancePanelMaterial.specularColor = BLACK.clone();
    performancePanelMaterial.emissiveColor = new Color3(0.11, 0.12, 0.13);
    performancePanelMaterial.backFaceCulling = false;
    performancePanelMaterial.disableLighting = true;

    const performanceRibMaterial = new StandardMaterial(
      'signal-run-rib-performance',
      this.scene,
    );
    performanceRibMaterial.diffuseColor = BLACK.clone();
    performanceRibMaterial.specularColor = BLACK.clone();
    performanceRibMaterial.emissiveColor = new Color3(0.03, 0.038, 0.044);
    performanceRibMaterial.disableLighting = true;

    return {
      tunnel,
      veins,
      ribs,
      rails,
      panelTexture,
      veinTexture,
      panelMaterial,
      ribMaterial,
      performancePanelMaterial,
      performanceRibMaterial,
      veinMaterial,
      railMaterial,
    };
  }

  private buildBall() {
    const root = new TransformNode('signal-run-ball-root', this.scene);

    const ballMaterial = new PBRMaterial('signal-run-ball-pbr', this.scene);
    ballMaterial.albedoColor = new Color3(0.18, 0.2, 0.22);
    ballMaterial.metallic = 0.54;
    ballMaterial.roughness = 0.18;
    setColorScaled(ballMaterial.emissiveColor, SIGNAL, 0.52);

    const shell = CreateSphere(
      'signal-run-player-ball',
      {
        diameter: SIGNAL_RUN_BALL_DIAMETER,
        segments: this.touchFirst ? 16 : 20,
      },
      this.scene,
    );
    shell.material = ballMaterial;
    shell.parent = root;
    shell.isPickable = false;

    const outlineMaterial = new StandardMaterial(
      'signal-run-ball-outline-material',
      this.scene,
    );
    outlineMaterial.diffuseColor = BLACK.clone();
    outlineMaterial.emissiveColor = SIGNAL_HOT.clone();
    outlineMaterial.disableLighting = true;

    const outline = CreateTorus(
      'signal-run-ball-outline',
      {
        diameter: SIGNAL_RUN_BALL_DIAMETER * 1.08,
        thickness: Math.max(0.035, BALL_RADIUS * 0.13),
        tessellation: this.touchFirst ? 14 : 20,
      },
      this.scene,
    );
    outline.rotation.x = Math.PI / 2;
    outline.material = outlineMaterial;
    outline.parent = root;
    outline.isPickable = false;

    const coronaMaterial = new StandardMaterial(
      'signal-run-ball-corona-material',
      this.scene,
    );
    coronaMaterial.diffuseColor = BLACK.clone();
    coronaMaterial.emissiveColor = SIGNAL.clone();
    coronaMaterial.alpha = 0.13;
    coronaMaterial.alphaMode = Constants.ALPHA_ADD;
    coronaMaterial.disableLighting = true;
    coronaMaterial.disableDepthWrite = true;

    const corona = CreateSphere(
      'signal-run-ball-corona',
      {
        diameter: SIGNAL_RUN_BALL_DIAMETER * 1.45,
        segments: this.touchFirst ? 10 : 12,
      },
      this.scene,
    );
    corona.material = coronaMaterial;
    corona.parent = root;
    corona.isPickable = false;

    const trailMaterial = new StandardMaterial(
      'signal-run-speed-trail-material',
      this.scene,
    );
    trailMaterial.diffuseColor = BLACK.clone();
    trailMaterial.emissiveColor = SIGNAL.clone();
    trailMaterial.alpha = 0.5;
    trailMaterial.alphaMode = Constants.ALPHA_ADD;
    trailMaterial.disableLighting = true;
    trailMaterial.disableDepthWrite = true;

    const trailPath = Array.from(
      { length: TRAIL_POINT_COUNT },
      (_, index) => new Vector3(0, 0, 0.22 + index * 0.34),
    );
    const trail = CreateTube(
      'signal-run-speed-trail',
      {
        path: trailPath,
        radius: this.touchFirst ? 0.06 : 0.052,
        tessellation: 6,
        cap: Mesh.CAP_ALL,
        updatable: true,
      },
      this.scene,
    );
    trail.material = trailMaterial;
    trail.parent = root;
    trail.isPickable = false;

    return {
      visual: { root, shell, outline, corona, trail, trailPath },
      ballMaterial,
      outlineMaterial,
      coronaMaterial,
      trailMaterial,
    };
  }

  private buildObstacles() {
    const gateMaterial = new StandardMaterial(
      'signal-run-gate-material',
      this.scene,
    );
    gateMaterial.diffuseColor = new Color3(0.018, 0.105, 0.13);
    gateMaterial.specularColor = new Color3(0.42, 0.78, 0.9);
    gateMaterial.specularPower = 96;
    gateMaterial.emissiveColor = new Color3(0.025, 0.22, 0.28);

    // With diameter 2.28 and thickness .28 the unit torus has an inner radius
    // of exactly 1. Scaling X/Y by an authored gate radius preserves the true
    // traversable opening. The substantial dark-metal rim stays legible even
    // after the renderer lowers its pixel ratio on a slower phone.
    const gateMesh = CreateTorus(
      'signal-run-gate-pool',
      {
        diameter: 2.28,
        thickness: 0.28,
        tessellation: this.touchFirst ? 28 : 40,
      },
      this.scene,
    );
    gateMesh.material = gateMaterial;
    gateMesh.isPickable = false;
    const gates = makeThinPool(gateMesh, SIGNAL_RUN_GATE_VISUAL_CAPACITY);

    // A separate narrow inner edge provides the crisp aperture boundary. It
    // deliberately does not rely on bloom, which made the old one-piece gate
    // look soft and reduced the apparent clearance of the opening.
    const gateCoreMaterial = new StandardMaterial(
      'signal-run-gate-core-material',
      this.scene,
    );
    gateCoreMaterial.diffuseColor = new Color3(0.08, 0.28, 0.34);
    gateCoreMaterial.emissiveColor = new Color3(0.72, 0.96, 1);
    gateCoreMaterial.disableLighting = true;
    const gateCoreMesh = CreateTorus(
      'signal-run-gate-core-pool',
      {
        diameter: 2.12,
        thickness: 0.07,
        tessellation: this.touchFirst ? 28 : 40,
      },
      this.scene,
    );
    gateCoreMesh.material = gateCoreMaterial;
    gateCoreMesh.isPickable = false;
    const gateCores = makeThinPool(
      gateCoreMesh,
      SIGNAL_RUN_GATE_VISUAL_CAPACITY,
    );

    const blockMaterial = new PBRMaterial(
      'signal-run-block-pbr',
      this.scene,
    );
    blockMaterial.albedoColor = new Color3(0.105, 0.075, 0.055);
    blockMaterial.metallic = 0.76;
    blockMaterial.roughness = 0.24;
    blockMaterial.emissiveColor = new Color3(0.105, 0.025, 0.008);
    const blockMesh = CreateBox(
      'signal-run-block-pool',
      { size: 1 },
      this.scene,
    );
    blockMesh.material = blockMaterial;
    blockMesh.isPickable = false;
    const blocks = makeThinPool(blockMesh, SIGNAL_RUN_BLOCK_VISUAL_CAPACITY);

    const performanceBlockMaterial = new StandardMaterial(
      'signal-run-block-performance',
      this.scene,
    );
    performanceBlockMaterial.diffuseColor = new Color3(0.075, 0.045, 0.03);
    performanceBlockMaterial.specularColor = BLACK.clone();
    performanceBlockMaterial.emissiveColor = new Color3(0.11, 0.028, 0.008);

    const blockEdgeMaterial = new StandardMaterial(
      'signal-run-block-edge-material',
      this.scene,
    );
    blockEdgeMaterial.diffuseColor = BLACK.clone();
    blockEdgeMaterial.emissiveColor = BLOCK_WARNING.clone();
    blockEdgeMaterial.disableLighting = true;
    blockEdgeMaterial.wireframe = true;
    const blockEdgeMesh = CreateBox(
      'signal-run-block-edge-pool',
      { size: 1 },
      this.scene,
    );
    blockEdgeMesh.material = blockEdgeMaterial;
    blockEdgeMesh.isPickable = false;
    const blockEdges = makeThinPool(
      blockEdgeMesh,
      SIGNAL_RUN_BLOCK_VISUAL_CAPACITY,
    );

    return {
      visuals: { gates, gateCores, blocks, blockEdges },
      gateMaterial,
      gateCoreMaterial,
      blockMaterial,
      performanceBlockMaterial,
      blockEdgeMaterial,
    };
  }

  private buildTelegraph(): TelegraphVisuals {
    const gateMaterial = new StandardMaterial(
      'signal-run-gate-telegraph-material',
      this.scene,
    );
    gateMaterial.diffuseColor = BLACK.clone();
    gateMaterial.emissiveColor = GATE_SIGNAL.clone();
    gateMaterial.alpha = 0;
    gateMaterial.alphaMode = Constants.ALPHA_ADD;
    gateMaterial.disableLighting = true;
    gateMaterial.disableDepthWrite = true;

    // The round cue marks the complete ball-center clearance of an aperture,
    // not a second collision ring. It sits just player-side of the real gate.
    const gateReticle = CreateTorus(
      'signal-run-gate-telegraph',
      {
        diameter: 2.12,
        thickness: 0.12,
        tessellation: this.touchFirst ? 16 : 24,
      },
      this.scene,
    );
    gateReticle.material = gateMaterial;
    gateReticle.rotation.x = Math.PI / 2;
    gateReticle.isPickable = false;
    gateReticle.setEnabled(false);

    const blockMaterial = new StandardMaterial(
      'signal-run-block-telegraph-material',
      this.scene,
    );
    blockMaterial.diffuseColor = BLACK.clone();
    blockMaterial.emissiveColor = BLOCK_SAFE_SIGNAL.clone();
    blockMaterial.alpha = 0;
    blockMaterial.alphaMode = Constants.ALPHA_ADD;
    blockMaterial.disableLighting = true;
    blockMaterial.disableDepthWrite = true;

    // Four segments read as a diamond-shaped safe-route marker, keeping solid
    // warnings structurally and chromatically distinct from circular gates.
    const blockReticle = CreateTorus(
      'signal-run-block-telegraph',
      {
        diameter: 1.72,
        thickness: 0.12,
        tessellation: 4,
      },
      this.scene,
    );
    blockReticle.material = blockMaterial;
    blockReticle.rotation.x = Math.PI / 2;
    blockReticle.rotation.z = Math.PI / 4;
    blockReticle.isPickable = false;
    blockReticle.setEnabled(false);

    return { gateReticle, blockReticle, gateMaterial, blockMaterial };
  }

  private buildDebris() {
    const material = new PBRMaterial('signal-run-debris-pbr', this.scene);
    material.albedoColor = new Color3(0.17, 0.12, 0.095);
    material.metallic = 0.72;
    material.roughness = 0.34;
    material.emissiveColor = new Color3(0.07, 0.018, 0.008);
    const mesh = CreatePolyhedron(
      'signal-run-debris-pool',
      { type: 1, size: 0.18 },
      this.scene,
    );
    mesh.material = material;
    mesh.isPickable = false;
    return {
      material,
      pool: makeThinPool(mesh, SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY),
    };
  }

  private rebuildGlowLayer(profile: QualityProfile) {
    this.glowLayer?.dispose();
    this.glowLayer = null;
    const glow = new GlowLayer('signal-run-protected-glow', this.scene, {
      blurKernelSize: profile.postProcessing === 'essential'
        ? 6
        : this.touchFirst ? 12 : 20,
      mainTextureRatio: profile.glowTextureRatio,
    });
    glow.intensity = profile.postProcessing === 'essential'
      ? 0.5
      : this.comfortMode
        ? 0.58
        : this.touchFirst ? 0.72 : 0.82;
    glow.addExcludedMesh(this.environment.tunnel);
    glow.addExcludedMesh(this.environment.veins);
    // Keep obstacle geometry sharp. Telegraphs and the ball retain bloom, but
    // the physical opening and solid collision boundary must not be blurred.
    glow.addExcludedMesh(this.obstacles.gates.mesh);
    glow.addExcludedMesh(this.obstacles.gateCores.mesh);
    glow.addExcludedMesh(this.obstacles.blocks.mesh);
    glow.addExcludedMesh(this.obstacles.blockEdges.mesh);
    if (profile.postProcessing === 'essential') {
      for (const mesh of [
        this.ball.shell,
        this.ball.outline,
        this.ball.corona,
        this.ball.trail,
        this.telegraph.gateReticle,
        this.telegraph.blockReticle,
      ]) {
        glow.addIncludedOnlyMesh(mesh);
      }
    }
    this.glowLayer = glow;
  }

  private applyQuality(profile: QualityProfile) {
    this.qualityProfile = profile;
    const essential = profile.postProcessing === 'essential';
    this.canvas.dataset.qualityTier = profile.tier;
    this.canvas.dataset.materialMode = essential ? 'standard' : 'pbr';
    this.environment.tunnel.material = essential
      ? this.environment.performancePanelMaterial
      : this.environment.panelMaterial;
    this.environment.ribs.mesh.material = essential
      ? this.environment.performanceRibMaterial
      : this.environment.ribMaterial;
    this.obstacles.blocks.mesh.material = essential
      ? this.performanceBlockMaterial
      : this.blockMaterial;
    this.environment.veins.setEnabled(!essential);
    this.scene.imageProcessingConfiguration.exposure = essential ? 0.97 : 1.04;
    this.playerLight.intensity = essential ? 13 : profile.tier === 'balanced' ? 20 : 24;
    this.playerLight.range = essential ? 16 : 22;
    this.coronaMaterial.alpha = essential ? 0.18 : 0.13;
    const shouldUseFxaa = !essential;
    if (shouldUseFxaa && !this.fxaaAttached) {
      this.camera.attachPostProcess(this.fxaa);
      this.fxaaAttached = true;
    } else if (!shouldUseFxaa && this.fxaaAttached) {
      this.camera.detachPostProcess(this.fxaa);
      this.fxaaAttached = false;
    }
    this.rebuildGlowLayer(profile);
    this.resize();
  }

  private writeTransform(
    pool: ThinPool,
    index: number,
    position: Vector3,
    rotation: Quaternion,
    scale: Vector3,
  ) {
    Matrix.ComposeToRef(scale, rotation, position, this.matrixScratch);
    this.matrixScratch.copyToArray(pool.matrices, index * 16);
  }

  private updateEnvironment(frame: AdaptedFrame) {
    const leadDistance = frame.distance + frame.speed * frame.accumulator;
    const ribCount = signalRunRibCountForQuality(this.qualityProfile.tier);
    this.quaternionScratch.set(
      Math.SQRT1_2,
      0,
      0,
      Math.SQRT1_2,
    );
    this.scaleScratch.setAll(1);
    for (let index = 0; index < ribCount; index += 1) {
      const sourceIndex = this.qualityProfile.tier === 'performance'
        ? index * 2
        : index;
      this.positionScratch.set(
        0,
        0,
        signalRunWrappedTunnelZ(
          -8 - sourceIndex * RIB_SPACING,
          leadDistance,
        ),
      );
      this.writeTransform(
        this.environment.ribs,
        index,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }
    hideUnusedThinInstances(this.environment.ribs, ribCount);
    updateThinPool(this.environment.ribs, ribCount);

    const railCount = signalRunRailCountForQuality(this.qualityProfile.tier);
    for (let index = 0; index < railCount; index += 1) {
      const lane = index % 4;
      const segment = Math.floor(index / 4);
      const angle = lane * Math.PI * 0.5 + 0.2;
      this.positionScratch.set(
        Math.cos(angle) * (TUNNEL_RADIUS - 0.72),
        Math.sin(angle) * (TUNNEL_RADIUS - 0.72),
        signalRunWrappedTunnelZ(
          -28 - segment * RAIL_SEGMENT_LENGTH,
          leadDistance,
        ),
      );
      this.quaternionScratch.set(0, 0, Math.sin(angle / 2), Math.cos(angle / 2));
      this.scaleScratch.setAll(1);
      this.writeTransform(
        this.environment.rails,
        index,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }
    hideUnusedThinInstances(this.environment.rails, railCount);
    updateThinPool(this.environment.rails, railCount);
    this.canvas.dataset.activeRibs = String(ribCount);
    this.canvas.dataset.activeRails = String(railCount);

    this.environment.panelTexture.vOffset = positiveModulo(
      leadDistance / 90,
      1,
    );
    this.environment.veinTexture.vOffset = positiveModulo(
      leadDistance / 72,
      1,
    );
  }

  private updateBall(frame: AdaptedFrame, deltaSeconds: number) {
    const visualX = signalRunVisualLead(
      frame.ball.position.x,
      frame.ball.velocity.x,
      frame.accumulator,
    );
    const visualY = signalRunVisualLead(
      frame.ball.position.y,
      frame.ball.velocity.y,
      frame.accumulator,
    );
    this.canvas.dataset.ballX = visualX.toFixed(3);
    this.canvas.dataset.ballY = visualY.toFixed(3);
    this.ball.root.position.set(visualX, visualY, PLAYER_Z);

    // Only the faceted shell rolls. Its geometric diameter and collision cue
    // never stretch, even while the non-colliding corona absorbs an impact.
    this.ball.shell.rotation.x +=
      frame.ball.velocity.y * deltaSeconds / Math.max(BALL_RADIUS, 0.001);
    this.ball.shell.rotation.y -=
      frame.ball.velocity.x * deltaSeconds / Math.max(BALL_RADIUS, 0.001);
    this.ball.shell.scaling.setAll(1);
    this.ball.outline.rotation.x = Math.PI / 2 + Math.sin(this.visualTime) * 0.18;
    this.ball.outline.rotation.z = this.visualTime * 1.25;

    const impact = this.impactPulse;
    this.ball.corona.scaling.set(
      1 + impact * 0.24 + this.gatePulse * 0.07,
      Math.max(0.72, 1 - impact * 0.13 + this.gatePulse * 0.07),
      1 + impact * 0.16 + this.overdrivePulse * 0.16,
    );

    const speedRatio = clamp((frame.speed - 8) / 26, 0, 1);
    const motionSpeedRatio = this.comfortMode ? 0 : speedRatio;
    const motionOverdrive = this.comfortMode
      ? this.overdrivePulse * 0.18
      : this.overdrivePulse;
    const trailLength = 1.4 + motionSpeedRatio * 2.25 + motionOverdrive * 1.25;
    const bendX = -frame.ball.velocity.x * 0.055;
    const bendY = -frame.ball.velocity.y * 0.055;
    for (let index = 0; index < TRAIL_POINT_COUNT; index += 1) {
      const t = index / (TRAIL_POINT_COUNT - 1);
      const curve = t * t;
      this.ball.trailPath[index].set(
        bendX * curve,
        bendY * curve,
        0.18 + trailLength * t,
      );
    }
    CreateTube(
      'signal-run-speed-trail',
      {
        path: this.ball.trailPath,
        radius: this.touchFirst ? 0.06 : 0.052,
        tessellation: 6,
        cap: Mesh.CAP_ALL,
        instance: this.ball.trail,
      },
      this.scene,
    );
    this.trailMaterial.alpha = clamp(
      0.3 + motionSpeedRatio * 0.34 + motionOverdrive * 0.25,
      0.3,
      0.94,
    );
    this.coronaMaterial.alpha = clamp(
      (this.qualityProfile.postProcessing === 'essential' ? 0.18 : 0.13) +
        this.gatePulse * 0.08 + this.overdrivePulse * 0.09,
      0.1,
      0.42,
    );
    setColorScaled(
      this.ballMaterial.emissiveColor,
      this.overdrivePulse > 0.05 ? SIGNAL_HOT : SIGNAL,
      0.52 + this.gatePulse * 0.22 + this.overdrivePulse * 0.28,
    );
    setColorScaled(
      this.outlineMaterial.emissiveColor,
      this.overdrivePulse > 0.05 ? SIGNAL_HOT : SIGNAL,
      0.9 + this.gatePulse * 0.3,
    );

    this.playerLight.position.set(visualX, visualY, 1.35);
    this.playerLight.intensity =
      (this.qualityProfile.postProcessing === 'essential' ? 13 : 22) +
      this.gatePulse * 8 + this.overdrivePulse * 10;

    const focusBlend = 1 - Math.exp(-Math.max(0, deltaSeconds) * 6.2);
    this.cameraFocus.x += (visualX - this.cameraFocus.x) * focusBlend;
    this.cameraFocus.y += (visualY - this.cameraFocus.y) * focusBlend;
    const motionScale = this.comfortMode ? 0.15 : 1;
    const shake = this.impactPulse * 0.12 * motionScale;
    this.camera.position.x = this.cameraFocus.x * 0.12 +
      Math.sin(this.visualTime * 43) * shake;
    this.camera.position.y = 1.05 + this.cameraFocus.y * 0.12 +
      Math.cos(this.visualTime * 37) * shake * 0.7;
    this.camera.position.z = 13.5;
    this.cameraTarget.set(
      this.cameraFocus.x * 0.24,
      this.cameraFocus.y * 0.24,
      -28,
    );
    this.camera.setTarget(this.cameraTarget);
    this.camera.fov = this.comfortMode
      ? 1.14
      : 1.1 + speedRatio * 0.1 + this.overdrivePulse * 0.035;
  }

  private updateObstacles(frame: AdaptedFrame) {
    let gateCount = 0;
    let blockCount = 0;
    for (const rawObstacle of frame.obstacles) {
      const obstacle = obstacleShape(rawObstacle);
      if (obstacle.active === false || obstacle.passed === true) continue;
      const z = finite(obstacle.z) + frame.speed * frame.accumulator;
      if (!signalRunObstacleVisibleAtZ(z)) continue;
      const x = finite(obstacle.x);
      const y = finite(obstacle.y);

      if (obstacle.kind === 'gate' || obstacle.kind === 'aperture') {
        if (gateCount >= SIGNAL_RUN_GATE_VISUAL_CAPACITY) continue;
        const radius = Math.max(
          BALL_RADIUS * 1.45,
          finite(obstacle.openingRadius ?? obstacle.radius, 2.4),
        );
        this.positionScratch.set(x, y, z);
        this.quaternionScratch.set(
          Math.SQRT1_2,
          0,
          0,
          Math.SQRT1_2,
        );
        this.scaleScratch.set(radius, radius, 1);
        this.writeTransform(
          this.obstacles.gates,
          gateCount,
          this.positionScratch,
          this.quaternionScratch,
          this.scaleScratch,
        );
        this.writeTransform(
          this.obstacles.gateCores,
          gateCount,
          this.positionScratch,
          this.quaternionScratch,
          this.scaleScratch,
        );
        gateCount += 1;
        continue;
      }

      if (obstacle.kind !== 'block' || blockCount >= SIGNAL_RUN_BLOCK_VISUAL_CAPACITY) {
        continue;
      }
      const width = Math.max(0.1, finite(obstacle.width, 1));
      const height = Math.max(0.1, finite(obstacle.height, 1));
      const depth = Math.max(0.1, finite(obstacle.depth, 1));
      this.positionScratch.set(x, y, z);
      this.quaternionScratch.set(0, 0, 0, 1);
      this.scaleScratch.set(width, height, depth);
      this.writeTransform(
        this.obstacles.blocks,
        blockCount,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
      this.scaleScratch.set(width * 1.025, height * 1.025, depth * 1.025);
      this.writeTransform(
        this.obstacles.blockEdges,
        blockCount,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
      blockCount += 1;
    }

    hideUnusedThinInstances(this.obstacles.gates, gateCount);
    hideUnusedThinInstances(this.obstacles.gateCores, gateCount);
    hideUnusedThinInstances(this.obstacles.blocks, blockCount);
    hideUnusedThinInstances(this.obstacles.blockEdges, blockCount);
    updateThinPool(this.obstacles.gates, gateCount);
    updateThinPool(this.obstacles.gateCores, gateCount);
    updateThinPool(this.obstacles.blocks, blockCount);
    updateThinPool(this.obstacles.blockEdges, blockCount);
    this.activeGates = gateCount;
    this.activeBlocks = blockCount;
    this.canvas.dataset.activeGates = String(gateCount);
    this.canvas.dataset.activeBlocks = String(blockCount);
  }

  private hideTelegraph() {
    this.telegraph.gateReticle.setEnabled(false);
    this.telegraph.blockReticle.setEnabled(false);
    this.telegraph.gateMaterial.alpha = 0;
    this.telegraph.blockMaterial.alpha = 0;
    this.canvas.dataset.telegraphKind = 'none';
    this.canvas.dataset.telegraphTti = '-1.000';
    this.canvas.dataset.telegraphStrength = '0.000';
    this.canvas.dataset.telegraphObstacle = '';
    this.canvas.dataset.telegraphSafeX = '0.000';
    this.canvas.dataset.telegraphSafeY = '0.000';
    this.canvas.dataset.telegraphGuideZ = '0.000';
    this.canvas.dataset.telegraphScale = '0.000';
  }

  private updateTelegraph(frame: AdaptedFrame) {
    const selectedIndex = signalRunNearestUpcomingObstacleIndex(
      frame.obstacles,
      frame.speed,
      frame.accumulator,
    );
    if (selectedIndex < 0) {
      this.hideTelegraph();
      return;
    }

    const rawObstacle = frame.obstacles[selectedIndex];
    const obstacle = obstacleShape(rawObstacle);
    const timeToContact = signalRunObstacleTimeToContact(
      rawObstacle,
      frame.speed,
      frame.accumulator,
    );
    const strength = signalRunTelegraphStrength(
      timeToContact,
      finite(obstacle.telegraphSeconds),
    );
    const safeX = finite(obstacle.safePoint?.x, finite(obstacle.x));
    const safeY = finite(obstacle.safePoint?.y, finite(obstacle.y));
    if (strength <= 0 || !Number.isFinite(safeX) || !Number.isFinite(safeY)) {
      this.hideTelegraph();
      return;
    }

    const visualStrength = strength * (this.comfortMode ? 0.42 : 1);
    const visualZ = finite(obstacle.z) + frame.speed * frame.accumulator;
    const cueZ = signalRunTelegraphCueZ(
      obstacle.kind as BallObstacle['kind'],
      visualZ,
      finite(obstacle.depth),
    );
    const alpha = clamp(0.08 + visualStrength * 0.58, 0.08, 0.66);

    this.canvas.dataset.telegraphKind = obstacle.kind;
    this.canvas.dataset.telegraphTti = timeToContact.toFixed(3);
    this.canvas.dataset.telegraphStrength = visualStrength.toFixed(3);
    this.canvas.dataset.telegraphObstacle = obstacle.id ?? '';
    this.canvas.dataset.telegraphSafeX = safeX.toFixed(3);
    this.canvas.dataset.telegraphSafeY = safeY.toFixed(3);
    this.canvas.dataset.telegraphGuideZ = cueZ.toFixed(3);

    if (obstacle.kind === 'gate') {
      const safeRadius = Math.max(
        BALL_RADIUS * 0.72,
        finite(obstacle.openingRadius ?? obstacle.radius, 2.4) - BALL_RADIUS,
      );
      const breathe = this.comfortMode
        ? 1
        : 1 + Math.sin(this.visualTime * 4.4) * 0.018 * visualStrength;
      this.telegraph.blockReticle.setEnabled(false);
      this.telegraph.blockMaterial.alpha = 0;
      this.telegraph.gateReticle.setEnabled(true);
      this.telegraph.gateReticle.position.set(safeX, safeY, cueZ);
      this.telegraph.gateReticle.scaling.setAll(safeRadius * breathe);
      this.canvas.dataset.telegraphScale = (safeRadius * breathe).toFixed(3);
      this.telegraph.gateReticle.rotation.z = this.comfortMode
        ? 0
        : this.visualTime * 0.16;
      this.telegraph.gateMaterial.alpha = alpha;
      return;
    }

    this.telegraph.gateReticle.setEnabled(false);
    this.telegraph.gateMaterial.alpha = 0;
    this.telegraph.blockReticle.setEnabled(true);
    this.telegraph.blockReticle.position.set(safeX, safeY, cueZ);
    const blockScale = 0.9 + visualStrength * 0.16;
    this.telegraph.blockReticle.scaling.setAll(blockScale);
    this.canvas.dataset.telegraphScale = blockScale.toFixed(3);
    this.telegraph.blockReticle.rotation.z = Math.PI / 4 + (
      this.comfortMode ? 0 : Math.sin(this.visualTime * 2.8) * 0.06
    );
    this.telegraph.blockMaterial.alpha = alpha;
  }

  private updateQuality(deltaSeconds: number, promotionBoundary: boolean) {
    if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return;
    const frameTimeMs = deltaSeconds * 1_000;
    const decision = this.qualityGovernor.observe({
      frameTimeMs,
      sampleDurationMs: frameTimeMs,
      promotionBoundary,
    });
    if (decision.changed) this.applyQuality(decision.profile);
  }

  render(
    simulation: Readonly<BallSimulation>,
    deltaSeconds: number,
    promotionBoundary = false,
  ): void {
    if (this.disposed || this.paused) return;
    this.updateQuality(deltaSeconds, promotionBoundary);
    const visualDelta = sanitizeSignalRunVisualDelta(deltaSeconds);
    this.visualTime += visualDelta;
    this.impactPulse = Math.max(0, this.impactPulse - visualDelta * 3.3);
    this.gatePulse = Math.max(0, this.gatePulse - visualDelta * 2.6);
    const overdriveTarget = this.overdriveActive ? 1 : 0;
    this.overdrivePulse +=
      (overdriveTarget - this.overdrivePulse) *
      Math.min(1, visualDelta * (this.overdriveActive ? 5.5 : 2.8));

    const frame = adaptSimulation(simulation);
    this.overdriveActive = frame.overdriveRemaining > 0;
    this.updateBall(frame, visualDelta);
    this.updateObstacles(frame);
    this.updateTelegraph(frame);
    this.updateEnvironment(frame);
    if (this.glowLayer) {
      const base = this.qualityProfile.postProcessing === 'essential'
        ? 0.5
        : this.comfortMode ? 0.58 : this.touchFirst ? 0.72 : 0.82;
      this.glowLayer.intensity = base + this.gatePulse * 0.12 +
        this.overdrivePulse * 0.1;
    }
    this.scene.render();
    this.canvas.dataset.activeIndices = String(this.scene.getActiveIndices());
    this.updateRenderDimensionDatasets();
  }

  syncDebris(
    source: (visit: (pose: Readonly<SignalRunDebrisPose>) => void) => void,
  ): void;
  syncDebris(source: Iterable<Readonly<SignalRunDebrisPose>>): void;
  syncDebris(source: SignalRunDebrisSource): void {
    if (this.disposed) return;
    this.debrisSeen.fill(0);
    let accepted = 0;
    const budget = Math.min(
      this.qualityProfile.debrisBudget,
      SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY,
    );
    const visit = (pose: Readonly<SignalRunDebrisPose>) => {
      if (accepted >= budget) return;
      const slot = signalRunDebrisPoolSlot(pose.id, SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY);
      if (slot < 0 || this.debrisSeen[slot]) return;
      this.debrisSeen[slot] = 1;
      this.positionScratch.set(
        finite(pose.position.x),
        finite(pose.position.y),
        finite(pose.position.z),
      );
      this.quaternionScratch.set(
        finite(pose.rotation.x),
        finite(pose.rotation.y),
        finite(pose.rotation.z),
        finite(pose.rotation.w, 1),
      );
      const sleepingScale = pose.sleeping ? 0.72 : 1;
      this.scaleScratch.set(
        0.34 * sleepingScale,
        0.18 * sleepingScale,
        0.46 * sleepingScale,
      );
      this.writeTransform(
        this.debris,
        accepted,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
      accepted += 1;
    };
    if (typeof source === 'function') source(visit);
    else for (const pose of source) visit(pose);

    hideUnusedThinInstances(this.debris, accepted);
    updateThinPool(this.debris, accepted);
    this.activeDebris = accepted;
    this.canvas.dataset.activeDebris = String(accepted);
  }

  impact(event?: Readonly<BallImpactEvent> | number): void {
    if (this.disposed) return;
    this.impactPulse = Math.max(
      this.impactPulse,
      feedbackStrength(event, event && typeof event === 'object' && event.crashed ? 1.6 : 1),
    );
  }

  gate(event?: Readonly<BallGateEvent> | number): void {
    if (this.disposed) return;
    const semanticStrength = event && typeof event === 'object'
      ? event.result === 'clean'
        ? event.nearMiss ? 1.35 : 1.08
        : 0.72
      : 1;
    this.gatePulse = Math.max(
      this.gatePulse,
      feedbackStrength(event, semanticStrength),
    );
  }

  overdrive(active = true): void {
    if (this.disposed) return;
    this.overdriveActive = active;
    if (active) this.overdrivePulse = Math.max(this.overdrivePulse, 0.42);
  }

  private updateRenderDimensionDatasets() {
    this.canvas.dataset.renderWidth = String(this.engine.getRenderWidth());
    this.canvas.dataset.renderHeight = String(this.engine.getRenderHeight());
  }

  resize(): void {
    if (this.disposed) return;
    const bounds = this.host.getBoundingClientRect();
    const width = Math.max(
      1,
      Math.floor(
        this.host.clientWidth || bounds.width || this.canvas.clientWidth || 1,
      ),
    );
    const height = Math.max(
      1,
      Math.floor(
        this.host.clientHeight || bounds.height || this.canvas.clientHeight || 1,
      ),
    );
    const devicePixelRatio = this.host.ownerDocument.defaultView
      ?.devicePixelRatio ?? 1;
    const fovAxis = signalRunCameraFovAxis(width, height);
    this.camera.fovMode = fovAxis === 'horizontal'
      ? Camera.FOVMODE_HORIZONTAL_FIXED
      : Camera.FOVMODE_VERTICAL_FIXED;
    this.pixelRatio = renderPixelRatioForQuality({
      width,
      height,
      devicePixelRatio,
      touchFirst: this.touchFirst,
      tier: this.qualityProfile.tier,
    });
    this.engine.setHardwareScalingLevel(
      hardwareScalingLevelForPixelRatio(this.pixelRatio),
    );
    // resize() lets Babylon derive the drawing buffer from CSS size and the
    // inverse hardware scale. setSize(width, height) would silently restore a
    // native-size buffer and make the performance tier cosmetic.
    this.engine.resize(true);
    this.canvas.dataset.pixelRatio = this.pixelRatio.toFixed(3);
    this.canvas.dataset.fovAxis = fovAxis;
    this.updateRenderDimensionDatasets();
  }

  setComfortMode(enabled: boolean): void {
    if (this.disposed) return;
    this.comfortMode = enabled;
    this.scene.imageProcessingConfiguration.vignetteWeight = enabled
      ? 1.05
      : 1.22;
    this.rebuildGlowLayer(this.qualityProfile);
  }

  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
  }

  resume(): void {
    if (this.disposed || !this.paused) return;
    this.paused = false;
    this.qualityGovernor.resetEvidence();
  }

  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  getDiagnostics(): SignalRunBabylonDiagnostics {
    return {
      renderBackend: this.backend,
      physicsBackend: this.physicsBackend,
      qualityTier: this.qualityProfile.tier,
      pixelRatio: this.pixelRatio,
      renderWidth: this.engine.getRenderWidth(),
      renderHeight: this.engine.getRenderHeight(),
      ballDiameter: SIGNAL_RUN_BALL_DIAMETER,
      gateCapacity: SIGNAL_RUN_GATE_VISUAL_CAPACITY,
      blockCapacity: SIGNAL_RUN_BLOCK_VISUAL_CAPACITY,
      debrisCapacity: SIGNAL_RUN_DEBRIS_VISUAL_CAPACITY,
      activeGates: this.activeGates,
      activeBlocks: this.activeBlocks,
      activeDebris: this.activeDebris,
      paused: this.paused,
      disposed: this.disposed,
    };
  }

  dispose = (): void => {
    if (this.disposed) return;
    this.disposed = true;
    this.paused = true;
    this.signal?.removeEventListener('abort', this.dispose);
    this.resizeObserver?.disconnect();
    this.glowLayer?.dispose();
    this.glowLayer = null;
    this.fxaa.dispose();
    this.environment.panelTexture.dispose();
    this.environment.veinTexture.dispose();
    this.scene.dispose();
    this.engine.dispose();
    this.canvas.remove();
  };
}
