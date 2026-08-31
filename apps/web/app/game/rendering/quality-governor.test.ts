import { describe, expect, it } from 'vitest';
import {
  PROTECTED_GAMEPLAY_CUES,
  QUALITY_TIER_ORDER,
  QualityGovernor,
  hardwareScalingLevelForPixelRatio,
  initialQualityTier,
  pixelRatioForHardwareScalingLevel,
  qualityProfileForTier,
  renderPixelRatioForQuality,
} from './quality-governor';

describe('Babylon quality profiles', () => {
  it('protects every gameplay cue at every visual tier', () => {
    for (const tier of QUALITY_TIER_ORDER) {
      expect(qualityProfileForTier(tier).protectedCues).toBe(
        PROTECTED_GAMEPLAY_CUES,
      );
      expect(Object.values(qualityProfileForTier(tier).protectedCues)).not.toContain(
        false,
      );
    }
  });

  it('starts touch-first devices conservatively without penalizing desktop', () => {
    expect(initialQualityTier(false)).toBe('cinematic');
    expect(initialQualityTier(true)).toBe('balanced');
  });

  it('keeps render resolution inside phone and desktop pixel budgets', () => {
    const desktop = renderPixelRatioForQuality({
      width: 2_560,
      height: 1_440,
      devicePixelRatio: 2,
      touchFirst: false,
      tier: 'cinematic',
    });
    const phone = renderPixelRatioForQuality({
      width: 430,
      height: 932,
      devicePixelRatio: 3,
      touchFirst: true,
      tier: 'balanced',
    });

    expect(2_560 * 1_440 * desktop ** 2).toBeLessThanOrEqual(1_750_001);
    expect(430 * 932 * phone ** 2).toBeLessThanOrEqual(1_350_000);
    expect(desktop).toBeGreaterThanOrEqual(0.48);
    expect(phone).toBeGreaterThanOrEqual(0.48);
  });

  it('maps render pixel ratios to Babylon hardware scaling without drift', () => {
    for (const pixelRatio of [0.48, 0.7, 1, 1.35, 1.4]) {
      const hardwareScale = hardwareScalingLevelForPixelRatio(pixelRatio);
      expect(pixelRatioForHardwareScalingLevel(hardwareScale)).toBeCloseTo(
        pixelRatio,
        12,
      );
    }
    expect(hardwareScalingLevelForPixelRatio(Number.NaN)).toBe(1);
    expect(pixelRatioForHardwareScalingLevel(0)).toBe(1);
  });
});

describe('QualityGovernor', () => {
  it('demotes only after sustained slow-frame evidence', () => {
    const governor = new QualityGovernor('cinematic');
    let decision = governor.observe({ frameTimeMs: 25 });

    for (let sample = 1; sample < 79; sample += 1) {
      decision = governor.observe({ frameTimeMs: 25 });
    }
    expect(decision.changed).toBe(false);
    expect(governor.getTier()).toBe('cinematic');

    decision = governor.observe({ frameTimeMs: 25 });
    expect(decision.direction).toBe('demoted');
    expect(decision.tier).toBe('balanced');
  });

  it('downshifts on sustained very slow visible frames', () => {
    const governor = new QualityGovernor('cinematic');
    let decision = governor.observe({ frameTimeMs: 150 });

    for (let sample = 1; sample < 14; sample += 1) {
      decision = governor.observe({ frameTimeMs: 150 });
    }

    expect(decision.direction).toBe('demoted');
    expect(decision.tier).toBe('balanced');
  });

  it('uses a neutral hysteresis band to reject noisy evidence', () => {
    const governor = new QualityGovernor('cinematic');

    for (let sample = 0; sample < 70; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    const neutral = governor.observe({ frameTimeMs: 17 });

    expect(neutral.slowEvidenceMs).toBe(0);
    for (let sample = 0; sample < 20; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    expect(governor.getTier()).toBe('cinematic');
  });

  it('holds earned promotion headroom until an allowed boundary', () => {
    const governor = new QualityGovernor('balanced');
    let decision = governor.observe({ frameTimeMs: 10 });

    for (let sample = 1; sample < 900; sample += 1) {
      decision = governor.observe({ frameTimeMs: 10 });
    }
    expect(decision.headroomEvidenceMs).toBe(9_000);
    expect(governor.getTier()).toBe('balanced');

    decision = governor.observe({
      frameTimeMs: 10,
      promotionBoundary: true,
    });
    expect(decision.direction).toBe('promoted');
    expect(decision.tier).toBe('cinematic');
  });

  it('enforces a cooldown between consecutive quality changes', () => {
    const governor = new QualityGovernor('cinematic');

    for (let sample = 0; sample < 80; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    expect(governor.getTier()).toBe('balanced');

    for (let sample = 0; sample < 80; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    expect(governor.getTier()).toBe('balanced');

    for (let sample = 0; sample < 20; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    expect(governor.getTier()).toBe('performance');
  });

  it('ignores interrupted frames and clears evidence while suspended', () => {
    const governor = new QualityGovernor('cinematic');

    for (let sample = 0; sample < 70; sample += 1) {
      governor.observe({ frameTimeMs: 25 });
    }
    const interrupted = governor.observe({ frameTimeMs: 1_500 });
    expect(interrupted.slowEvidenceMs).toBe(1_750);

    const suspended = governor.observe({ frameTimeMs: 25, suspended: true });
    expect(suspended.slowEvidenceMs).toBe(0);
    expect(suspended.headroomEvidenceMs).toBe(0);
    expect(governor.getTier()).toBe('cinematic');
  });
});
