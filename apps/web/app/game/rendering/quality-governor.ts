export type QualityTier = 'cinematic' | 'balanced' | 'performance';

export const QUALITY_TIER_ORDER: readonly QualityTier[] = Object.freeze([
  'cinematic',
  'balanced',
  'performance',
]);

export const PROTECTED_GAMEPLAY_CUES = Object.freeze({
  hazardSilhouettes: true,
  hazardTelegraphs: true,
  hudFeedback: true,
  phaseEmission: true,
  phaseShapeLanguage: true,
} as const);

export interface QualityProfile {
  tier: QualityTier;
  resolutionScale: number;
  glowTextureRatio: number;
  volumetricLighting: boolean;
  optionalShadows: boolean;
  particleBudget: number;
  debrisBudget: number;
  postProcessing: 'full' | 'reduced' | 'essential';
  protectedCues: typeof PROTECTED_GAMEPLAY_CUES;
}

export const QUALITY_PROFILES: Readonly<Record<QualityTier, QualityProfile>> =
  Object.freeze({
    cinematic: Object.freeze({
      tier: 'cinematic',
      resolutionScale: 1,
      glowTextureRatio: 0.5,
      volumetricLighting: true,
      optionalShadows: true,
      particleBudget: 600,
      debrisBudget: 32,
      postProcessing: 'full',
      protectedCues: PROTECTED_GAMEPLAY_CUES,
    }),
    balanced: Object.freeze({
      tier: 'balanced',
      resolutionScale: 0.86,
      glowTextureRatio: 0.375,
      volumetricLighting: false,
      optionalShadows: false,
      particleBudget: 320,
      debrisBudget: 16,
      postProcessing: 'reduced',
      protectedCues: PROTECTED_GAMEPLAY_CUES,
    }),
    performance: Object.freeze({
      tier: 'performance',
      // A fallback GPU needs a decisive step, not a barely-visible one. HUD
      // text remains DOM-sharp while the abstract world can trade resolution
      // for stable steering and collision timing.
      resolutionScale: 0.48,
      glowTextureRatio: 0.125,
      volumetricLighting: false,
      optionalShadows: false,
      particleBudget: 48,
      debrisBudget: 4,
      postProcessing: 'essential',
      protectedCues: PROTECTED_GAMEPLAY_CUES,
    }),
  });

const DESKTOP_PIXEL_BUDGET = 1_750_000;
const TOUCH_PIXEL_BUDGET = 1_350_000;
const DESKTOP_PIXEL_RATIO_CAP = 1.4;
const TOUCH_PIXEL_RATIO_CAP = 1.35;
const MINIMUM_PIXEL_RATIO = 0.48;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

export function initialQualityTier(touchFirst: boolean): QualityTier {
  return touchFirst ? 'balanced' : 'cinematic';
}

export function qualityProfileForTier(tier: QualityTier): QualityProfile {
  return QUALITY_PROFILES[tier];
}

export interface RenderPixelRatioInput {
  width: number;
  height: number;
  devicePixelRatio: number;
  touchFirst: boolean;
  tier: QualityTier;
}

/** Returns the render-pixel/CSS-pixel ratio without mutating an engine. */
export function renderPixelRatioForQuality({
  width,
  height,
  devicePixelRatio,
  touchFirst,
  tier,
}: RenderPixelRatioInput) {
  const safeWidth = Math.max(1, Number.isFinite(width) ? width : 1);
  const safeHeight = Math.max(1, Number.isFinite(height) ? height : 1);
  const safeDeviceRatio = Number.isFinite(devicePixelRatio)
    ? Math.max(1, devicePixelRatio)
    : 1;
  const pixelBudget = touchFirst
    ? TOUCH_PIXEL_BUDGET
    : DESKTOP_PIXEL_BUDGET;
  const ratioCap = touchFirst
    ? TOUCH_PIXEL_RATIO_CAP
    : DESKTOP_PIXEL_RATIO_CAP;
  const budgetRatio = Math.sqrt(pixelBudget / (safeWidth * safeHeight));
  const tierScale = qualityProfileForTier(tier).resolutionScale;

  return clamp(
    Math.min(safeDeviceRatio, ratioCap, budgetRatio) * tierScale,
    MINIMUM_PIXEL_RATIO,
    ratioCap,
  );
}

/** Babylon hardware scaling is the inverse of the desired render pixel ratio. */
export function hardwareScalingLevelForPixelRatio(pixelRatio: number) {
  if (!Number.isFinite(pixelRatio) || pixelRatio <= 0) return 1;
  return 1 / pixelRatio;
}

export function pixelRatioForHardwareScalingLevel(hardwareScalingLevel: number) {
  if (!Number.isFinite(hardwareScalingLevel) || hardwareScalingLevel <= 0) {
    return 1;
  }
  return 1 / hardwareScalingLevel;
}

export interface QualityGovernorConfig {
  slowFrameThresholdMs: number;
  headroomFrameThresholdMs: number;
  demoteAfterMs: number;
  promoteAfterMs: number;
  changeCooldownMs: number;
  maximumAcceptedFrameTimeMs: number;
}

export const DEFAULT_QUALITY_GOVERNOR_CONFIG: Readonly<QualityGovernorConfig> =
  Object.freeze({
    slowFrameThresholdMs: 20,
    headroomFrameThresholdMs: 14,
    demoteAfterMs: 2_000,
    promoteAfterMs: 9_000,
    changeCooldownMs: 2_500,
    // The runtime clamps visible frame deltas to 250 ms. Accept that entire
    // range as real performance evidence so a 4-10 FPS phone can still shed
    // effects instead of being mistaken for a debugger or background tab.
    maximumAcceptedFrameTimeMs: 250,
  });

export interface QualityFrameSample {
  frameTimeMs: number;
  /** Wall time represented by this sample. Defaults to frameTimeMs. */
  sampleDurationMs?: number;
  /** True only at a pause, restart, countdown, or authored sector boundary. */
  promotionBoundary?: boolean;
  /** Background tabs and interrupted frames must not count as evidence. */
  suspended?: boolean;
}

export type QualityChangeDirection = 'demoted' | 'promoted' | null;

export interface QualityDecision {
  tier: QualityTier;
  profile: QualityProfile;
  changed: boolean;
  direction: QualityChangeDirection;
  slowEvidenceMs: number;
  headroomEvidenceMs: number;
}

function positiveFinite(value: number, fallback: number) {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function normalizedConfig(
  config: Partial<QualityGovernorConfig>,
): QualityGovernorConfig {
  const defaults = DEFAULT_QUALITY_GOVERNOR_CONFIG;
  const headroomFrameThresholdMs = positiveFinite(
    config.headroomFrameThresholdMs ?? defaults.headroomFrameThresholdMs,
    defaults.headroomFrameThresholdMs,
  );
  const slowFrameThresholdMs = Math.max(
    positiveFinite(
      config.slowFrameThresholdMs ?? defaults.slowFrameThresholdMs,
      defaults.slowFrameThresholdMs,
    ),
    headroomFrameThresholdMs + 0.1,
  );

  return {
    slowFrameThresholdMs,
    headroomFrameThresholdMs,
    demoteAfterMs: positiveFinite(
      config.demoteAfterMs ?? defaults.demoteAfterMs,
      defaults.demoteAfterMs,
    ),
    promoteAfterMs: positiveFinite(
      config.promoteAfterMs ?? defaults.promoteAfterMs,
      defaults.promoteAfterMs,
    ),
    changeCooldownMs: positiveFinite(
      config.changeCooldownMs ?? defaults.changeCooldownMs,
      defaults.changeCooldownMs,
    ),
    maximumAcceptedFrameTimeMs: Math.max(
      positiveFinite(
        config.maximumAcceptedFrameTimeMs ??
          defaults.maximumAcceptedFrameTimeMs,
        defaults.maximumAcceptedFrameTimeMs,
      ),
      slowFrameThresholdMs,
    ),
  };
}

export class QualityGovernor {
  private tier: QualityTier;
  private readonly config: QualityGovernorConfig;
  private slowEvidenceMs = 0;
  private headroomEvidenceMs = 0;
  private timeSinceChangeMs = Number.POSITIVE_INFINITY;

  constructor(
    initialTier: QualityTier,
    config: Partial<QualityGovernorConfig> = {},
  ) {
    this.tier = initialTier;
    this.config = normalizedConfig(config);
  }

  getTier() {
    return this.tier;
  }

  getProfile() {
    return qualityProfileForTier(this.tier);
  }

  resetEvidence() {
    this.slowEvidenceMs = 0;
    this.headroomEvidenceMs = 0;
  }

  observe(sample: QualityFrameSample): QualityDecision {
    if (sample.suspended) {
      this.resetEvidence();
      return this.decision(null);
    }

    const frameTimeMs = sample.frameTimeMs;
    if (
      !Number.isFinite(frameTimeMs) ||
      frameTimeMs <= 0 ||
      frameTimeMs > this.config.maximumAcceptedFrameTimeMs
    ) {
      return this.decision(null);
    }

    const requestedDuration = sample.sampleDurationMs ?? frameTimeMs;
    const sampleDurationMs = clamp(
      Number.isFinite(requestedDuration) ? requestedDuration : frameTimeMs,
      0,
      this.config.maximumAcceptedFrameTimeMs,
    );
    this.timeSinceChangeMs += sampleDurationMs;

    if (frameTimeMs >= this.config.slowFrameThresholdMs) {
      this.slowEvidenceMs += sampleDurationMs;
      this.headroomEvidenceMs = 0;
    } else if (frameTimeMs <= this.config.headroomFrameThresholdMs) {
      this.headroomEvidenceMs += sampleDurationMs;
      this.slowEvidenceMs = 0;
    } else {
      // The gap between thresholds is intentional hysteresis. Middling frames
      // prove neither sustained overload nor stable promotion headroom.
      this.resetEvidence();
    }

    const tierIndex = QUALITY_TIER_ORDER.indexOf(this.tier);
    const changeAllowed =
      this.timeSinceChangeMs >= this.config.changeCooldownMs;

    if (
      changeAllowed &&
      this.slowEvidenceMs >= this.config.demoteAfterMs &&
      tierIndex < QUALITY_TIER_ORDER.length - 1
    ) {
      this.tier = QUALITY_TIER_ORDER[tierIndex + 1];
      this.afterChange();
      return this.decision('demoted');
    }

    if (
      changeAllowed &&
      sample.promotionBoundary === true &&
      this.headroomEvidenceMs >= this.config.promoteAfterMs &&
      tierIndex > 0
    ) {
      this.tier = QUALITY_TIER_ORDER[tierIndex - 1];
      this.afterChange();
      return this.decision('promoted');
    }

    return this.decision(null);
  }

  private afterChange() {
    this.timeSinceChangeMs = 0;
    this.resetEvidence();
  }

  private decision(direction: QualityChangeDirection): QualityDecision {
    return {
      tier: this.tier,
      profile: this.getProfile(),
      changed: direction !== null,
      direction,
      slowEvidenceMs: this.slowEvidenceMs,
      headroomEvidenceMs: this.headroomEvidenceMs,
    };
  }
}
