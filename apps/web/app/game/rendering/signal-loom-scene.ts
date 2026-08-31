import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { Constants } from '@babylonjs/core/Engines/constants.js';
import type { Engine } from '@babylonjs/core/Engines/engine.js';
import type { WebGPUEngine } from '@babylonjs/core/Engines/webgpuEngine.js';
import { Camera } from '@babylonjs/core/Cameras/camera.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { GlowLayer } from '@babylonjs/core/Layers/glowLayer.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { PointLight } from '@babylonjs/core/Lights/pointLight.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import { Matrix, Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { ImageProcessingConfiguration } from '@babylonjs/core/Materials/imageProcessingConfiguration.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture.js';
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
import { ParticleSystem } from '@babylonjs/core/Particles/particleSystem.js';
import { FxaaPostProcess } from '@babylonjs/core/PostProcesses/fxaaPostProcess.js';
import { Scene } from '@babylonjs/core/scene.js';

import {
  LOOM_ANCHOR_POOL_SIZE,
  type LoomArc,
  type LoomPhase,
  type LoomSimulation,
  type LoomStitchEvent,
} from '../loom-simulation';
import type { RapierDebrisPose } from '../physics/rapier-physics';
import {
  createBabylonEngine,
  type BabylonEngineFactoryOptions,
  type BabylonRenderBackend,
} from './babylon-engine-factory';
import {
  hardwareScalingLevelForPixelRatio,
  initialQualityTier,
  QualityGovernor,
  qualityProfileForTier,
  renderPixelRatioForQuality,
  type QualityProfile,
  type QualityTier,
} from './quality-governor';

export const SIGNAL_LOOM_ASSETS = Object.freeze({
  panelAlbedo: '/game/loom-panels-albedo.webp',
  veinMask: '/game/loom-veins-mask.webp',
} as const);

export const SIGNAL_LOOM_ANCHOR_VISUAL_CAPACITY = LOOM_ANCHOR_POOL_SIZE;
export const SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY = 32;

const TUNNEL_RADIUS = 9.45;
const TUNNEL_LENGTH = 390;
const PLAYER_Z = 0;
const ECHO_Z = 2.35;
const RIB_COUNT = 24;
const RIB_SPACING = 15;
const RIB_LOOP_LENGTH = RIB_COUNT * RIB_SPACING;
const RAIL_LANES = 4;
const RAIL_SEGMENTS_PER_LANE = 6;
const RAIL_SEGMENT_COUNT = RAIL_LANES * RAIL_SEGMENTS_PER_LANE;
const RAIL_SEGMENT_LENGTH = RIB_LOOP_LENGTH / RAIL_SEGMENTS_PER_LANE;
const IRIS_BLADE_COUNT = 12;
const THREAD_POINT_COUNT = 14;
const MAX_VISUAL_DELTA_SECONDS = 0.05;
const MAX_FEEDBACK_STRENGTH = 2;

const EMBER = Color3.FromHexString('#ff6a45');
const EMBER_DARK = Color3.FromHexString('#42150f');
const COBALT = Color3.FromHexString('#53a1ff');
const COBALT_DARK = Color3.FromHexString('#10264d');
const WARM_WHITE = Color3.FromHexString('#f1e4d1');
const BLACK = Color3.Black();

export type SignalLoomPhysicsBackend = 'rapier' | 'none';
export type SignalLoomPhaseShape = 'diamond' | 'ring';

export interface SignalLoomArcVisualProfile {
  fogDensity: number;
  ribRotationRate: number;
  railSpiral: number;
  veinBoost: number;
  warmBlend: number;
  irisVisible: boolean;
}

const ARC_VISUAL_PROFILES: Readonly<Record<LoomArc, SignalLoomArcVisualProfile>> =
  Object.freeze({
    1: Object.freeze({
      fogDensity: 0.013,
      ribRotationRate: 0.018,
      railSpiral: 0,
      veinBoost: 0,
      warmBlend: 0,
      irisVisible: false,
    }),
    2: Object.freeze({
      fogDensity: 0.0145,
      ribRotationRate: 0.042,
      railSpiral: 0.16,
      veinBoost: 0.08,
      warmBlend: 0,
      irisVisible: false,
    }),
    3: Object.freeze({
      fogDensity: 0.017,
      ribRotationRate: 0.078,
      railSpiral: 0.29,
      veinBoost: 0.16,
      warmBlend: 0,
      irisVisible: true,
    }),
    4: Object.freeze({
      fogDensity: 0.0095,
      ribRotationRate: 0.115,
      railSpiral: 0.42,
      veinBoost: 0.26,
      warmBlend: 0.28,
      irisVisible: true,
    }),
  });

export function signalLoomArcVisualProfile(
  arc: LoomArc,
): Readonly<SignalLoomArcVisualProfile> {
  return ARC_VISUAL_PROFILES[arc] ?? ARC_VISUAL_PROFILES[1];
}

export function signalLoomRibCountForQuality(tier: QualityTier): number {
  return tier === 'performance' ? 6 : RIB_COUNT;
}

export function signalLoomRailCountForQuality(tier: QualityTier): number {
  return tier === 'performance' ? 8 : RAIL_SEGMENT_COUNT;
}

export function signalLoomRendererIsSoftware(renderer: string): boolean {
  return /swiftshader|llvmpipe|software raster|software renderer/i.test(renderer);
}

export function signalLoomCameraFovAxis(
  width: number,
  height: number,
): 'horizontal' | 'vertical' {
  const safeWidth = Number.isFinite(width) ? Math.max(1, width) : 1;
  const safeHeight = Number.isFinite(height) ? Math.max(1, height) : 1;
  return safeHeight > safeWidth ? 'horizontal' : 'vertical';
}

export function signalLoomIrisGapScale(gapRadius: number): number {
  return Math.max(0.05, gapRadius / 2.9);
}

export function signalLoomIrisBladeCenterRadius(gapRadius: number): number {
  return Math.max(0, gapRadius) + 1.62;
}

export function signalLoomIrisCueStrength(
  stage: LoomSimulation['iris']['stage'],
  z: number,
  intensity: number,
): number {
  if (stage === 'telegraph' || stage === 'approach') {
    return Math.max(0, Math.min(1, intensity));
  }
  if (stage === 'close') {
    return Math.max(0, Math.min(1, -z / 24));
  }
  return 0;
}

export function signalLoomAnchorVisibleAtZ(
  z: number,
  tier: QualityTier,
): boolean {
  if (!Number.isFinite(z)) return false;
  const farPlane = tier === 'performance' ? -95 : -180;
  return z >= farPlane && z <= 18;
}

export interface SignalLoomEngineSelection {
  engine: AbstractEngine;
  backend: BabylonRenderBackend;
}

export type SignalLoomEngineFactory = (
  canvas: HTMLCanvasElement,
  options?: BabylonEngineFactoryOptions,
) => Promise<SignalLoomEngineSelection>;

export interface SignalLoomResizeObserver {
  observe(target: Element): void;
  disconnect(): void;
}

export type SignalLoomResizeObserverFactory = (
  callback: ResizeObserverCallback,
) => SignalLoomResizeObserver;

export interface SignalLoomSceneOptions {
  /** Abort this during React effect cleanup to dispose a late WebGPU result. */
  signal?: AbortSignal;
  touchFirst?: boolean;
  comfortMode?: boolean;
  physicsBackend?: SignalLoomPhysicsBackend;
  engineFactory?: SignalLoomEngineFactory;
  resizeObserverFactory?: SignalLoomResizeObserverFactory;
}

export interface SignalLoomSceneDiagnostics {
  renderBackend: BabylonRenderBackend;
  physicsBackend: SignalLoomPhysicsBackend;
  qualityTier: QualityTier;
  activeDebris: number;
  pixelRatio: number;
  anchorCapacity: number;
  debrisCapacity: number;
  paused: boolean;
  disposed: boolean;
}

export type SignalLoomDebrisSource =
  | Iterable<Readonly<RapierDebrisPose>>
  | ((visit: (pose: Readonly<RapierDebrisPose>) => void) => void);

export type SignalLoomStitchFeedback = Pick<
  LoomStitchEvent,
  'phase' | 'expressive' | 'nearMiss'
>;

interface ThinPool {
  mesh: Mesh;
  matrices: Float32Array;
}

interface AnchorPools {
  ember: ThinPool;
  cobalt: ThinPool;
  safe: ThinPool;
  expressive: ThinPool;
}

interface IrisVisual {
  root: TransformNode;
  ring: Mesh;
  core: Mesh;
  blades: ThinPool;
  material: PBRMaterial;
  coreMaterial: StandardMaterial;
  cueRoot: TransformNode;
  cueRing: Mesh;
  cueTicks: ThinPool;
  cueMaterial: StandardMaterial;
}

interface PlayerVisual {
  root: TransformNode;
  hull: Mesh;
  core: Mesh;
  echoRoot: TransformNode;
  echoRing: Mesh;
  echoCore: Mesh;
  thread: Mesh;
  threadPath: Vector3[];
}

const defaultEngineFactory: SignalLoomEngineFactory = async (
  canvas,
  options,
) => createBabylonEngine<WebGPUEngine, Engine>(canvas, options);

function defaultTouchFirst(): boolean {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
    ? window.matchMedia('(hover: none), (pointer: coarse)').matches
    : false;
}

function createAbortError() {
  if (typeof DOMException === 'function') {
    return new DOMException('Signal Loom scene creation was aborted.', 'AbortError');
  }
  const error = new Error('Signal Loom scene creation was aborted.');
  error.name = 'AbortError';
  return error;
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

function copyMatrixToPool(matrix: Matrix, pool: ThinPool, index: number) {
  matrix.copyToArray(pool.matrices, index * 16);
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
  pool.mesh.thinInstanceCount = Math.max(
    0,
    Math.min(Math.trunc(activeCount), pool.matrices.length / 16),
  );
  pool.mesh.thinInstanceBufferUpdated('matrix');
}

export function signalLoomPhaseShape(
  phase: LoomPhase,
): SignalLoomPhaseShape {
  return phase === 'ember' ? 'diamond' : 'ring';
}

export function sanitizeLoomVisualDelta(deltaSeconds: number): number {
  if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return 0;
  return Math.min(deltaSeconds, MAX_VISUAL_DELTA_SECONDS);
}

/** Moves geometry toward the camera and wraps it without frame-rate drift. */
export function wrappedLoomTunnelZ(
  baseZ: number,
  distance: number,
  loopLength: number,
  frontZ = 12,
): number {
  const safeLoopLength = Number.isFinite(loopLength)
    ? Math.max(1, loopLength)
    : 1;
  const safeBase = Number.isFinite(baseZ) ? baseZ : 0;
  const safeDistance = Number.isFinite(distance) ? distance : 0;
  const minimumZ = frontZ - safeLoopLength;
  return minimumZ + positiveModulo(
    safeBase + safeDistance - minimumZ,
    safeLoopLength,
  );
}

export function signalLoomDebrisPoolSlot(id: number, capacity: number): number {
  if (!Number.isFinite(id) || !Number.isFinite(capacity) || capacity < 1) {
    return -1;
  }
  return positiveModulo(Math.trunc(id), Math.trunc(capacity));
}

export class SignalLoomScene {
  private readonly host: HTMLElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly engine: AbstractEngine;
  private readonly backend: BabylonRenderBackend;
  private readonly physicsBackend: SignalLoomPhysicsBackend;
  private readonly touchFirst: boolean;
  private readonly softwareRenderer: boolean;
  private readonly scene: Scene;
  private readonly camera: FreeCamera;
  private readonly qualityGovernor: QualityGovernor;
  private readonly resizeObserver: SignalLoomResizeObserver | null;
  private readonly signal: AbortSignal | undefined;

  private readonly tunnel: Mesh;
  private readonly veinShell: Mesh;
  private readonly panelMaterial: PBRMaterial;
  private readonly ribMaterial: PBRMaterial;
  private readonly performancePanelMaterial: StandardMaterial;
  private readonly performanceRibMaterial: StandardMaterial;
  private readonly panelTexture: Texture;
  private readonly veinTexture: Texture;
  private readonly veinMaterial: StandardMaterial;
  private readonly railMaterial: StandardMaterial;
  private readonly phaseLight: PointLight;
  private readonly needleMaterial: PBRMaterial;
  private readonly phaseMaterial: StandardMaterial;
  private readonly echoMaterial: StandardMaterial;
  private readonly threadMaterial: StandardMaterial;
  private readonly debrisMaterial: PBRMaterial;
  private readonly player: PlayerVisual;
  private readonly anchors: AnchorPools;
  private readonly ribs: ThinPool;
  private readonly rails: ThinPool;
  private readonly iris: IrisVisual;
  private readonly debris: ThinPool;
  private readonly particleTexture: RawTexture;
  private readonly particles: ParticleSystem;
  private readonly fxaa: FxaaPostProcess;
  private fxaaAttached = true;

  private glowLayer: GlowLayer | null = null;
  private comfortMode: boolean;
  private paused = false;
  private disposed = false;
  private visualTime = 0;
  private pixelRatio = 1;
  private activeDebris = 0;
  private impactPulse = 0;
  private stitchPulse = 0;
  private resonancePulse = 0;
  private resonanceActive = false;
  private lastStitchSequence = 0;
  private lastMissedAnchors = 0;
  private lastThreadBreaks = 0;
  private currentPhase: LoomPhase = 'ember';
  private qualityProfile: QualityProfile;

  private readonly debrisSeen = new Uint8Array(
    SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
  );
  private readonly matrixScratch = Matrix.Identity();
  private readonly quaternionScratch = Quaternion.Identity();
  private readonly scaleScratch = Vector3.One();
  private readonly positionScratch = Vector3.Zero();
  private readonly cameraTarget = new Vector3(0, 0, -28);
  private readonly cameraFocus = Vector3.Zero();
  private readonly cueCenterWorld = Vector3.Zero();
  private readonly cueEdgeWorld = Vector3.Zero();
  private readonly cueCenterScreen = Vector3.Zero();
  private readonly cueEdgeScreen = Vector3.Zero();

  static async create(
    host: HTMLElement,
    options: SignalLoomSceneOptions = {},
  ): Promise<SignalLoomScene> {
    if (options.signal?.aborted) throw createAbortError();

    const canvas = host.ownerDocument.createElement('canvas');
    canvas.className = 'signal-loom__canvas';
    canvas.setAttribute('role', 'application');
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute(
      'aria-label',
      'Signal Loom interactive flight canvas',
    );
    canvas.setAttribute(
      'aria-description',
      'Steer the Needle, manage the luminous Thread, and match anchor phase shapes.',
    );
    host.appendChild(canvas);

    let engine: AbstractEngine | null = null;
    let instance: SignalLoomScene | null = null;
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

      instance = new SignalLoomScene(
        host,
        canvas,
        selection,
        options,
      );
      if (options.signal?.aborted) throw createAbortError();
      return instance;
    } catch (error) {
      if (instance) {
        instance.dispose();
      } else {
        engine?.dispose();
        canvas.remove();
      }
      throw error;
    }
  }

  private constructor(
    host: HTMLElement,
    canvas: HTMLCanvasElement,
    selection: SignalLoomEngineSelection,
    options: SignalLoomSceneOptions,
  ) {
    this.host = host;
    this.canvas = canvas;
    this.engine = selection.engine;
    this.backend = selection.backend;
    this.physicsBackend = options.physicsBackend ?? 'none';
    this.touchFirst = options.touchFirst ?? defaultTouchFirst();
    let rendererLabel = '';
    if (this.backend === 'webgl') {
      try {
        rendererLabel = (this.engine as Engine).getGlInfo().renderer ?? '';
      } catch {
        // NullEngine and hardened browsers may intentionally hide GL details.
      }
    }
    this.softwareRenderer = signalLoomRendererIsSoftware(rendererLabel);
    this.canvas.dataset.softwareRenderer = this.softwareRenderer
      ? 'true'
      : 'false';
    this.comfortMode = options.comfortMode ?? false;
    this.signal = options.signal;
    this.qualityGovernor = new QualityGovernor(
      this.softwareRenderer
        ? 'performance'
        : initialQualityTier(this.touchFirst),
    );
    this.qualityProfile = this.qualityGovernor.getProfile();

    this.canvas.dataset.renderBackend = this.backend;
    this.canvas.dataset.physicsBackend = this.physicsBackend;
    this.canvas.dataset.activeDebris = '0';

    this.scene = new Scene(this.engine);
    // The camera looks down -Z. A right-handed scene keeps +X visually right,
    // so Right/D on both keyboard and touch never feels mirrored.
    this.scene.useRightHandedSystem = true;
    this.scene.clearColor = new Color4(0.006, 0.009, 0.012, 1);
    this.scene.ambientColor = new Color3(0.055, 0.065, 0.075);
    this.scene.fogMode = Scene.FOGMODE_EXP2;
    this.scene.fogDensity = 0.013;
    this.scene.fogColor = new Color3(0.009, 0.014, 0.019);
    this.scene.skipPointerMovePicking = true;

    this.camera = new FreeCamera(
      'loom-camera',
      new Vector3(0, 1.05, 13.5),
      this.scene,
    );
    this.camera.minZ = 0.12;
    this.camera.maxZ = 430;
    this.camera.fov = 1.16;
    this.camera.setTarget(this.cameraTarget);
    this.scene.activeCamera = this.camera;

    const imageProcessing = this.scene.imageProcessingConfiguration;
    imageProcessing.toneMappingEnabled = true;
    imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
    imageProcessing.exposure = 1.03;
    imageProcessing.contrast = 1.1;
    imageProcessing.vignetteEnabled = true;
    imageProcessing.vignetteStretch = 0.18;
    imageProcessing.vignetteWeight = 1.28;
    imageProcessing.vignetteColor = new Color4(0.004, 0.006, 0.009, 1);

    const ambientLight = new HemisphericLight(
      'loom-ambient',
      new Vector3(0.2, 1, 0.35),
      this.scene,
    );
    ambientLight.intensity = 0.72;
    ambientLight.diffuse = new Color3(0.56, 0.68, 0.75);
    ambientLight.groundColor = new Color3(0.08, 0.025, 0.018);

    this.phaseLight = new PointLight(
      'loom-phase-light',
      new Vector3(-4, 4, -20),
      this.scene,
    );
    this.phaseLight.diffuse = EMBER.clone();
    this.phaseLight.specular = WARM_WHITE.clone();
    this.phaseLight.intensity = 46;
    this.phaseLight.range = 74;

    const coldFill = new PointLight(
      'loom-cold-fill',
      new Vector3(5, -3, -62),
      this.scene,
    );
    coldFill.diffuse = new Color3(0.2, 0.42, 0.68);
    coldFill.specular = new Color3(0.34, 0.48, 0.7);
    coldFill.intensity = 28;
    coldFill.range = 105;

    const environment = this.buildTunnel();
    this.tunnel = environment.tunnel;
    this.veinShell = environment.veinShell;
    this.panelMaterial = environment.tunnelMaterial;
    this.ribMaterial = environment.ribMaterial;
    this.panelTexture = environment.panelTexture;
    this.veinTexture = environment.veinTexture;
    this.veinMaterial = environment.veinMaterial;
    this.railMaterial = environment.railMaterial;
    this.ribs = environment.ribs;
    this.rails = environment.rails;
    const fallbackEnvironment = this.buildPerformanceEnvironmentMaterials();
    this.performancePanelMaterial = fallbackEnvironment.panel;
    this.performanceRibMaterial = fallbackEnvironment.rib;

    const player = this.buildPlayer();
    this.player = player.visual;
    this.needleMaterial = player.needleMaterial;
    this.phaseMaterial = player.phaseMaterial;
    this.echoMaterial = player.echoMaterial;
    this.threadMaterial = player.threadMaterial;

    this.anchors = this.buildAnchors();
    this.iris = this.buildIris();
    const debris = this.buildDebris();
    this.debris = debris.pool;
    this.debrisMaterial = debris.material;

    const particleVisual = this.buildParticles();
    this.particleTexture = particleVisual.texture;
    this.particles = particleVisual.system;

    this.fxaa = new FxaaPostProcess(
      'loom-fxaa',
      1,
      this.camera,
      Texture.BILINEAR_SAMPLINGMODE,
      this.engine,
      false,
    );

    this.applyPhase('ember');
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

  private defaultResizeObserverFactory(): SignalLoomResizeObserverFactory | null {
    const ResizeObserverConstructor = this.host.ownerDocument.defaultView
      ?.ResizeObserver;
    if (!ResizeObserverConstructor) return null;
    return (callback) => new ResizeObserverConstructor(callback);
  }

  private buildTunnel() {
    const panelTexture = new Texture(
      SIGNAL_LOOM_ASSETS.panelAlbedo,
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

    const tunnelMaterial = new PBRMaterial('loom-panel-pbr', this.scene);
    tunnelMaterial.albedoTexture = panelTexture;
    tunnelMaterial.albedoColor = new Color3(0.47, 0.5, 0.51);
    tunnelMaterial.metallic = 0.76;
    tunnelMaterial.roughness = 0.39;
    tunnelMaterial.emissiveColor = new Color3(0.018, 0.024, 0.026);
    tunnelMaterial.backFaceCulling = false;

    const tunnel = CreateCylinder(
      'loom-panel-tunnel',
      {
        height: TUNNEL_LENGTH,
        diameter: TUNNEL_RADIUS * 2,
        tessellation: this.touchFirst ? 36 : 48,
        subdivisions: 1,
        sideOrientation: Mesh.BACKSIDE,
      },
      this.scene,
    );
    tunnel.rotation.x = Math.PI / 2;
    tunnel.position.z = -TUNNEL_LENGTH / 2 + 12;
    tunnel.material = tunnelMaterial;
    tunnel.isPickable = false;

    const veinTexture = new Texture(
      SIGNAL_LOOM_ASSETS.veinMask,
      this.scene,
      true,
      false,
      Texture.TRILINEAR_SAMPLINGMODE,
    );
    veinTexture.wrapU = Texture.WRAP_ADDRESSMODE;
    veinTexture.wrapV = Texture.WRAP_ADDRESSMODE;
    veinTexture.uScale = 3;
    veinTexture.vScale = 20;
    veinTexture.hasAlpha = true;
    veinTexture.getAlphaFromRGB = true;
    veinTexture.anisotropicFilteringLevel = this.touchFirst ? 2 : 4;

    const veinMaterial = new StandardMaterial(
      'loom-additive-veins',
      this.scene,
    );
    veinMaterial.diffuseColor = BLACK.clone();
    veinMaterial.emissiveColor = EMBER.clone();
    veinMaterial.emissiveTexture = veinTexture;
    veinMaterial.opacityTexture = veinTexture;
    veinMaterial.alpha = 0.5;
    veinMaterial.alphaMode = Constants.ALPHA_ADD;
    veinMaterial.backFaceCulling = false;
    veinMaterial.disableLighting = true;
    veinMaterial.disableDepthWrite = true;

    const veinShell = CreateCylinder(
      'loom-vein-shell',
      {
        height: TUNNEL_LENGTH - 0.5,
        diameter: TUNNEL_RADIUS * 2 - 0.06,
        tessellation: this.touchFirst ? 36 : 48,
        subdivisions: 1,
        sideOrientation: Mesh.BACKSIDE,
      },
      this.scene,
    );
    veinShell.rotation.x = Math.PI / 2;
    veinShell.position.copyFrom(tunnel.position);
    veinShell.material = veinMaterial;
    veinShell.isPickable = false;

    const ribMaterial = new PBRMaterial('loom-rib-pbr', this.scene);
    ribMaterial.albedoColor = new Color3(0.06, 0.075, 0.08);
    ribMaterial.metallic = 0.9;
    ribMaterial.roughness = 0.34;
    ribMaterial.emissiveColor = new Color3(0.012, 0.018, 0.02);

    const ribMesh = CreateTorus(
      'loom-rib-pool',
      {
        diameter: TUNNEL_RADIUS * 2 - 0.18,
        thickness: 0.28,
        // The faceted silhouette is intentional projection machinery and cuts
        // the dominant index cost by an order of magnitude on fallback GPUs.
        tessellation: 12,
      },
      this.scene,
    );
    ribMesh.material = ribMaterial;
    ribMesh.isPickable = false;
    const ribs = makeThinPool(ribMesh, RIB_COUNT);

    const railMaterial = new StandardMaterial('loom-rail-glow', this.scene);
    railMaterial.diffuseColor = EMBER_DARK.clone();
    railMaterial.emissiveColor = new Color3(0.45, 0.12, 0.06);
    railMaterial.disableLighting = false;

    const railMesh = CreateBox(
      'loom-rail-segment-pool',
      { size: 1 },
      this.scene,
    );
    railMesh.material = railMaterial;
    railMesh.isPickable = false;
    const rails = makeThinPool(railMesh, RAIL_SEGMENT_COUNT);

    return {
      panelTexture,
      railMaterial,
      rails,
      ribMaterial,
      ribs,
      tunnel,
      tunnelMaterial,
      veinMaterial,
      veinShell,
      veinTexture,
    };
  }

  private buildPerformanceEnvironmentMaterials() {
    const panel = new StandardMaterial(
      'loom-panel-performance',
      this.scene,
    );
    // One dark unlit albedo sample is dramatically cheaper than PBR and keeps
    // fallback devices inside the same cinematic world without being washed
    // white by the gameplay lights.
    panel.emissiveTexture = this.panelTexture;
    panel.diffuseColor = BLACK.clone();
    panel.specularColor = BLACK.clone();
    panel.emissiveColor = new Color3(0.13, 0.14, 0.15);
    panel.backFaceCulling = false;
    panel.disableLighting = true;

    const rib = new StandardMaterial('loom-rib-performance', this.scene);
    rib.diffuseColor = BLACK.clone();
    rib.specularColor = BLACK.clone();
    rib.emissiveColor = new Color3(0.035, 0.045, 0.05);
    rib.disableLighting = true;

    return { panel, rib };
  }

  private buildPlayer() {
    const root = new TransformNode('loom-needle-root', this.scene);

    const needleMaterial = new PBRMaterial('loom-needle-pbr', this.scene);
    needleMaterial.albedoColor = new Color3(0.37, 0.39, 0.4);
    needleMaterial.metallic = 0.88;
    needleMaterial.roughness = 0.24;
    needleMaterial.emissiveColor = new Color3(0.12, 0.035, 0.018);

    const hull = CreateCylinder(
      'loom-needle',
      {
        height: 2.8,
        diameterTop: 0.08,
        diameterBottom: 0.72,
        tessellation: 16,
      },
      this.scene,
    );
    hull.rotation.x = -Math.PI / 2;
    hull.material = needleMaterial;
    hull.parent = root;
    hull.isPickable = false;

    const wing = CreateBox(
      'loom-needle-wing',
      { width: 2.15, height: 0.09, depth: 0.62 },
      this.scene,
    );
    wing.position.z = 0.34;
    wing.material = needleMaterial;
    wing.parent = root;
    wing.isPickable = false;

    const fin = CreateBox(
      'loom-needle-fin',
      { width: 0.09, height: 1.22, depth: 0.54 },
      this.scene,
    );
    fin.position.z = 0.42;
    fin.material = needleMaterial;
    fin.parent = root;
    fin.isPickable = false;

    const phaseMaterial = new StandardMaterial(
      'loom-needle-phase-core',
      this.scene,
    );
    phaseMaterial.diffuseColor = EMBER_DARK.clone();
    phaseMaterial.emissiveColor = EMBER.clone();
    phaseMaterial.disableLighting = true;

    const core = CreateSphere(
      'loom-needle-core',
      { diameter: 0.48, segments: 12 },
      this.scene,
    );
    core.position.z = 1.08;
    core.scaling.y = 0.52;
    core.material = phaseMaterial;
    core.parent = root;
    core.isPickable = false;

    const tailHalo = CreateTorus(
      'loom-needle-tail-halo',
      { diameter: 0.86, thickness: 0.075, tessellation: 18 },
      this.scene,
    );
    tailHalo.position.z = 1.43;
    tailHalo.rotation.x = Math.PI / 2;
    tailHalo.material = phaseMaterial;
    tailHalo.parent = root;
    tailHalo.isPickable = false;

    const echoRoot = new TransformNode('loom-echo-root', this.scene);
    const echoMaterial = new StandardMaterial('loom-echo-material', this.scene);
    echoMaterial.diffuseColor = BLACK.clone();
    echoMaterial.emissiveColor = new Color3(0.7, 0.25, 0.1);
    echoMaterial.alpha = 0.7;
    echoMaterial.alphaMode = Constants.ALPHA_ADD;
    echoMaterial.disableLighting = true;
    echoMaterial.disableDepthWrite = true;

    const echoRing = CreateTorus(
      'loom-echo-ring',
      { diameter: 1.05, thickness: 0.105, tessellation: 18 },
      this.scene,
    );
    echoRing.rotation.x = Math.PI / 2;
    echoRing.material = echoMaterial;
    echoRing.parent = echoRoot;
    echoRing.isPickable = false;

    const echoCore = CreatePolyhedron(
      'loom-echo-core',
      { type: 1, size: 0.25 },
      this.scene,
    );
    echoCore.material = echoMaterial;
    echoCore.parent = echoRoot;
    echoCore.isPickable = false;

    const threadMaterial = new StandardMaterial(
      'loom-thread-material',
      this.scene,
    );
    threadMaterial.diffuseColor = BLACK.clone();
    threadMaterial.emissiveColor = EMBER.clone();
    threadMaterial.alpha = 0.9;
    threadMaterial.alphaMode = Constants.ALPHA_ADD;
    threadMaterial.disableLighting = true;
    threadMaterial.disableDepthWrite = true;

    const threadPath = Array.from(
      { length: THREAD_POINT_COUNT },
      (_, index) => new Vector3(0, 0, ECHO_Z * (1 - index / (THREAD_POINT_COUNT - 1))),
    );
    const thread = CreateTube(
      'loom-thread',
      {
        path: threadPath,
        radius: this.touchFirst ? 0.05 : 0.042,
        tessellation: 6,
        cap: Mesh.CAP_ALL,
        updatable: true,
      },
      this.scene,
    );
    thread.material = threadMaterial;
    thread.isPickable = false;

    return {
      visual: {
        root,
        hull,
        core,
        echoRoot,
        echoRing,
        echoCore,
        thread,
        threadPath,
      },
      needleMaterial,
      phaseMaterial,
      echoMaterial,
      threadMaterial,
    };
  }

  private buildAnchors(): AnchorPools {
    const emberMaterial = new StandardMaterial(
      'loom-anchor-ember-material',
      this.scene,
    );
    emberMaterial.diffuseColor = EMBER_DARK.clone();
    emberMaterial.emissiveColor = EMBER.clone();

    const cobaltMaterial = new StandardMaterial(
      'loom-anchor-cobalt-material',
      this.scene,
    );
    cobaltMaterial.diffuseColor = COBALT_DARK.clone();
    cobaltMaterial.emissiveColor = COBALT.clone();

    const routeMaterial = new StandardMaterial(
      'loom-anchor-route-material',
      this.scene,
    );
    routeMaterial.diffuseColor = new Color3(0.11, 0.12, 0.12);
    routeMaterial.emissiveColor = new Color3(0.48, 0.43, 0.34);
    routeMaterial.alpha = 0.82;

    // Ember is a faceted diamond; Cobalt is an open ring. Phase remains
    // readable in monochrome, peripheral vision, and common color deficiencies.
    const emberGlyph = CreatePolyhedron(
      'loom-anchor-ember-diamond-pool',
      { type: 1, size: 0.72 },
      this.scene,
    );
    emberGlyph.material = emberMaterial;
    emberGlyph.isPickable = false;

    const cobaltGlyph = CreateTorus(
      'loom-anchor-cobalt-ring-pool',
      {
        diameter: 1.42,
        thickness: 0.18,
        tessellation: this.touchFirst ? 12 : 16,
      },
      this.scene,
    );
    cobaltGlyph.material = cobaltMaterial;
    cobaltGlyph.isPickable = false;

    const safeGlyph = CreateSphere(
      'loom-anchor-safe-dot-pool',
      { diameter: 0.23, segments: 6 },
      this.scene,
    );
    safeGlyph.material = routeMaterial;
    safeGlyph.isPickable = false;

    const expressiveGlyph = CreateTorus(
      'loom-anchor-expressive-orbit-pool',
      {
        diameter: 2.05,
        thickness: 0.065,
        tessellation: this.touchFirst ? 12 : 16,
      },
      this.scene,
    );
    expressiveGlyph.material = routeMaterial;
    expressiveGlyph.isPickable = false;

    return {
      ember: makeThinPool(emberGlyph, LOOM_ANCHOR_POOL_SIZE),
      cobalt: makeThinPool(cobaltGlyph, LOOM_ANCHOR_POOL_SIZE),
      safe: makeThinPool(safeGlyph, LOOM_ANCHOR_POOL_SIZE),
      expressive: makeThinPool(expressiveGlyph, LOOM_ANCHOR_POOL_SIZE),
    };
  }

  private buildIris(): IrisVisual {
    const root = new TransformNode('loom-iris-engine-root', this.scene);

    const irisMaterial = new PBRMaterial('loom-iris-pbr', this.scene);
    irisMaterial.albedoColor = new Color3(0.09, 0.095, 0.1);
    irisMaterial.metallic = 0.92;
    irisMaterial.roughness = 0.28;
    irisMaterial.emissiveColor = new Color3(0.12, 0.028, 0.014);

    const ring = CreateTorus(
      'loom-iris-engine-ring',
      {
        diameter: TUNNEL_RADIUS * 1.7,
        thickness: 0.52,
        tessellation: this.touchFirst ? 24 : 32,
      },
      this.scene,
    );
    ring.rotation.x = Math.PI / 2;
    ring.material = irisMaterial;
    ring.parent = root;
    ring.isPickable = false;

    const coreMaterial = new StandardMaterial(
      'loom-iris-core-material',
      this.scene,
    );
    coreMaterial.diffuseColor = BLACK.clone();
    coreMaterial.emissiveColor = EMBER.clone();
    coreMaterial.alpha = 0.28;
    coreMaterial.alphaMode = Constants.ALPHA_ADD;
    coreMaterial.disableLighting = true;
    coreMaterial.disableDepthWrite = true;

    const core = CreateTorus(
      'loom-iris-core',
      { diameter: 5.8, thickness: 0.13, tessellation: 24 },
      this.scene,
    );
    core.rotation.x = Math.PI / 2;
    core.material = coreMaterial;
    core.parent = root;
    core.isPickable = false;

    const bladeMesh = CreateBox(
      'loom-iris-blade-pool',
      { width: 1, height: 1, depth: 1 },
      this.scene,
    );
    bladeMesh.material = irisMaterial;
    bladeMesh.parent = root;
    bladeMesh.isPickable = false;

    // This reticle lives just in front of the player plane. The physical Iris
    // can be tiny through deep fog, but its projected safe opening must remain
    // readable early enough for deliberate phone steering.
    const cueRoot = new TransformNode('loom-iris-cue-root', this.scene);
    const cueMaterial = new StandardMaterial(
      'loom-iris-cue-material',
      this.scene,
    );
    cueMaterial.diffuseColor = BLACK.clone();
    cueMaterial.emissiveColor = EMBER.clone();
    cueMaterial.alpha = 0;
    cueMaterial.alphaMode = Constants.ALPHA_ADD;
    cueMaterial.disableLighting = true;
    cueMaterial.disableDepthWrite = true;
    cueMaterial.depthFunction = Constants.ALWAYS;

    const cueRing = CreateTorus(
      'loom-iris-future-aperture',
      { diameter: 5.8, thickness: 0.16, tessellation: 24 },
      this.scene,
    );
    cueRing.rotation.x = Math.PI / 2;
    cueRing.material = cueMaterial;
    cueRing.parent = cueRoot;
    cueRing.isPickable = false;
    cueRing.renderingGroupId = 3;
    cueRing.alwaysSelectAsActiveMesh = true;

    const cueTickMesh = CreateBox(
      'loom-iris-cue-tick-pool',
      { width: 1, height: 1, depth: 1 },
      this.scene,
    );
    cueTickMesh.material = cueMaterial;
    cueTickMesh.parent = cueRoot;
    cueTickMesh.isPickable = false;
    cueTickMesh.renderingGroupId = 3;
    cueTickMesh.alwaysSelectAsActiveMesh = true;
    this.scene.setRenderingAutoClearDepthStencil(3, true, true, false);
    cueRoot.setEnabled(false);

    return {
      root,
      ring,
      core,
      blades: makeThinPool(bladeMesh, IRIS_BLADE_COUNT),
      material: irisMaterial,
      coreMaterial,
      cueRoot,
      cueRing,
      cueTicks: makeThinPool(cueTickMesh, 4),
      cueMaterial,
    };
  }

  private buildDebris() {
    const material = new PBRMaterial('loom-debris-pbr', this.scene);
    material.albedoColor = new Color3(0.16, 0.17, 0.17);
    material.metallic = 0.82;
    material.roughness = 0.31;
    material.emissiveColor = new Color3(0.08, 0.02, 0.01);

    const mesh = CreatePolyhedron(
      'loom-debris-pose-pool',
      { type: 5, size: 0.42 },
      this.scene,
    );
    mesh.material = material;
    mesh.isPickable = false;
    return {
      material,
      pool: makeThinPool(mesh, SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY),
    };
  }

  private buildParticles() {
    const texture = RawTexture.CreateRGBATexture(
      new Uint8Array([
        0, 0, 0, 0, 255, 255, 255, 80, 255, 255, 255, 80, 0, 0, 0, 0,
        255, 255, 255, 80, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 80,
        255, 255, 255, 80, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 80,
        0, 0, 0, 0, 255, 255, 255, 80, 255, 255, 255, 80, 0, 0, 0, 0,
      ]),
      4,
      4,
      this.scene,
      false,
      false,
      Texture.BILINEAR_SAMPLINGMODE,
    );

    const system = new ParticleSystem(
      'loom-forward-motes',
      qualityProfileForTier('cinematic').particleBudget,
      this.scene,
    );
    system.particleTexture = texture;
    system.emitter = new Vector3(0, 0, -170);
    system.minEmitBox = new Vector3(-8.2, -8.2, 0);
    system.maxEmitBox = new Vector3(8.2, 8.2, 155);
    system.direction1 = new Vector3(-0.08, -0.08, 1);
    system.direction2 = new Vector3(0.08, 0.08, 1);
    system.minEmitPower = 8;
    system.maxEmitPower = 14;
    system.minLifeTime = 7;
    system.maxLifeTime = 12;
    system.minSize = 0.025;
    system.maxSize = 0.085;
    system.emitRate = 42;
    system.blendMode = ParticleSystem.BLENDMODE_ADD;
    system.color1 = new Color4(1, 0.37, 0.18, 0.55);
    system.color2 = new Color4(1, 0.78, 0.58, 0.32);
    system.colorDead = new Color4(0, 0, 0, 0);
    system.updateSpeed = 0.014;
    system.start();
    return { system, texture };
  }

  private rebuildGlowLayer(profile: QualityProfile) {
    this.glowLayer?.dispose();
    this.glowLayer = null;
    const glow = new GlowLayer('loom-protected-glow', this.scene, {
      // Keep the phase silhouettes crisp on a phone. The full-screen vein
      // shell supplies its own additive light and must never be blurred into a
      // low-contrast wash by the glow compositor.
      blurKernelSize: profile.postProcessing === 'essential'
        ? 6
        : this.touchFirst ? 12 : 20,
      mainTextureRatio: profile.glowTextureRatio,
    });
    glow.intensity = profile.postProcessing === 'essential'
      ? 0.44
      : this.comfortMode
        ? 0.52
        : this.touchFirst ? 0.7 : 0.8;
    glow.addExcludedMesh(this.tunnel);
    glow.addExcludedMesh(this.veinShell);
    if (profile.postProcessing === 'essential') {
      // Draw only gameplay language into the additional glow pass. Ambient
      // machinery remains emissive in the main pass but cannot double the
      // geometry cost on a fallback GPU.
      const protectedMeshes = [
        this.player.core,
        this.player.echoRing,
        this.player.echoCore,
        this.player.thread,
        this.anchors.ember.mesh,
        this.anchors.cobalt.mesh,
        this.iris.core,
      ];
      for (const mesh of protectedMeshes) glow.addIncludedOnlyMesh(mesh);
    }
    this.glowLayer = glow;
  }

  private applyQuality(profile: QualityProfile) {
    this.qualityProfile = profile;
    this.canvas.dataset.qualityTier = profile.tier;
    const usePerformanceMaterials = profile.postProcessing === 'essential';
    this.canvas.dataset.materialMode = usePerformanceMaterials
      ? 'standard'
      : 'pbr';
    this.tunnel.material = usePerformanceMaterials
      ? this.performancePanelMaterial
      : this.panelMaterial;
    this.ribs.mesh.material = usePerformanceMaterials
      ? this.performanceRibMaterial
      : this.ribMaterial;
    this.veinShell.setEnabled(!usePerformanceMaterials);
    this.scene.imageProcessingConfiguration.exposure =
      profile.postProcessing === 'essential' ? 0.96 : 1.03;
    if (usePerformanceMaterials) {
      this.particles.stop();
      this.particles.reset();
    } else {
      this.particles.emitRate = profile.particleBudget / 10.5;
      this.particles.start();
    }
    this.veinMaterial.alpha = profile.postProcessing === 'essential'
      ? 0.27
      : profile.postProcessing === 'reduced'
        ? 0.34
        : 0.4;
    this.fxaa.samples = 1;
    const shouldUseFxaa = profile.postProcessing !== 'essential';
    if (shouldUseFxaa && !this.fxaaAttached) {
      this.camera.attachPostProcess(this.fxaa);
      this.fxaaAttached = true;
    } else if (!shouldUseFxaa && this.fxaaAttached) {
      this.camera.detachPostProcess(this.fxaa);
      this.fxaaAttached = false;
    }
    this.rebuildGlowLayer(profile);
    this.applyPhase(this.currentPhase);
    this.resize();
  }

  private applyPhase(phase: LoomPhase) {
    this.currentPhase = phase;
    const color = phase === 'ember' ? EMBER : COBALT;
    const dark = phase === 'ember' ? EMBER_DARK : COBALT_DARK;
    this.phaseLight.diffuse.copyFrom(color);
    const directEmission = this.qualityProfile.postProcessing === 'essential'
      ? 1.32
      : 1;
    setColorScaled(this.phaseMaterial.emissiveColor, color, directEmission);
    this.phaseMaterial.diffuseColor.copyFrom(dark);
    setColorScaled(this.echoMaterial.emissiveColor, color, directEmission);
    setColorScaled(this.threadMaterial.emissiveColor, color, directEmission);
    this.veinMaterial.emissiveColor.copyFrom(color);
    setColorScaled(this.railMaterial.emissiveColor, color, 0.5);
    this.railMaterial.diffuseColor.copyFrom(dark);
    setColorScaled(this.needleMaterial.emissiveColor, color, 0.16);
    setColorScaled(this.debrisMaterial.emissiveColor, color, 0.13);
    this.particles.color1.set(color.r, color.g, color.b, 0.55);
    this.particles.color2.set(
      Math.min(1, color.r * 1.25),
      Math.min(1, color.g * 1.25),
      Math.min(1, color.b * 1.25),
      0.3,
    );
  }

  private writeTransform(
    pool: ThinPool,
    index: number,
    position: Vector3,
    rotation: Quaternion,
    scale: Vector3,
  ) {
    Matrix.ComposeToRef(scale, rotation, position, this.matrixScratch);
    copyMatrixToPool(this.matrixScratch, pool, index);
  }

  private updateAnchors(frame: Readonly<LoomSimulation>) {
    let emberCount = 0;
    let cobaltCount = 0;
    let safeCount = 0;
    let expressiveCount = 0;

    for (const anchor of frame.anchors) {
      if (
        !anchor.active ||
        !signalLoomAnchorVisibleAtZ(anchor.z, this.qualityProfile.tier)
      ) continue;

      const phasePool = anchor.phase === 'ember'
        ? this.anchors.ember
        : this.anchors.cobalt;
      const routePool = anchor.route === 'safe'
        ? this.anchors.safe
        : this.anchors.expressive;
      const phaseSlot = anchor.phase === 'ember' ? emberCount++ : cobaltCount++;
      const routeSlot = anchor.route === 'safe' ? safeCount++ : expressiveCount++;
      const animationSlot = anchor.poolSlot;
      const pulse = 1 + Math.sin(
        this.visualTime * 4.6 + animationSlot * 0.71,
      ) * 0.07;
      const stateScale = anchor.resolved ? 0.55 : anchor.latched ? 1.24 : 1;

      this.positionScratch.set(anchor.x, anchor.y, anchor.z);
      Quaternion.RotationYawPitchRollToRef(
        0,
        Math.PI / 2,
        this.visualTime * (anchor.phase === 'ember' ? 0.82 : -0.58) +
          animationSlot,
        this.quaternionScratch,
      );
      this.scaleScratch.set(
        pulse * stateScale,
        pulse * stateScale,
        anchor.phase === 'ember' ? 0.58 * stateScale : stateScale,
      );
      this.writeTransform(
        phasePool,
        phaseSlot,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );

      Quaternion.RotationYawPitchRollToRef(
        0,
        Math.PI / 2,
        -this.visualTime * 0.4 + animationSlot * 0.37,
        this.quaternionScratch,
      );
      const routeScale = anchor.hit ? 0.42 : anchor.latched ? 1.3 : 1;
      this.scaleScratch.setAll(routeScale);
      this.writeTransform(
        routePool,
        routeSlot,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }

    updateThinPool(this.anchors.ember, emberCount);
    updateThinPool(this.anchors.cobalt, cobaltCount);
    updateThinPool(this.anchors.safe, safeCount);
    updateThinPool(this.anchors.expressive, expressiveCount);
    this.canvas.dataset.activeAnchorInstances = String(
      emberCount + cobaltCount + safeCount + expressiveCount,
    );
  }

  private updateTunnel(frame: Readonly<LoomSimulation>) {
    const arcProfile = signalLoomArcVisualProfile(frame.arc);
    this.canvas.dataset.visualArc = String(frame.arc);
    this.scene.fogDensity = arcProfile.fogDensity;
    this.panelTexture.vOffset = positiveModulo(frame.distance * 0.006, 1);
    this.veinTexture.vOffset = positiveModulo(frame.distance * 0.012, 1);
    this.veinTexture.uOffset = Math.sin(this.visualTime * 0.11) * 0.025 +
      Math.sin(this.visualTime * 0.37) * arcProfile.railSpiral * 0.035;

    const phaseColor = this.currentPhase === 'ember' ? EMBER : COBALT;
    const warmBlend = arcProfile.warmBlend;
    this.veinMaterial.emissiveColor.set(
      phaseColor.r * (1 - warmBlend) + WARM_WHITE.r * warmBlend,
      phaseColor.g * (1 - warmBlend) + WARM_WHITE.g * warmBlend,
      phaseColor.b * (1 - warmBlend) + WARM_WHITE.b * warmBlend,
    );
    const baseVeinAlpha = this.qualityProfile.postProcessing === 'essential'
      ? 0.27
      : this.qualityProfile.postProcessing === 'reduced'
        ? 0.34
        : 0.4;
    this.veinMaterial.alpha = Math.min(
      0.58,
      baseVeinAlpha + arcProfile.veinBoost + this.resonancePulse * 0.035,
    );
    setColorScaled(
      this.railMaterial.emissiveColor,
      phaseColor,
      0.5 + arcProfile.veinBoost * 0.7,
    );

    const activeRibCount = signalLoomRibCountForQuality(
      this.qualityProfile.tier,
    );
    for (let index = 0; index < activeRibCount; index += 1) {
      this.positionScratch.set(
        0,
        0,
        wrappedLoomTunnelZ(-index * RIB_SPACING, frame.distance, RIB_LOOP_LENGTH),
      );
      Quaternion.RotationYawPitchRollToRef(
        0,
        0,
        index * (0.018 + arcProfile.railSpiral * 0.016) +
          this.visualTime * arcProfile.ribRotationRate,
        this.quaternionScratch,
      );
      const breathing = 1 + Math.sin(
        this.visualTime * (0.55 + frame.arc * 0.16) + index * 0.48,
      ) * arcProfile.railSpiral * 0.012;
      this.scaleScratch.setAll(breathing);
      this.writeTransform(
        this.ribs,
        index,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }
    updateThinPool(this.ribs, activeRibCount);
    this.canvas.dataset.activeRibs = String(activeRibCount);

    const activeRailCount = signalLoomRailCountForQuality(
      this.qualityProfile.tier,
    );
    for (let index = 0; index < activeRailCount; index += 1) {
      const lane = index % RAIL_LANES;
      const segment = Math.floor(index / RAIL_LANES);
      const angle = Math.PI / 4 + lane * (Math.PI / 2) +
        Math.sin(
          segment * 0.82 + frame.distance * 0.014 + lane,
        ) * arcProfile.railSpiral;
      this.positionScratch.set(
        Math.cos(angle) * (TUNNEL_RADIUS - 0.18),
        Math.sin(angle) * (TUNNEL_RADIUS - 0.18),
        wrappedLoomTunnelZ(
          -segment * RAIL_SEGMENT_LENGTH - lane * 4.2,
          frame.distance,
          RIB_LOOP_LENGTH,
        ),
      );
      Quaternion.RotationYawPitchRollToRef(
        0,
        0,
        angle,
        this.quaternionScratch,
      );
      this.scaleScratch.set(0.11, 0.11, RAIL_SEGMENT_LENGTH * 0.46);
      this.writeTransform(
        this.rails,
        index,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }
    updateThinPool(this.rails, activeRailCount);
    this.canvas.dataset.activeRails = String(activeRailCount);
  }

  private updateIris(frame: Readonly<LoomSimulation>) {
    const iris = frame.iris;
    const active = iris.active && iris.stage !== 'dormant' && iris.intensity > 0;
    const cueStrength = active
      ? signalLoomIrisCueStrength(iris.stage, iris.z, iris.intensity)
      : 0;
    this.canvas.dataset.irisStage = iris.stage;
    this.canvas.dataset.irisCycle = String(iris.cycle);
    this.canvas.dataset.irisZ = iris.z.toFixed(3);
    this.canvas.dataset.irisGapX = iris.gapCenter.x.toFixed(3);
    this.canvas.dataset.irisGapY = iris.gapCenter.y.toFixed(3);
    this.canvas.dataset.irisGapRadius = iris.gapRadius.toFixed(3);
    this.canvas.dataset.irisOutcome = iris.outcome ?? 'pending';
    this.canvas.dataset.irisCueVisible = cueStrength > 0 ? 'true' : 'false';
    this.canvas.dataset.irisCueStrength = cueStrength.toFixed(3);
    this.iris.root.setEnabled(active);
    this.iris.cueRoot.setEnabled(cueStrength > 0);
    if (!active) {
      updateThinPool(this.iris.blades, 0);
      updateThinPool(this.iris.cueTicks, 0);
      this.canvas.dataset.activeIrisBlades = '0';
      return;
    }

    if (cueStrength > 0) {
      this.iris.cueRoot.position.set(
        iris.gapCenter.x,
        iris.gapCenter.y,
        1.15,
      );
      this.iris.cueRoot.rotation.set(0, 0, 0);
      const cueScale = signalLoomIrisGapScale(iris.gapRadius) *
        (1 + Math.sin(this.visualTime * 4.4) * 0.015);
      this.iris.cueRing.scaling.setAll(cueScale);
      this.iris.cueRing.rotation.z = this.visualTime * -0.12;
      const phaseColor = frame.phase === 'ember' ? EMBER : COBALT;
      setColorScaled(
        this.iris.cueMaterial.emissiveColor,
        phaseColor,
        0.75 + cueStrength * 0.75,
      );
      this.iris.cueMaterial.alpha = (0.42 + cueStrength * 0.5) *
        (0.9 + Math.sin(this.visualTime * 3.8) * 0.1);

      const tickRadius = iris.gapRadius + 0.58;
      for (let index = 0; index < 4; index += 1) {
        const angle = index * Math.PI / 2;
        this.positionScratch.set(
          Math.cos(angle) * tickRadius,
          Math.sin(angle) * tickRadius,
          0,
        );
        Quaternion.RotationYawPitchRollToRef(
          0,
          0,
          angle,
          this.quaternionScratch,
        );
        this.scaleScratch.set(0.9, 0.13, 0.08);
        this.writeTransform(
          this.iris.cueTicks,
          index,
          this.positionScratch,
          this.quaternionScratch,
          this.scaleScratch,
        );
      }
      updateThinPool(this.iris.cueTicks, 4);
    } else {
      updateThinPool(this.iris.cueTicks, 0);
    }

    this.iris.root.position.set(0, 0, iris.z);
    this.iris.root.rotation.set(0, 0, 0);
    this.iris.ring.scaling.setAll(0.96 + iris.intensity * 0.04);
    this.iris.core.position.set(iris.gapCenter.x, iris.gapCenter.y, 0);
    const outcomePulse = iris.outcome === 'clear'
      ? 0.12
      : iris.outcome === 'hit' ? 0.07 : 0;
    const gapScale = signalLoomIrisGapScale(iris.gapRadius) *
      (1 + Math.sin(this.visualTime * 5.2) * 0.018 + outcomePulse);
    this.iris.core.scaling.setAll(gapScale);
    this.iris.core.rotation.z = -this.visualTime * 0.22;

    const phaseColor = frame.phase === 'ember' ? EMBER : COBALT;
    const irisColor = iris.outcome === 'clear'
      ? WARM_WHITE
      : iris.outcome === 'hit' ? EMBER : phaseColor;
    setColorScaled(
      this.iris.material.emissiveColor,
      irisColor,
      0.08 + iris.intensity * 0.22,
    );
    setColorScaled(
      this.iris.coreMaterial.emissiveColor,
      irisColor,
      0.62 + iris.intensity * 0.72,
    );
    this.iris.coreMaterial.alpha = 0.2 + iris.intensity * 0.48;

    const aperture = signalLoomIrisBladeCenterRadius(iris.gapRadius);
    const spin = iris.cycle * 0.41 + this.visualTime *
      (frame.arc === 4 ? 0.22 : 0.14);

    for (let index = 0; index < IRIS_BLADE_COUNT; index += 1) {
      const angle = (index / IRIS_BLADE_COUNT) * Math.PI * 2 + spin;
      this.positionScratch.set(
        iris.gapCenter.x + Math.cos(angle) * aperture,
        iris.gapCenter.y + Math.sin(angle) * aperture,
        0,
      );
      Quaternion.RotationYawPitchRollToRef(
        0.045 * Math.sin(this.visualTime + index),
        0,
        angle + Math.PI / 2 + 0.28,
        this.quaternionScratch,
      );
      this.scaleScratch.set(
        0.74 + iris.intensity * 0.08,
        3.18 + iris.intensity * 0.18,
        0.24 + iris.intensity * 0.1,
      );
      this.writeTransform(
        this.iris.blades,
        index,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    }
    updateThinPool(this.iris.blades, IRIS_BLADE_COUNT);
    this.canvas.dataset.activeIrisBlades = String(IRIS_BLADE_COUNT);
  }

  private updatePlayer(frame: Readonly<LoomSimulation>) {
    this.canvas.dataset.needleX = frame.needle.position.x.toFixed(3);
    this.canvas.dataset.needleY = frame.needle.position.y.toFixed(3);
    this.canvas.dataset.echoX = frame.echo.position.x.toFixed(3);
    this.canvas.dataset.echoY = frame.echo.position.y.toFixed(3);
    this.player.root.position.set(
      frame.needle.position.x,
      frame.needle.position.y,
      PLAYER_Z,
    );
    this.player.root.rotation.x = frame.needle.velocity.y * -0.018;
    this.player.root.rotation.y = frame.needle.velocity.x * 0.022;
    this.player.root.rotation.z = frame.needle.velocity.x * -0.045;

    this.player.echoRoot.position.set(
      frame.echo.position.x,
      frame.echo.position.y,
      ECHO_Z,
    );
    this.player.echoRoot.rotation.z = -this.visualTime * 0.9;
    const echoPulse = 1 + Math.sin(this.visualTime * 5.4) * 0.06 +
      this.stitchPulse * 0.16;
    this.player.echoRoot.scaling.setAll(echoPulse);

    const dx = frame.needle.position.x - frame.echo.position.x;
    const dy = frame.needle.position.y - frame.echo.position.y;
    const inverseLength = 1 / Math.max(0.001, Math.hypot(dx, dy));
    const normalX = -dy * inverseLength;
    const normalY = dx * inverseLength;
    for (let index = 0; index < THREAD_POINT_COUNT; index += 1) {
      const t = index / (THREAD_POINT_COUNT - 1);
      const curve = Math.sin(Math.PI * t) * (0.12 + frame.thread.tension * 0.3);
      this.player.threadPath[index].set(
        frame.echo.position.x + dx * t + normalX * curve,
        frame.echo.position.y + dy * t + normalY * curve,
        ECHO_Z * (1 - t),
      );
    }
    CreateTube(
      'loom-thread',
      {
        path: this.player.threadPath,
        radius: this.touchFirst ? 0.05 : 0.042,
        tessellation: 6,
        cap: Mesh.CAP_ALL,
        instance: this.player.thread,
      },
      this.scene,
    );

    const threadPulse = 0.72 + Math.min(1, frame.thread.tension) * 0.28 +
      this.resonancePulse * 0.24;
    this.threadMaterial.alpha = Math.min(1, threadPulse);
    this.player.thread.scaling.z = 1 + this.stitchPulse * 0.03;
    this.phaseLight.position.set(
      frame.needle.position.x - 3.5,
      frame.needle.position.y + 3.5,
      -14,
    );
  }

  private updateIrisScreenDiagnostics(frame: Readonly<LoomSimulation>) {
    if (this.canvas.dataset.irisCueVisible !== 'true') {
      this.canvas.dataset.irisCueScreenX = '';
      this.canvas.dataset.irisCueScreenY = '';
      this.canvas.dataset.irisCueScreenRadius = '';
      return;
    }

    const renderWidth = Math.max(1, this.engine.getRenderWidth());
    const renderHeight = Math.max(1, this.engine.getRenderHeight());
    const cssWidth = Math.max(1, this.canvas.clientWidth || this.host.clientWidth);
    const cssHeight = Math.max(1, this.canvas.clientHeight || this.host.clientHeight);
    const viewport = this.camera.viewport.toGlobal(renderWidth, renderHeight);
    this.cueCenterWorld.set(
      frame.iris.gapCenter.x,
      frame.iris.gapCenter.y,
      1.15,
    );
    this.cueEdgeWorld.set(
      frame.iris.gapCenter.x + frame.iris.gapRadius,
      frame.iris.gapCenter.y,
      1.15,
    );
    Vector3.ProjectToRef(
      this.cueCenterWorld,
      Matrix.IdentityReadOnly,
      this.scene.getTransformMatrix(),
      viewport,
      this.cueCenterScreen,
    );
    Vector3.ProjectToRef(
      this.cueEdgeWorld,
      Matrix.IdentityReadOnly,
      this.scene.getTransformMatrix(),
      viewport,
      this.cueEdgeScreen,
    );
    const scaleX = cssWidth / renderWidth;
    const scaleY = cssHeight / renderHeight;
    this.canvas.dataset.irisCueScreenX =
      (this.cueCenterScreen.x * scaleX).toFixed(1);
    this.canvas.dataset.irisCueScreenY =
      (this.cueCenterScreen.y * scaleY).toFixed(1);
    this.canvas.dataset.irisCueScreenRadius = Math.abs(
      (this.cueEdgeScreen.x - this.cueCenterScreen.x) * scaleX,
    ).toFixed(1);
  }

  private updateFeedback(frame: Readonly<LoomSimulation>, deltaSeconds: number) {
    if (
      frame.lastStitchEvent &&
      frame.lastStitchEvent.sequence !== this.lastStitchSequence
    ) {
      this.lastStitchSequence = frame.lastStitchEvent.sequence;
      this.stitch(frame.lastStitchEvent);
    }
    if (
      frame.missedAnchors > this.lastMissedAnchors ||
      frame.threadBreaks > this.lastThreadBreaks
    ) {
      this.impact(frame.threadBreaks > this.lastThreadBreaks ? 1.35 : 0.8);
    }
    this.lastMissedAnchors = frame.missedAnchors;
    this.lastThreadBreaks = frame.threadBreaks;

    const resonanceNow = frame.resonanceRemaining > 0;
    if (resonanceNow !== this.resonanceActive) this.resonance(resonanceNow);

    this.impactPulse = Math.max(0, this.impactPulse - deltaSeconds * 2.5);
    this.stitchPulse = Math.max(0, this.stitchPulse - deltaSeconds * 3.7);
    const resonanceTarget = resonanceNow ? 1 : 0;
    this.resonancePulse +=
      (resonanceTarget - this.resonancePulse) *
      Math.min(1, deltaSeconds * (resonanceNow ? 5 : 2.4));

    const motionScale = this.comfortMode ? 0.18 : 1;
    const shake = this.impactPulse * 0.18 * motionScale;
    const frameIris = frame.iris.active &&
      frame.iris.stage !== 'dormant' &&
      frame.iris.stage !== 'recovery';
    const desiredFocusX = frameIris
      ? frame.iris.gapCenter.x
      : (frame.needle.position.x + frame.echo.position.x) * 0.5;
    const desiredFocusY = frameIris
      ? frame.iris.gapCenter.y
      : (frame.needle.position.y + frame.echo.position.y) * 0.5;
    const focusBlend = 1 - Math.exp(
      -Math.max(0, deltaSeconds) * (frameIris ? 3.2 : 4.6),
    );
    this.cameraFocus.x += (desiredFocusX - this.cameraFocus.x) * focusBlend;
    this.cameraFocus.y += (desiredFocusY - this.cameraFocus.y) * focusBlend;

    this.camera.position.x = this.cameraFocus.x * 0.26 +
      Math.sin(this.visualTime * 47) * shake;
    this.camera.position.y = 1.05 + this.cameraFocus.y * 0.26 +
      Math.cos(this.visualTime * 39) * shake * 0.72;
    this.camera.position.z = 13.5 + Math.sin(this.visualTime * 29) * shake * 0.4;
    this.cameraTarget.set(
      this.cameraFocus.x * 0.42,
      this.cameraFocus.y * 0.42,
      -28,
    );
    this.camera.setTarget(this.cameraTarget);
    this.camera.fov = 1.16 - this.resonancePulse * 0.035 * motionScale;

    if (this.glowLayer) {
      const baseGlow = this.comfortMode
        ? 0.52
        : this.touchFirst ? 0.7 : 0.8;
      this.glowLayer.intensity = baseGlow +
        this.stitchPulse * 0.16 + this.resonancePulse * 0.12;
    }
    this.phaseLight.intensity = 34 + this.stitchPulse * 18 +
      this.resonancePulse * 14;
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
    frame: Readonly<LoomSimulation>,
    deltaSeconds: number,
    promotionBoundary = false,
  ): void {
    if (this.disposed || this.paused) return;

    this.updateQuality(deltaSeconds, promotionBoundary);
    const visualDelta = sanitizeLoomVisualDelta(deltaSeconds);
    this.visualTime += visualDelta;
    if (frame.phase !== this.currentPhase) this.applyPhase(frame.phase);

    this.updateFeedback(frame, visualDelta);
    this.updatePlayer(frame);
    this.updateAnchors(frame);
    this.updateTunnel(frame);
    this.updateIris(frame);
    this.particles.minEmitPower = Math.max(7, frame.forwardSpeed * 0.68);
    this.particles.maxEmitPower = Math.max(12, frame.forwardSpeed * 0.96);
    this.scene.render();
    this.updateIrisScreenDiagnostics(frame);
    this.canvas.dataset.activeIndices = String(this.scene.getActiveIndices());
  }

  syncDebris(
    source: (visit: (pose: Readonly<RapierDebrisPose>) => void) => void,
  ): void;
  syncDebris(source: Iterable<Readonly<RapierDebrisPose>>): void;
  syncDebris(source: SignalLoomDebrisSource): void {
    if (this.disposed) return;
    this.debrisSeen.fill(0);
    let accepted = 0;
    const budget = Math.min(
      this.qualityProfile.debrisBudget,
      SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
    );

    const visit = (pose: Readonly<RapierDebrisPose>) => {
      if (accepted >= budget) return;
      const slot = signalLoomDebrisPoolSlot(
        pose.id,
        SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
      );
      if (slot < 0 || this.debrisSeen[slot]) return;
      this.debrisSeen[slot] = 1;
      const visualSlot = accepted;
      accepted += 1;

      this.positionScratch.set(
        pose.position.x,
        pose.position.y,
        pose.position.z,
      );
      this.quaternionScratch.set(
        pose.rotation.x,
        pose.rotation.y,
        pose.rotation.z,
        pose.rotation.w,
      );
      const scale = pose.sleeping ? 0.72 : 1;
      this.scaleScratch.set(0.34 * scale, 0.16 * scale, 0.52 * scale);
      this.writeTransform(
        this.debris,
        visualSlot,
        this.positionScratch,
        this.quaternionScratch,
        this.scaleScratch,
      );
    };

    if (typeof source === 'function') {
      source(visit);
    } else {
      for (const pose of source) visit(pose);
    }

    updateThinPool(this.debris, accepted);
    this.activeDebris = accepted;
    this.canvas.dataset.activeDebris = String(accepted);
  }

  impact(strength = 1): void {
    if (this.disposed) return;
    const safeStrength = Number.isFinite(strength)
      ? Math.min(MAX_FEEDBACK_STRENGTH, Math.max(0, strength))
      : 1;
    this.impactPulse = Math.max(this.impactPulse, safeStrength);
  }

  stitch(event?: SignalLoomStitchFeedback): void {
    if (this.disposed) return;
    if (event?.phase && event.phase !== this.currentPhase) {
      this.applyPhase(event.phase);
    }
    const strength = event?.expressive ? 1.25 : event?.nearMiss ? 1.08 : 0.9;
    this.stitchPulse = Math.max(this.stitchPulse, strength);
  }

  resonance(active = true): void {
    if (this.disposed) return;
    this.resonanceActive = active;
    if (active) this.resonancePulse = Math.max(this.resonancePulse, 0.45);
  }

  resize(): void {
    if (this.disposed) return;
    const bounds = this.host.getBoundingClientRect();
    const width = Math.max(
      1,
      Math.floor(this.host.clientWidth || bounds.width || this.canvas.clientWidth || 1),
    );
    const height = Math.max(
      1,
      Math.floor(this.host.clientHeight || bounds.height || this.canvas.clientHeight || 1),
    );
    const devicePixelRatio = this.host.ownerDocument.defaultView
      ?.devicePixelRatio ?? 1;
    const fovAxis = signalLoomCameraFovAxis(width, height);
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
    // Babylon derives the backing buffer from the canvas' CSS size and the
    // hardware scaling level. Calling setSize(width, height) here would
    // immediately restore full native resolution and make the quality
    // governor diagnostic-only on high-pixel-count phones.
    this.engine.resize(true);
    this.canvas.dataset.pixelRatio = this.pixelRatio.toFixed(3);
    this.canvas.dataset.fovAxis = fovAxis;
  }

  setComfortMode(enabled: boolean): void {
    if (this.disposed) return;
    this.comfortMode = enabled;
    this.scene.imageProcessingConfiguration.vignetteWeight = enabled ? 1.08 : 1.28;
    this.rebuildGlowLayer(this.qualityProfile);
  }

  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
    this.particles.stop();
  }

  resume(): void {
    if (this.disposed || !this.paused) return;
    this.paused = false;
    this.particles.start();
    this.qualityGovernor.resetEvidence();
  }

  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  getDiagnostics(): SignalLoomSceneDiagnostics {
    return {
      renderBackend: this.backend,
      physicsBackend: this.physicsBackend,
      qualityTier: this.qualityProfile.tier,
      activeDebris: this.activeDebris,
      pixelRatio: this.pixelRatio,
      anchorCapacity: LOOM_ANCHOR_POOL_SIZE,
      debrisCapacity: SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
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
    this.particles.stop();
    this.glowLayer?.dispose();
    this.glowLayer = null;
    this.fxaa.dispose();
    this.particleTexture.dispose();
    this.panelTexture.dispose();
    this.veinTexture.dispose();
    this.scene.dispose();
    this.engine.dispose();
    this.canvas.remove();
  };
}

export function createSignalLoomScene(
  host: HTMLElement,
  options: SignalLoomSceneOptions = {},
): Promise<SignalLoomScene> {
  return SignalLoomScene.create(host, options);
}
