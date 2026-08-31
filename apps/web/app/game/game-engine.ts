import * as THREE from 'three';
import { SignalRunAudio } from './audio';
import {
  INITIAL_SPEED,
  MAX_SPEED,
  RESONANCE_DURATION_SECONDS,
  TUNNEL_RADIUS,
  commitPrimedInput,
  createSimulation,
  sectorForElapsed,
  stepSimulation,
  type ActiveSignalPhrase,
  type GameObstacle,
  type GamePhase,
  type GameSector,
  type GameSimulation,
  type InputState,
  type SignalPhraseEvent,
  type SimulationSeed,
} from './simulation';

export type RunMode =
  | 'idle'
  | 'countdown'
  | 'resuming'
  | 'running'
  | 'paused'
  | 'finished'
  | 'crashed';

export interface GameSnapshot {
  score: number;
  distance: number;
  speed: number;
  integrity: number;
  combo: number;
  phase: GamePhase;
  sector: GameSector;
  activePhrase: ActiveSignalPhrase | null;
  phrasesCompleted: number;
  cleanPhrases: number;
  cleanPhraseStreak: number;
  peakCleanPhraseStreak: number;
  resonancePips: number;
  resonanceRemaining: number;
  resonanceActivations: number;
}

export interface PrimedInputFeedback {
  direction: string | null;
  phase: GamePhase | null;
}

interface SignalRunEngineOptions {
  onReady: () => void;
  onSnapshot: (snapshot: GameSnapshot) => void;
  onDamage: (integrity: number) => void;
  onCrash: (snapshot: GameSnapshot) => void;
  onPhase: (phase: GamePhase) => void;
  onSector: (sector: GameSector) => void;
  onPhrase: (event: SignalPhraseEvent) => void;
  onResonance: () => void;
  onPrimedInput: (feedback: PrimedInputFeedback) => void;
  onError?: (message: string) => void;
}

interface HazardVisual {
  kind: GameObstacle['kind'];
  phase?: GamePhase;
  group: THREE.Group;
  body?: THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
  edges?: THREE.LineSegments<THREE.EdgesGeometry, THREE.LineBasicMaterial>;
  warnings?: [
    THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>,
    THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>,
  ];
  blockDimensions?: {
    width: number;
    height: number;
    depth: number;
    blockingSide: number;
  };
  baffleWash?: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  baffleSpine?: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;
  baffleGuides?: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>[];
  membrane?: THREE.Mesh<THREE.CircleGeometry, THREE.MeshBasicMaterial>;
  ring?: THREE.Mesh<THREE.TorusGeometry, THREE.MeshStandardMaterial>;
}

const EMBER = new THREE.Color(0xff6944);
const COBALT = new THREE.Color(0x4f8cff);
const PLAYER_Z = 0;
const RIB_COUNT = 24;
const RIB_SPACING = 15;
const RIB_LOOP_LENGTH = RIB_COUNT * RIB_SPACING;
const PARTICLE_COUNT = 220;
const DESKTOP_PIXEL_BUDGET = 1_750_000;
const TOUCH_PIXEL_BUDGET = 1_350_000;
const MIN_PIXEL_RATIO = 0.48;

export function adaptivePixelRatio(
  width: number,
  height: number,
  devicePixelRatio: number,
  touchFirst: boolean,
  qualityScale = 1,
) {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const safeDeviceRatio = Number.isFinite(devicePixelRatio)
    ? Math.max(1, devicePixelRatio)
    : 1;
  const pixelBudget = touchFirst ? TOUCH_PIXEL_BUDGET : DESKTOP_PIXEL_BUDGET;
  const ratioCap = touchFirst ? 1.35 : 1.4;
  const budgetRatio = Math.sqrt(pixelBudget / (safeWidth * safeHeight));
  const scaledRatio = Math.min(safeDeviceRatio, ratioCap, budgetRatio) *
    THREE.MathUtils.clamp(qualityScale, 0.62, 1);
  return THREE.MathUtils.clamp(scaledRatio, MIN_PIXEL_RATIO, ratioCap);
}

export function blockVisualLayout(width: number, height: number, depth: number) {
  return {
    bodyScale: { x: width, y: height, z: depth },
    warningScale: { x: width * 0.72, y: 1, z: depth },
    warningOffset: height * 0.34,
  };
}

export function movementBaffleSignalLayout(
  centerX: number,
  width: number,
  height: number,
  depth: number,
) {
  const blockingSide = Math.sign(centerX) || 1;
  return {
    blockingSide,
    signalHeight: Math.min(height, TUNNEL_RADIUS * 2 - 0.5),
    signalZ: depth / 2 + 0.07,
    spineOffsetX: -blockingSide * width / 2,
    guideWidth: width * 0.68,
  };
}

export const MOVEMENT_BAFFLE_TELEGRAPH_SECONDS = 3.15;
const MOVEMENT_BAFFLE_FULL_SIGNAL_SECONDS = 0.85;

export function movementBaffleTelegraphStrength(z: number, speed: number) {
  if (!Number.isFinite(z) || !Number.isFinite(speed) || speed <= 0) return 0;
  const secondsToImpact = Math.max(0, -z) / speed;
  const progress = THREE.MathUtils.clamp(
    (MOVEMENT_BAFFLE_TELEGRAPH_SECONDS - secondsToImpact) /
      (MOVEMENT_BAFFLE_TELEGRAPH_SECONDS - MOVEMENT_BAFFLE_FULL_SIGNAL_SECONDS),
    0,
    1,
  );
  return progress * progress * (3 - 2 * progress);
}

export function displayDivisorForRefreshRate(refreshRate: number) {
  if (!Number.isFinite(refreshRate) || refreshRate <= 0) return 1;
  // Choose only an even display divisor that keeps the submitted cadence near
  // or above 60 fps. In particular, a 90 Hz phone must remain 90 fps rather
  // than being visibly stepped down to 45 fps.
  return Math.max(1, Math.floor((refreshRate + 0.75) / 60));
}

export function primedDirectionLabel(x: number, y: number): string | null {
  const horizontal = x > 0.15 ? 'Right' : x < -0.15 ? 'Left' : '';
  const vertical = y > 0.15 ? 'Upper' : y < -0.15 ? 'Lower' : '';
  if (!horizontal && !vertical) return null;
  return vertical && horizontal
    ? `${vertical} ${horizontal.toLowerCase()}`
    : vertical || horizontal;
}

export class DisplayDivisorLatch {
  private divisor = 1;
  private candidate = 1;
  private candidateSamples = 0;

  constructor(private readonly requiredSamples = 18) {}

  update(refreshRate: number) {
    const target = displayDivisorForRefreshRate(refreshRate);
    if (target === this.divisor) {
      this.candidate = target;
      this.candidateSamples = 0;
      return this.divisor;
    }
    if (target !== this.candidate) {
      this.candidate = target;
      this.candidateSamples = 1;
      return this.divisor;
    }
    this.candidateSamples += 1;
    if (this.candidateSamples >= this.requiredSamples) {
      this.divisor = target;
      this.candidateSamples = 0;
    }
    return this.divisor;
  }
}

function phaseColor(phase: GamePhase) {
  return phase === 'ember' ? EMBER : COBALT;
}

function snapshotOf(simulation: GameSimulation): GameSnapshot {
  return {
    score: Math.floor(simulation.score),
    distance: simulation.distance,
    speed: simulation.speed,
    integrity: simulation.integrity,
    combo: simulation.combo,
    phase: simulation.phase,
    sector: sectorForElapsed(simulation.elapsed),
    activePhrase: simulation.activePhrase ? { ...simulation.activePhrase } : null,
    phrasesCompleted: simulation.phrasesCompleted,
    cleanPhrases: simulation.cleanPhrases,
    cleanPhraseStreak: simulation.cleanPhraseStreak,
    peakCleanPhraseStreak: simulation.peakCleanPhraseStreak,
    resonancePips: simulation.resonancePips,
    resonanceRemaining: simulation.resonanceRemaining,
    resonanceActivations: simulation.resonanceActivations,
  };
}

export class SignalRunEngine {
  private readonly host: HTMLElement;
  private readonly options: SignalRunEngineOptions;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly touchFirst: boolean;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(67, 1, 0.12, 420);
  private readonly audio = new SignalRunAudio();
  private readonly resizeObserver: ResizeObserver;
  private readonly hazardVisuals = new Map<string, HazardVisual>();
  private readonly rings: THREE.Mesh[] = [];
  private readonly keys = new Set<string>();

  private simulation = createSimulation('signal-run-preview');
  private running = false;
  private inputPrimed = false;
  private primedInputSignature = '';
  private loopActive = false;
  private disposed = false;
  private comfortMode = false;
  private pendingPhaseToggle = false;
  private virtualInput = { x: 0, y: 0 };
  private pointerInput = { x: 0, y: 0 };
  private pointerId: number | null = null;
  private pointerOrigin = { x: 0, y: 0, time: 0 };
  private pointerMaxTravel = 0;
  private pointerType = '';
  private suppressCanvasTapUntil = 0;
  private lastSnapshotAt = 0;
  private shakeRemaining = 0;
  private idleTime = 0;
  private lastFrameTime = 0;
  private lastAnimationCallbackAt = 0;
  private refreshFrameAverage = 16.7;
  private readonly displayDivisorLatch = new DisplayDivisorLatch();
  private displayFrameModulo = 0;
  private lastAudioUpdateAt = 0;
  private frameTimeAverage = 16.7;
  private qualityScale = 1;
  private qualityWindowStartedAt = 0;
  private lastQualityChangeAt = 0;
  private readySignaled = false;
  private renderWidth = 0;
  private renderHeight = 0;
  private renderPixelRatio = 0;

  private readonly tunnelMaterial: THREE.MeshPhongMaterial;
  private readonly placeholderTunnelTexture: THREE.DataTexture;
  private tunnelTexture: THREE.Texture | null = null;
  private readonly player = new THREE.Group();
  private readonly playerHullMaterial: THREE.MeshStandardMaterial;
  private readonly playerGlowMaterial: THREE.MeshBasicMaterial;
  private readonly trailMaterial: THREE.MeshBasicMaterial;
  private readonly playerLight: THREE.PointLight;
  private readonly particleGeometry: THREE.BufferGeometry;
  private readonly particleBasePositions: Float32Array;

  private readonly blockGeometry = new THREE.BoxGeometry(1, 1, 1);
  private readonly blockMaterial = new THREE.MeshStandardMaterial({
    color: 0x242829,
    roughness: 0.38,
    metalness: 0.78,
    emissive: 0x100b08,
    emissiveIntensity: 0.32,
  });
  private readonly blockEdgeGeometry = new THREE.EdgesGeometry(this.blockGeometry, 24);
  private readonly blockEdgeMaterial = new THREE.LineBasicMaterial({
    color: 0xff7957,
    transparent: true,
    opacity: 0.72,
    fog: false,
  });
  private readonly warningGeometry = new THREE.BoxGeometry(1, 0.06, 1.04);
  private readonly warningMaterial = new THREE.MeshBasicMaterial({ color: 0xff8b55, fog: false });
  private readonly baffleWashGeometry = new THREE.PlaneGeometry(1, 1);
  private readonly baffleSpineGeometry = new THREE.BoxGeometry(0.16, 1, 0.12);
  private readonly baffleGuideGeometry = new THREE.BoxGeometry(1, 0.075, 0.09);
  private readonly membraneGeometry = new THREE.CircleGeometry(TUNNEL_RADIUS - 0.2, 48);
  private readonly membraneRingGeometry = new THREE.TorusGeometry(TUNNEL_RADIUS - 0.12, 0.18, 6, 40);
  private readonly membraneInnerRingGeometry = new THREE.TorusGeometry(3.25, 0.08, 6, 32);
  private readonly membraneSpokeGeometry = new THREE.BoxGeometry(5.3, 0.035, 0.035);
  private readonly emberMembraneMaterial = new THREE.MeshBasicMaterial({
    color: EMBER,
    transparent: true,
    opacity: 0.15,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  private readonly cobaltMembraneMaterial = new THREE.MeshBasicMaterial({
    color: COBALT,
    transparent: true,
    opacity: 0.15,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  private readonly emberRingMaterial = new THREE.MeshStandardMaterial({
    color: 0x562219,
    emissive: EMBER,
    emissiveIntensity: 2.2,
    roughness: 0.28,
    metalness: 0.66,
    fog: false,
  });
  private readonly cobaltRingMaterial = new THREE.MeshStandardMaterial({
    color: 0x172a59,
    emissive: COBALT,
    emissiveIntensity: 2.2,
    roughness: 0.28,
    metalness: 0.66,
    fog: false,
  });

  constructor(host: HTMLElement, options: SignalRunEngineOptions) {
    this.host = host;
    this.options = options;
    this.touchFirst = window.matchMedia('(hover: none), (pointer: coarse)').matches;

    this.renderer = new THREE.WebGLRenderer({
      // Full-scene MSAA multiplies the cost of every pixel. The adaptive
      // resolution below gives cleaner motion and better detail per millisecond.
      antialias: false,
      alpha: false,
      powerPreference: 'high-performance',
      precision: this.touchFirst ? 'mediump' : 'highp',
      stencil: false,
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    this.renderer.domElement.dataset.renderProfile = this.touchFirst ? 'touch' : 'desktop';
    this.renderer.domElement.setAttribute('aria-label', 'Signal Run interactive 3D tunnel');
    this.renderer.domElement.setAttribute('role', 'application');
    this.renderer.domElement.setAttribute('tabindex', '-1');
    this.renderer.domElement.setAttribute(
      'aria-description',
      'Steer with WASD, arrow keys, pointer drag, or touch controls. Press Space to shift phase.',
    );
    host.appendChild(this.renderer.domElement);

    this.scene.background = new THREE.Color(0x030505);
    this.scene.fog = new THREE.FogExp2(0x060909, 0.0185);
    this.camera.position.set(0, 1.15, 13.5);
    this.camera.lookAt(0, 0, -28);

    this.placeholderTunnelTexture = new THREE.DataTexture(
      new Uint8Array([104, 108, 107, 255]),
      1,
      1,
      THREE.RGBAFormat,
    );
    this.placeholderTunnelTexture.colorSpace = THREE.SRGBColorSpace;
    this.placeholderTunnelTexture.needsUpdate = true;
    this.tunnelMaterial = new THREE.MeshPhongMaterial({
      color: 0x8d9291,
      emissive: 0x141818,
      emissiveIntensity: 0.46,
      specular: 0x5b6262,
      shininess: 22,
      side: THREE.BackSide,
      map: this.placeholderTunnelTexture,
    });
    this.playerHullMaterial = new THREE.MeshStandardMaterial({
      color: 0x706f6a,
      metalness: 0.86,
      roughness: 0.24,
      emissive: 0x23100a,
      emissiveIntensity: 0.42,
    });
    this.playerGlowMaterial = new THREE.MeshBasicMaterial({
      color: EMBER,
      transparent: true,
      opacity: 0.96,
      blending: THREE.AdditiveBlending,
    });
    this.trailMaterial = new THREE.MeshBasicMaterial({
      color: EMBER,
      transparent: true,
      opacity: 0.32,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.playerLight = new THREE.PointLight(EMBER, 34, 28, 1.65);

    const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
    for (let index = 0; index < PARTICLE_COUNT; index += 1) {
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.sqrt(Math.random()) * (TUNNEL_RADIUS - 0.6);
      particlePositions[index * 3] = Math.cos(angle) * radius;
      particlePositions[index * 3 + 1] = Math.sin(angle) * radius;
      particlePositions[index * 3 + 2] = -Math.random() * 340 + 4;
    }
    this.particleBasePositions = particlePositions.slice();
    this.particleGeometry = new THREE.BufferGeometry();
    this.particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));

    this.buildEnvironment();
    this.buildPlayer();
    this.syncHazards();
    this.installPointerInput();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(host);
    this.resize();

    this.renderer.domElement.addEventListener('webglcontextlost', this.handleContextLost);
    this.renderStatic();

  }

  private signalReady() {
    if (this.disposed || this.readySignaled) return;
    this.readySignaled = true;
    queueMicrotask(() => {
      if (!this.disposed) this.options.onReady();
    });
  }

  private buildEnvironment() {
    const tunnel = new THREE.Mesh(
      new THREE.CylinderGeometry(TUNNEL_RADIUS + 0.5, TUNNEL_RADIUS + 0.5, 390, 48, 1, true),
      this.tunnelMaterial,
    );
    tunnel.rotation.x = Math.PI / 2;
    tunnel.position.z = -180;
    this.scene.add(tunnel);

    const ribMaterial = new THREE.MeshStandardMaterial({
      color: 0x181c1d,
      roughness: 0.42,
      metalness: 0.9,
      emissive: 0x080b0b,
      emissiveIntensity: 0.4,
    });
    const ribGeometry = new THREE.TorusGeometry(TUNNEL_RADIUS + 0.18, 0.18, 5, 40);
    for (let index = 0; index < RIB_COUNT; index += 1) {
      const rib = new THREE.Mesh(ribGeometry, ribMaterial);
      rib.position.z = -index * RIB_SPACING;
      rib.rotation.z = (index % 4) * 0.02;
      this.rings.push(rib);
      this.scene.add(rib);
    }

    const railGeometry = new THREE.BoxGeometry(0.13, 0.13, 380);
    const railMaterial = new THREE.MeshBasicMaterial({ color: 0x5d281b });
    for (let index = 0; index < 4; index += 1) {
      const angle = Math.PI / 4 + index * (Math.PI / 2);
      const rail = new THREE.Mesh(railGeometry, railMaterial);
      rail.position.set(
        Math.cos(angle) * (TUNNEL_RADIUS - 0.14),
        Math.sin(angle) * (TUNNEL_RADIUS - 0.14),
        -178,
      );
      rail.rotation.z = angle;
      this.scene.add(rail);
    }

    const particles = new THREE.Points(
      this.particleGeometry,
      new THREE.PointsMaterial({
        color: 0xbcc6c3,
        size: 0.055,
        transparent: true,
        opacity: 0.44,
        sizeAttenuation: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.scene.add(particles);

    this.scene.add(new THREE.HemisphereLight(0x9cb4bc, 0x190b07, 1.35));
    const keyLight = new THREE.PointLight(0xff895d, 115, 82, 1.65);
    keyLight.position.set(-5, 5, -22);
    this.scene.add(keyLight);
    const coldLight = new THREE.PointLight(0x4e78bb, 72, 90, 1.72);
    coldLight.position.set(6, -4, -54);
    this.scene.add(coldLight);

    const textureLoader = new THREE.TextureLoader();
    textureLoader.load(
      '/game/tunnel-panels.webp',
      (texture) => {
        if (this.disposed) {
          texture.dispose();
          return;
        }
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.wrapS = THREE.RepeatWrapping;
        texture.wrapT = THREE.RepeatWrapping;
        texture.repeat.set(3, 20);
        texture.anisotropy = Math.min(
          this.renderer.capabilities.getMaxAnisotropy(),
          this.touchFirst ? 3 : 6,
        );
        this.tunnelTexture = texture;
        this.tunnelMaterial.map = texture;
        // The 1px placeholder compiled USE_MAP up front; this swap does not
        // rebuild the shader during the first live run.
        this.renderStatic();
        this.placeholderTunnelTexture.dispose();
        this.signalReady();
      },
      undefined,
      () => {
        // The material has a complete procedural fallback if the image is unavailable.
        this.signalReady();
      },
    );
  }

  private buildPlayer() {
    const fuselage = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.6, 1.65, 6, 12),
      this.playerHullMaterial,
    );
    fuselage.rotation.x = Math.PI / 2;
    this.player.add(fuselage);

    const nose = new THREE.Mesh(
      new THREE.ConeGeometry(0.61, 1.42, 18),
      this.playerHullMaterial,
    );
    nose.rotation.x = -Math.PI / 2;
    nose.position.z = -1.64;
    this.player.add(nose);

    const canopyMaterial = new THREE.MeshStandardMaterial({
      color: 0x263940,
      emissive: 0x102c36,
      emissiveIntensity: 0.68,
      metalness: 0.38,
      roughness: 0.16,
      transparent: true,
      opacity: 0.84,
    });
    const canopy = new THREE.Mesh(new THREE.SphereGeometry(0.48, 18, 12), canopyMaterial);
    canopy.scale.set(0.9, 0.52, 1.42);
    canopy.position.set(0, 0.38, -0.72);
    this.player.add(canopy);

    const wing = new THREE.Mesh(new THREE.BoxGeometry(3.3, 0.1, 0.86), this.playerHullMaterial);
    wing.position.z = 0.2;
    this.player.add(wing);
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.1, 1.65, 0.7), this.playerHullMaterial);
    fin.position.z = 0.38;
    this.player.add(fin);

    const engineRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.48, 0.085, 8, 28),
      this.playerGlowMaterial,
    );
    engineRing.position.z = 1.28;
    this.player.add(engineRing);

    const core = new THREE.Mesh(new THREE.CircleGeometry(0.4, 24), this.playerGlowMaterial);
    core.position.z = 1.3;
    this.player.add(core);

    const trail = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.42, 3.8, 14, 1, true),
      this.trailMaterial,
    );
    trail.rotation.x = Math.PI / 2;
    trail.position.z = 3.18;
    this.player.add(trail);

    this.playerLight.position.set(0, 0, 1.6);
    this.player.add(this.playerLight);
    this.player.position.z = PLAYER_Z;
    this.scene.add(this.player);
  }

  private createHazardVisual(obstacle: GameObstacle): HazardVisual {
    const group = new THREE.Group();
    if (obstacle.kind === 'block') {
      const body = new THREE.Mesh(this.blockGeometry, this.blockMaterial);
      const edges = new THREE.LineSegments(
        this.blockEdgeGeometry,
        this.blockEdgeMaterial.clone(),
      );
      const layout = blockVisualLayout(obstacle.width, obstacle.height, obstacle.depth);
      body.scale.set(layout.bodyScale.x, layout.bodyScale.y, layout.bodyScale.z);
      edges.scale.copy(body.scale);
      group.add(body, edges);

      const upperWarning = new THREE.Mesh(this.warningGeometry, this.warningMaterial);
      upperWarning.scale.set(
        layout.warningScale.x,
        layout.warningScale.y,
        layout.warningScale.z,
      );
      upperWarning.position.y = layout.warningOffset;
      const lowerWarning = upperWarning.clone();
      lowerWarning.position.y *= -1;
      const baffleWash = new THREE.Mesh(
        this.baffleWashGeometry,
        new THREE.MeshBasicMaterial({
          color: 0xff754d,
          transparent: true,
          opacity: 0,
          fog: false,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      );
      const baffleSignalMaterial = new THREE.MeshBasicMaterial({
        color: 0xffa071,
        transparent: true,
        opacity: 0,
        fog: false,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const baffleSpine = new THREE.Mesh(
        this.baffleSpineGeometry,
        baffleSignalMaterial,
      );
      const baffleGuides = [-0.24, 0, 0.24].map(() =>
        new THREE.Mesh(this.baffleGuideGeometry, baffleSignalMaterial),
      );
      baffleWash.visible = false;
      baffleSpine.visible = false;
      baffleGuides.forEach((guide) => { guide.visible = false; });
      group.add(
        upperWarning,
        lowerWarning,
        baffleWash,
        baffleSpine,
        ...baffleGuides,
      );
      return {
        kind: obstacle.kind,
        group,
        body,
        edges,
        warnings: [upperWarning, lowerWarning],
        baffleWash,
        baffleSpine,
        baffleGuides,
      };
    }

    const membraneMaterial = obstacle.phase === 'ember'
      ? this.emberMembraneMaterial.clone()
      : this.cobaltMembraneMaterial.clone();
    const ringMaterial = obstacle.phase === 'ember'
      ? this.emberRingMaterial.clone()
      : this.cobaltRingMaterial.clone();
    const membrane = new THREE.Mesh(this.membraneGeometry, membraneMaterial);
    const ring = new THREE.Mesh(this.membraneRingGeometry, ringMaterial);
    const innerRing = new THREE.Mesh(this.membraneInnerRingGeometry, ringMaterial);
    group.add(membrane, ring, innerRing);

    const spokeCount = obstacle.phase === 'ember' ? 8 : 4;
    for (let index = 0; index < spokeCount; index += 1) {
      const angle = index * ((Math.PI * 2) / spokeCount);
      const spoke = new THREE.Mesh(
        this.membraneSpokeGeometry,
        ringMaterial,
      );
      spoke.position.set(Math.cos(angle) * 5.8, Math.sin(angle) * 5.8, 0);
      spoke.rotation.z = angle;
      group.add(spoke);
    }
    return { kind: obstacle.kind, phase: obstacle.phase, group, membrane, ring };
  }

  private syncHazards(visualLead = 0) {
    this.hazardVisuals.forEach((visual) => { visual.group.visible = false; });

    for (const obstacle of this.simulation.obstacles) {
      const variant = obstacle.kind === 'membrane' ? obstacle.phase : 'neutral';
      const visualKey = `${obstacle.poolSlot}:${obstacle.kind}:${variant}`;
      let visual = this.hazardVisuals.get(visualKey);
      if (!visual) {
        visual = this.createHazardVisual(obstacle);
        this.hazardVisuals.set(visualKey, visual);
        this.scene.add(visual.group);
      }
      const visualZ = obstacle.z + visualLead;
      visual.group.position.set(obstacle.x, obstacle.y, visualZ);
      // Exp2 fog is already opaque beyond this point. Avoid sending invisible
      // hazards through the GPU, especially on tile-based phone renderers.
      visual.group.visible = visualZ > -125 && visualZ < 12;

      if (obstacle.kind === 'block') {
        const signalLayout = movementBaffleSignalLayout(
          obstacle.x,
          obstacle.width,
          obstacle.height,
          obstacle.depth,
        );
        const dimensionsChanged = !visual.blockDimensions ||
          visual.blockDimensions.width !== obstacle.width ||
          visual.blockDimensions.height !== obstacle.height ||
          visual.blockDimensions.depth !== obstacle.depth ||
          visual.blockDimensions.blockingSide !== signalLayout.blockingSide;
        if (dimensionsChanged && visual.body && visual.edges && visual.warnings) {
          const layout = blockVisualLayout(
            obstacle.width,
            obstacle.height,
            obstacle.depth,
          );
          visual.body.scale.set(
            layout.bodyScale.x,
            layout.bodyScale.y,
            layout.bodyScale.z,
          );
          visual.edges.scale.copy(visual.body.scale);
          visual.warnings.forEach((warning, index) => {
            warning.scale.set(
              layout.warningScale.x,
              layout.warningScale.y,
              layout.warningScale.z,
            );
            warning.position.y = layout.warningOffset * (index === 0 ? 1 : -1);
          });
          if (visual.baffleWash && visual.baffleSpine && visual.baffleGuides) {
            visual.baffleWash.scale.set(
              obstacle.width,
              signalLayout.signalHeight,
              1,
            );
            visual.baffleWash.position.z = signalLayout.signalZ;
            visual.baffleSpine.position.set(
              signalLayout.spineOffsetX,
              0,
              signalLayout.signalZ + 0.035,
            );
            visual.baffleSpine.scale.y = signalLayout.signalHeight;
            visual.baffleGuides.forEach((guide, index) => {
              guide.scale.x = signalLayout.guideWidth;
              guide.position.set(
                0,
                (index - 1) * signalLayout.signalHeight * 0.24,
                signalLayout.signalZ + 0.04,
              );
            });
          }
          visual.blockDimensions = {
            width: obstacle.width,
            height: obstacle.height,
            depth: obstacle.depth,
            blockingSide: signalLayout.blockingSide,
          };
        }
        const pulse = 0.82 + Math.sin(this.idleTime * 4 + obstacle.poolSlot) * 0.18;
        const edges = visual.edges ?? visual.group.children[1] as THREE.LineSegments;
        const edgeMaterial = edges.material as THREE.LineBasicMaterial;
        const movementBaffle = obstacle.phraseKind === 'slalom';
        const telegraphStrength = movementBaffle
          ? movementBaffleTelegraphStrength(visualZ, this.simulation.speed)
          : 0;
        edgeMaterial.opacity = obstacle.hit
          ? 0.16
          : Math.max(pulse, telegraphStrength * 0.96);
        if (visual.baffleWash && visual.baffleSpine && visual.baffleGuides) {
          const telegraphVisible = movementBaffle && telegraphStrength > 0.005;
          visual.baffleWash.visible = telegraphVisible;
          visual.baffleSpine.visible = telegraphVisible;
          visual.baffleGuides.forEach((guide) => { guide.visible = telegraphVisible; });
          visual.baffleWash.material.opacity = telegraphStrength * 0.16;
          const signalOpacity = telegraphStrength * (0.42 + telegraphStrength * 0.48);
          visual.baffleSpine.material.opacity = signalOpacity;
        }
      } else if (visual.membrane && visual.ring) {
        const matching = obstacle.phase === this.simulation.phase;
        visual.membrane.material.opacity = obstacle.hit ? 0.025 : matching ? 0.065 : 0.2;
        visual.ring.material.emissiveIntensity = matching ? 1.35 : 2.7;
        visual.group.rotation.z = this.idleTime * (obstacle.poolSlot % 2 ? 0.12 : -0.1);
      }
    }
  }

  private installPointerInput() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('pointerdown', this.handlePointerDown);
    canvas.addEventListener('pointermove', this.handlePointerMove);
    canvas.addEventListener('pointerup', this.handlePointerUp);
    canvas.addEventListener('pointercancel', this.handlePointerCancel);
    canvas.addEventListener('lostpointercapture', this.handleLostPointerCapture);
  }

  private readonly handlePointerDown = (event: PointerEvent) => {
    if ((!this.running && !this.inputPrimed) || this.pointerId !== null) return;
    this.pointerId = event.pointerId;
    this.pointerOrigin = { x: event.clientX, y: event.clientY, time: performance.now() };
    this.pointerMaxTravel = 0;
    this.pointerType = event.pointerType;
    this.pointerInput = { x: 0, y: 0 };
    try {
      this.renderer.domElement.setPointerCapture(event.pointerId);
    } catch {
      // A rapid pointer cancellation can invalidate capture before this handler runs.
    }
    this.renderer.domElement.focus({ preventScroll: true });
  };

  private readonly handlePointerMove = (event: PointerEvent) => {
    if (
      event.pointerId !== this.pointerId ||
      (!this.running && !this.inputPrimed)
    ) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const response = Math.max(Math.min(rect.width, rect.height) * 0.2, 90);
    const deltaX = event.clientX - this.pointerOrigin.x;
    const deltaY = event.clientY - this.pointerOrigin.y;
    this.pointerMaxTravel = Math.max(this.pointerMaxTravel, Math.hypot(deltaX, deltaY));
    this.pointerInput.x = THREE.MathUtils.clamp(
      deltaX / response,
      -1,
      1,
    );
    this.pointerInput.y = THREE.MathUtils.clamp(
      -deltaY / response,
      -1,
      1,
    );
    this.emitPrimedInput();
  };

  private readonly handlePointerUp = (event: PointerEvent) => {
    if (event.pointerId !== this.pointerId) return;
    const releaseTravel = Math.hypot(
      event.clientX - this.pointerOrigin.x,
      event.clientY - this.pointerOrigin.y,
    );
    this.pointerMaxTravel = Math.max(this.pointerMaxTravel, releaseTravel);
    const duration = performance.now() - this.pointerOrigin.time;
    const isTouchLike = this.pointerType === 'touch' || this.pointerType === 'pen';
    const tapSlop = isTouchLike ? 16 : 9;
    const tapDuration = isTouchLike ? 460 : 320;
    if (
      (this.running || this.inputPrimed) &&
      performance.now() >= this.suppressCanvasTapUntil &&
      this.pointerMaxTravel <= tapSlop &&
      duration <= tapDuration
    ) {
      this.togglePhase();
    }
    try {
      if (this.renderer.domElement.hasPointerCapture(event.pointerId)) {
        this.renderer.domElement.releasePointerCapture(event.pointerId);
      }
    } catch {
      // Capture may already have been released by the user agent.
    }
    this.pointerId = null;
    this.pointerInput = { x: 0, y: 0 };
    this.pointerMaxTravel = 0;
    this.pointerType = '';
    this.emitPrimedInput();
  };

  private readonly handlePointerCancel = (event: PointerEvent) => {
    if (event.pointerId !== this.pointerId) return;
    this.releasePointerCapture();
  };

  private readonly handleLostPointerCapture = (event: PointerEvent) => {
    if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
    this.pointerId = null;
    this.pointerInput = { x: 0, y: 0 };
    this.pointerMaxTravel = 0;
    this.pointerType = '';
    this.emitPrimedInput();
  };

  private releasePointerCapture() {
    const pointerId = this.pointerId;
    this.pointerId = null;
    this.pointerInput = { x: 0, y: 0 };
    this.pointerMaxTravel = 0;
    this.pointerType = '';
    try {
      if (pointerId !== null && this.renderer.domElement.hasPointerCapture(pointerId)) {
        this.renderer.domElement.releasePointerCapture(pointerId);
      }
    } catch {
      // Capture may already have been released by the user agent.
    }
    this.emitPrimedInput();
  }

  private readonly handleContextLost = (event: Event) => {
    event.preventDefault();
    this.running = false;
    this.inputPrimed = false;
    this.stopLoop();
    this.releaseInput();
    this.setSurfaceInteractive(false);
    this.audio.setRunning(false);
    this.options.onError?.('The graphics context was interrupted. Reload the page to reconnect the signal.');
  };

  private combinedDirection() {
    const keyboardX = Number(this.keys.has('ArrowRight') || this.keys.has('KeyD')) -
      Number(this.keys.has('ArrowLeft') || this.keys.has('KeyA'));
    const keyboardY = Number(this.keys.has('ArrowUp') || this.keys.has('KeyW')) -
      Number(this.keys.has('ArrowDown') || this.keys.has('KeyS'));
    const x = THREE.MathUtils.clamp(
      keyboardX + this.virtualInput.x + this.pointerInput.x,
      -1,
      1,
    );
    const y = THREE.MathUtils.clamp(
      keyboardY + this.virtualInput.y + this.pointerInput.y,
      -1,
      1,
    );
    return { x, y };
  }

  private emitPrimedInput() {
    if (!this.inputPrimed) return;
    const combinedDirection = this.combinedDirection();
    const direction = primedDirectionLabel(combinedDirection.x, combinedDirection.y);
    const phase = this.pendingPhaseToggle
      ? this.simulation.phase === 'ember' ? 'cobalt' : 'ember'
      : null;
    const signature = `${direction ?? ''}|${phase ?? ''}`;
    if (signature === this.primedInputSignature) return;
    this.primedInputSignature = signature;
    this.options.onPrimedInput({ direction, phase });
  }

  private clearPrimedInputFeedback() {
    if (!this.inputPrimed && this.primedInputSignature === '') return;
    this.primedInputSignature = '';
    this.options.onPrimedInput({ direction: null, phase: null });
  }

  private inputSnapshot(): InputState {
    const { x, y } = this.combinedDirection();
    const phaseToggle = this.pendingPhaseToggle;
    this.pendingPhaseToggle = false;
    return { x, y, phaseToggle };
  }

  private updateSimulation(delta: number) {
    const previous = this.simulation;
    const next = stepSimulation(previous, this.inputSnapshot(), delta);
    this.simulation = next;

    if (next.phase !== previous.phase) {
      this.applyPhase(next.phase);
      this.audio.phase(next.phase);
      this.options.onPhase(next.phase);
    }
    const previousSector = sectorForElapsed(previous.elapsed);
    const nextSector = sectorForElapsed(next.elapsed);
    if (nextSector !== previousSector) {
      this.audio.sector(nextSector);
      this.options.onSector(nextSector);
    }
    if (next.integrity < previous.integrity) {
      this.shakeRemaining = this.comfortMode ? 0 : 0.38;
      this.audio.damage();
      this.options.onDamage(next.integrity);
    }

    const phraseEvent = next.lastPhraseEvent;
    const previousPhraseSequence = previous.lastPhraseEvent?.sequence ?? 0;
    const phraseResolved = Boolean(
      phraseEvent && phraseEvent.sequence > previousPhraseSequence,
    );
    if (phraseEvent && phraseResolved) {
      if (next.resonanceActivations === previous.resonanceActivations) {
        this.audio.phrase(phraseEvent.result, phraseEvent.cleanStreak);
      }
      this.options.onPhrase({ ...phraseEvent });
    }

    const resonanceStarted =
      next.resonanceActivations > previous.resonanceActivations;
    if (resonanceStarted) {
      this.audio.resonance();
      this.options.onResonance();
    }

    if (!phraseResolved && !resonanceStarted && next.obstacles.some((obstacle) => {
      const previousObstacle = previous.obstacles.find(({ id }) => id === obstacle.id);
      return obstacle.passed && !obstacle.hit && !previousObstacle?.passed;
    })) {
      this.audio.gate();
    }

    if (next.status === 'crashed' && previous.status !== 'crashed') {
      this.running = false;
      this.stopLoop();
      this.setSurfaceInteractive(false);
      this.audio.setRunning(false);
      this.audio.crash();
      const finalSnapshot = snapshotOf(next);
      this.options.onSnapshot(finalSnapshot);
      this.options.onCrash(finalSnapshot);
    }
  }

  private updateVisuals(delta: number) {
    // The fixed-step simulation retains a fractional accumulator. Projecting
    // that small remainder removes visible 60 Hz stair-steps on 90/120/144 Hz
    // phone and desktop displays without changing collision determinism.
    const interpolationSeconds = this.running ? this.simulation.accumulator : 0;
    const visualLead = this.simulation.speed * interpolationSeconds;
    const travel = this.simulation.distance + visualLead;
    this.idleTime += delta;

    if (this.tunnelTexture) this.tunnelTexture.offset.y = -(travel * 0.012) % 1;
    this.rings.forEach((ring, index) => {
      let z = -index * RIB_SPACING + (travel % RIB_LOOP_LENGTH);
      if (z > 12) z -= RIB_LOOP_LENGTH;
      ring.position.z = z;
      ring.visible = z > -135;
      ring.rotation.z = index * 0.025 + travel * 0.0009;
    });

    const positionAttribute = this.particleGeometry.getAttribute('position') as THREE.BufferAttribute;
    const positions = positionAttribute.array as Float32Array;
    for (let index = 0; index < PARTICLE_COUNT; index += 1) {
      const baseOffset = index * 3;
      let z = this.particleBasePositions[baseOffset + 2] + (travel % 344);
      if (z > 6) z -= 344;
      positions[baseOffset + 2] = z;
    }
    positionAttribute.needsUpdate = true;

    const { player } = this.simulation;
    const visualPlayerX = player.position.x + player.velocity.x * interpolationSeconds;
    const visualPlayerY = player.position.y + player.velocity.y * interpolationSeconds;
    const smoothing = 1 - Math.exp(-14 * Math.max(delta, 0));
    // Movement physics already accelerate and damp smoothly. Rendering the
    // exact projected collider avoids apparent hits on a lagging craft.
    this.player.position.x = visualPlayerX;
    this.player.position.y = visualPlayerY;
    this.player.position.z = PLAYER_Z;
    if (!this.comfortMode) {
      this.player.rotation.z = THREE.MathUtils.lerp(this.player.rotation.z, -player.velocity.x * 0.045, smoothing);
      this.player.rotation.x = THREE.MathUtils.lerp(this.player.rotation.x, player.velocity.y * 0.022, smoothing);
    } else {
      this.player.rotation.set(0, 0, 0);
    }

    const speedRatio = THREE.MathUtils.clamp(
      (this.simulation.speed - INITIAL_SPEED) / (MAX_SPEED - INITIAL_SPEED),
      0,
      1,
    );
    const resonanceEnvelope = this.simulation.resonanceRemaining > 0
      ? THREE.MathUtils.clamp(
          this.simulation.resonanceRemaining / Math.min(RESONANCE_DURATION_SECONDS, 0.35),
          0,
          1,
        )
      : 0;
    const resonancePulse = resonanceEnvelope * (
      this.comfortMode ? 1 : 0.86 + Math.sin(this.idleTime * 10) * 0.14
    );
    this.trailMaterial.opacity = 0.25 + speedRatio * 0.28 + resonancePulse * 0.18;
    this.playerLight.intensity = 34 + resonancePulse * 28;
    this.playerHullMaterial.emissiveIntensity = 0.42 + resonancePulse * 0.34;
    this.player.children.forEach((child) => {
      if (child instanceof THREE.Mesh && child.geometry instanceof THREE.CylinderGeometry && child.material === this.trailMaterial) {
        child.scale.y = 1 + speedRatio * 0.52 + resonancePulse * 0.28;
      }
    });

    const targetFov = this.comfortMode ? 67 : 67 + speedRatio * 7;
    if (Math.abs(this.camera.fov - targetFov) > 0.02) {
      this.camera.fov = THREE.MathUtils.lerp(this.camera.fov, targetFov, smoothing * 0.35);
      this.camera.updateProjectionMatrix();
    }

    const cameraX = this.comfortMode ? 0 : player.position.x * 0.1;
    const cameraY = 1.15 + (this.comfortMode ? 0 : player.position.y * 0.08);
    this.camera.position.x = THREE.MathUtils.lerp(this.camera.position.x, cameraX, smoothing * 0.45);
    this.camera.position.y = THREE.MathUtils.lerp(this.camera.position.y, cameraY, smoothing * 0.45);
    if (this.shakeRemaining > 0) {
      this.shakeRemaining = Math.max(0, this.shakeRemaining - delta);
      const amplitude = this.comfortMode ? 0.025 : Math.min(this.shakeRemaining, 0.18) * 0.45;
      this.camera.position.x += (Math.random() - 0.5) * amplitude;
      this.camera.position.y += (Math.random() - 0.5) * amplitude;
    }
    this.camera.lookAt(player.position.x * 0.14, player.position.y * 0.12, -30);
    this.syncHazards(visualLead);
  }

  private applyPhase(phase: GamePhase) {
    const color = phaseColor(phase);
    this.playerGlowMaterial.color.copy(color);
    this.trailMaterial.color.copy(color);
    this.playerLight.color.copy(color);
    this.playerHullMaterial.emissive.copy(color).multiplyScalar(0.18);
  }

  private updateRenderQuality(frameMilliseconds: number, time: number) {
    // Ignore tab switches and debugger pauses; they do not describe GPU load.
    if (frameMilliseconds <= 0 || frameMilliseconds > 1_000 || document.hidden) return;
    const frameSample = Math.min(frameMilliseconds, 120);
    this.frameTimeAverage = this.frameTimeAverage * 0.94 + frameSample * 0.06;
    if (this.qualityWindowStartedAt === 0) {
      this.qualityWindowStartedAt = time;
      return;
    }
    if (time - this.qualityWindowStartedAt < 1_800) return;

    const canChangeAgain = time - this.lastQualityChangeAt > 2_500;
    if (canChangeAgain && this.frameTimeAverage > 24 && this.qualityScale > 0.64) {
      this.qualityScale = Math.max(0.64, this.qualityScale - 0.14);
      this.lastQualityChangeAt = time;
      this.resize(true);
    }
    this.qualityWindowStartedAt = time;
  }

  private readonly animate = (time: number) => {
    if (this.disposed) return;
    const callbackDelta = this.lastAnimationCallbackAt === 0
      ? 0
      : time - this.lastAnimationCallbackAt;
    this.lastAnimationCallbackAt = time;
    if (callbackDelta > 3 && callbackDelta < 50) {
      this.refreshFrameAverage = this.refreshFrameAverage * 0.9 + callbackDelta * 0.1;
    }

    // On high-refresh phones, submit an even divisor of the display cadence
    // (120→60, 144→72, 180→60) without dropping 90 Hz panels to a choppy 45.
    const shouldPaceFrames = this.touchFirst || this.qualityScale < 0.99;
    const estimatedRefreshRate = 1000 / this.refreshFrameAverage;
    const displayDivisor = shouldPaceFrames
      ? this.displayDivisorLatch.update(estimatedRefreshRate)
      : 1;
    this.displayFrameModulo = (this.displayFrameModulo + 1) % displayDivisor;
    if (this.displayFrameModulo !== 0) return;

    const frameMilliseconds = this.lastFrameTime === 0 ? 0 : time - this.lastFrameTime;
    const delta = this.lastFrameTime === 0
      ? 0
      : Math.min(Math.max(frameMilliseconds / 1000, 0), 0.2);
    this.lastFrameTime = time;
    this.updateRenderQuality(frameMilliseconds, time);
    if (this.running) {
      this.updateSimulation(delta);
      if (time - this.lastAudioUpdateAt > 140) {
        this.lastAudioUpdateAt = time;
        this.audio.setSpeed(this.simulation.speed);
      }
    }
    this.updateVisuals(this.running ? delta : 0);

    const now = performance.now();
    if (this.running && now - this.lastSnapshotAt > 100) {
      this.lastSnapshotAt = now;
      this.options.onSnapshot(snapshotOf(this.simulation));
    }
    this.renderer.render(this.scene, this.camera);
  };

  private startLoop() {
    if (this.loopActive || this.disposed) return;
    this.loopActive = true;
    this.lastFrameTime = 0;
    this.lastAnimationCallbackAt = 0;
    this.displayFrameModulo = 0;
    this.renderer.setAnimationLoop(this.animate);
  }

  private stopLoop() {
    if (!this.loopActive) return;
    this.renderer.setAnimationLoop(null);
    this.loopActive = false;
    this.lastFrameTime = 0;
    this.lastAnimationCallbackAt = 0;
    this.displayFrameModulo = 0;
  }

  private renderStatic() {
    if (this.disposed) return;
    this.updateVisuals(0);
    this.renderer.render(this.scene, this.camera);
  }

  private setSurfaceInteractive(interactive: boolean) {
    this.renderer.domElement.tabIndex = interactive ? 0 : -1;
    this.renderer.domElement.setAttribute('aria-disabled', String(!interactive));
  }

  private resize(force = false) {
    if (this.disposed) return;
    const rect = this.host.getBoundingClientRect();
    const width = Math.floor(rect.width);
    const height = Math.floor(rect.height);
    if (width < 1 || height < 1) return;
    const pixelRatio = adaptivePixelRatio(
      width,
      height,
      window.devicePixelRatio || 1,
      this.touchFirst,
      this.qualityScale,
    );
    const sizeChanged = width !== this.renderWidth || height !== this.renderHeight;
    const ratioChanged = Math.abs(pixelRatio - this.renderPixelRatio) > 0.01;
    if (!force && !sizeChanged && !ratioChanged) return;

    this.renderWidth = width;
    this.renderHeight = height;
    this.renderPixelRatio = pixelRatio;
    this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height, false);
    this.renderer.domElement.dataset.pixelRatio = pixelRatio.toFixed(2);
    this.renderer.domElement.dataset.qualityScale = this.qualityScale.toFixed(2);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    if (!this.running) this.renderStatic();
  }

  async unlockAudio() {
    try {
      return await this.audio.unlock();
    } catch {
      this.audio.setMuted(true);
      return false;
    }
  }

  prepareRun(seed: SimulationSeed) {
    this.running = false;
    this.inputPrimed = false;
    this.simulation = createSimulation(seed);
    this.releaseInput();
    this.setSurfaceInteractive(false);
    this.shakeRemaining = 0;
    this.player.position.set(0, 0, PLAYER_Z);
    this.player.rotation.set(0, 0, 0);
    this.applyPhase(this.simulation.phase);
    this.syncHazards();
    this.renderStatic();
    this.options.onSnapshot(snapshotOf(this.simulation));
  }

  start() {
    if (this.disposed || this.simulation.status === 'crashed') return;
    const wasPrimed = this.inputPrimed;
    const previousPhase = this.simulation.phase;
    if (wasPrimed) {
      this.simulation = commitPrimedInput(
        this.simulation,
        this.pendingPhaseToggle,
      );
      this.pendingPhaseToggle = false;
      if (this.simulation.phase !== previousPhase) {
        this.applyPhase(this.simulation.phase);
        this.syncHazards();
        this.options.onPhase(this.simulation.phase);
      }
      this.options.onSnapshot(snapshotOf(this.simulation));
    }
    this.running = true;
    this.clearPrimedInputFeedback();
    this.inputPrimed = false;
    this.startLoop();
    this.setSurfaceInteractive(true);
    this.audio.setRunning(true);
    if (wasPrimed && this.simulation.phase !== previousPhase) {
      this.audio.phase(this.simulation.phase);
    }
    this.renderer.domElement.focus({ preventScroll: true });
  }

  pause() {
    this.running = false;
    this.inputPrimed = false;
    this.stopLoop();
    this.releaseInput();
    this.setSurfaceInteractive(false);
    this.audio.setRunning(false);
    this.renderStatic();
    // React snapshots are intentionally throttled during play. Flush the exact
    // frozen score here so the pause HUD and a subsequent banked result cannot
    // disagree by the last unreported simulation tick.
    this.options.onSnapshot(snapshotOf(this.simulation));
  }

  getSnapshot() {
    return snapshotOf(this.simulation);
  }

  finishRun() {
    this.pause();
    const finalSnapshot = this.getSnapshot();
    this.options.onSnapshot(finalSnapshot);
    return finalSnapshot;
  }

  togglePhase() {
    if (!this.running && !this.inputPrimed) return;
    if (this.inputPrimed) {
      this.pendingPhaseToggle = !this.pendingPhaseToggle;
      this.emitPrimedInput();
      return;
    }
    if (this.simulation.phaseCooldown > 0) return;
    this.pendingPhaseToggle = true;
    this.emitPrimedInput();
  }

  setKey(code: string, pressed: boolean) {
    if (!this.running && !this.inputPrimed) return;
    if (pressed) this.keys.add(code);
    else this.keys.delete(code);
    this.emitPrimedInput();
  }

  setVirtualDirection(x: number, y: number) {
    if (!this.running && !this.inputPrimed) return;
    this.virtualInput = {
      x: THREE.MathUtils.clamp(x, -1, 1),
      y: THREE.MathUtils.clamp(y, -1, 1),
    };
    this.emitPrimedInput();
  }

  releaseInput() {
    this.keys.clear();
    this.virtualInput = { x: 0, y: 0 };
    this.pendingPhaseToggle = false;
    this.releasePointerCapture();
    this.emitPrimedInput();
  }

  primeInput() {
    if (this.disposed || this.running || this.simulation.status === 'crashed') return;
    this.inputPrimed = true;
    this.primedInputSignature = '__initial__';
    this.emitPrimedInput();
    this.setSurfaceInteractive(true);
    // A launch or pause dialog disappears on the first click. Ignore only the
    // brief tap portion of a second click that can then land on the canvas at
    // the same screen coordinate; drag steering and the explicit Shift control
    // remain available throughout the countdown.
    this.suppressCanvasTapUntil = performance.now() + 180;
    // Move keyboard ownership away from the launch/resume button before it
    // leaves the DOM. Otherwise a rapid click can leave Space targeted at a
    // stale button, silently dropping the staged phase.
    this.renderer.domElement.focus({ preventScroll: true });
  }

  setMuted(muted: boolean) {
    this.audio.setMuted(muted);
  }

  setComfortMode(enabled: boolean) {
    this.comfortMode = enabled;
    if (enabled) {
      this.shakeRemaining = 0;
      this.camera.fov = 67;
      this.camera.updateProjectionMatrix();
      if (!this.running) this.renderStatic();
    }
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.running = false;
    this.inputPrimed = false;
    this.stopLoop();
    this.resizeObserver.disconnect();
    this.renderer.domElement.removeEventListener('pointerdown', this.handlePointerDown);
    this.renderer.domElement.removeEventListener('pointermove', this.handlePointerMove);
    this.renderer.domElement.removeEventListener('pointerup', this.handlePointerUp);
    this.renderer.domElement.removeEventListener('pointercancel', this.handlePointerCancel);
    this.renderer.domElement.removeEventListener('lostpointercapture', this.handleLostPointerCapture);
    this.renderer.domElement.removeEventListener('webglcontextlost', this.handleContextLost);
    this.releaseInput();
    this.audio.dispose();

    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    this.scene.traverse((object) => {
      if (!(object instanceof THREE.Mesh || object instanceof THREE.LineSegments || object instanceof THREE.Points)) return;
      if (object.geometry) geometries.add(object.geometry);
      const objectMaterials = Array.isArray(object.material) ? object.material : [object.material];
      objectMaterials.forEach((material) => {
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value instanceof THREE.Texture) textures.add(value);
        }
      });
    });
    if (this.tunnelTexture) textures.add(this.tunnelTexture);
    geometries.add(this.blockGeometry);
    geometries.add(this.blockEdgeGeometry);
    geometries.add(this.warningGeometry);
    geometries.add(this.baffleWashGeometry);
    geometries.add(this.baffleSpineGeometry);
    geometries.add(this.baffleGuideGeometry);
    geometries.add(this.membraneGeometry);
    geometries.add(this.membraneRingGeometry);
    geometries.add(this.membraneInnerRingGeometry);
    geometries.add(this.membraneSpokeGeometry);
    materials.add(this.blockMaterial);
    materials.add(this.blockEdgeMaterial);
    materials.add(this.warningMaterial);
    materials.add(this.emberMembraneMaterial);
    materials.add(this.cobaltMembraneMaterial);
    materials.add(this.emberRingMaterial);
    materials.add(this.cobaltRingMaterial);
    geometries.forEach((geometry) => geometry.dispose());
    textures.forEach((texture) => texture.dispose());
    materials.forEach((material) => material.dispose());
    this.renderer.dispose();
    if (this.renderer.domElement.parentNode === this.host) {
      this.host.removeChild(this.renderer.domElement);
    }
  }
}
