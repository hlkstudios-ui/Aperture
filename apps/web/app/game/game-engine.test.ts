import { describe, expect, it } from 'vitest';
import {
  DisplayDivisorLatch,
  MOVEMENT_BAFFLE_TELEGRAPH_SECONDS,
  adaptivePixelRatio,
  blockVisualLayout,
  displayDivisorForRefreshRate,
  movementBaffleSignalLayout,
  movementBaffleTelegraphStrength,
  primedDirectionLabel,
} from './game-engine';

describe('adaptive game render quality', () => {
  it('keeps a large desktop canvas inside its pixel budget', () => {
    const ratio = adaptivePixelRatio(2560, 1440, 2, false);

    expect(ratio).toBeGreaterThanOrEqual(0.48);
    expect(2560 * 1440 * ratio ** 2).toBeLessThanOrEqual(1_750_001);
  });

  it('caps high-density phone rendering without making it blurry', () => {
    const ratio = adaptivePixelRatio(430, 932, 3, true);

    expect(ratio).toBe(1.35);
    expect(430 * 932 * ratio ** 2).toBeLessThanOrEqual(1_350_000);
  });

  it('can lower resolution when sustained frame time is slow', () => {
    const fullQuality = adaptivePixelRatio(1440, 900, 2, false, 1);
    const recoveryQuality = adaptivePixelRatio(1440, 900, 2, false, 0.72);

    expect(recoveryQuality).toBeLessThan(fullQuality);
    expect(recoveryQuality).toBeGreaterThanOrEqual(0.48);
  });

  it('derives pooled block visuals from the current collision dimensions', () => {
    const ordinary = blockVisualLayout(2.4, 3.1, 2.4);
    const baffle = blockVisualLayout(8, 20, 2.4);

    expect(ordinary.bodyScale).toEqual({ x: 2.4, y: 3.1, z: 2.4 });
    expect(baffle.bodyScale).toEqual({ x: 8, y: 20, z: 2.4 });
    expect(baffle.warningScale).toEqual({ x: 5.76, y: 1, z: 2.4 });
    expect(baffle.warningOffset).toBeCloseTo(6.8, 10);
    expect(baffle).not.toEqual(ordinary);
  });

  it('telegraphs movement baffles early and consistently at every speed', () => {
    const openingSpeed = 9.5;
    const redlineSpeed = 39;
    const farSeconds = MOVEMENT_BAFFLE_TELEGRAPH_SECONDS + 0.1;
    const readableSeconds = 2.25;
    const nearSeconds = 0.7;

    expect(movementBaffleTelegraphStrength(-openingSpeed * farSeconds, openingSpeed)).toBe(0);
    expect(movementBaffleTelegraphStrength(-redlineSpeed * farSeconds, redlineSpeed)).toBe(0);
    const openingReadable = movementBaffleTelegraphStrength(
      -openingSpeed * readableSeconds,
      openingSpeed,
    );
    const redlineReadable = movementBaffleTelegraphStrength(
      -redlineSpeed * readableSeconds,
      redlineSpeed,
    );
    expect(openingReadable).toBeGreaterThan(0.3);
    expect(redlineReadable).toBeCloseTo(openingReadable, 10);
    expect(movementBaffleTelegraphStrength(-redlineSpeed * nearSeconds, redlineSpeed)).toBe(1);
  });

  it('moves a reused baffle guide to the inner corridor edge when its side flips', () => {
    const rightBaffle = movementBaffleSignalLayout(5, 8, 20, 2.4);
    const leftBaffle = movementBaffleSignalLayout(-5, 8, 20, 2.4);

    expect(rightBaffle.blockingSide).toBe(1);
    expect(leftBaffle.blockingSide).toBe(-1);
    expect(5 + rightBaffle.spineOffsetX).toBe(1);
    expect(-5 + leftBaffle.spineOffsetX).toBe(-1);
    expect(rightBaffle.spineOffsetX).toBe(-leftBaffle.spineOffsetX);
  });

  it('uses even display divisors for high-refresh mobile panels', () => {
    expect(displayDivisorForRefreshRate(60)).toBe(1);
    expect(displayDivisorForRefreshRate(89.9)).toBe(1);
    expect(displayDivisorForRefreshRate(90)).toBe(1);
    expect(displayDivisorForRefreshRate(90.1)).toBe(1);
    expect(displayDivisorForRefreshRate(120)).toBe(2);
    expect(displayDivisorForRefreshRate(144)).toBe(2);
    expect(displayDivisorForRefreshRate(165)).toBe(2);
    expect(displayDivisorForRefreshRate(180)).toBe(3);
    expect(displayDivisorForRefreshRate(240)).toBe(4);

    for (const refreshRate of [60, 90, 120, 144, 165, 180, 240]) {
      const renderedRate = refreshRate / displayDivisorForRefreshRate(refreshRate);
      expect(renderedRate).toBeGreaterThanOrEqual(59);
    }
  });

  it('latches a stable cadence instead of flapping around a refresh boundary', () => {
    const latch = new DisplayDivisorLatch(4);
    for (let sample = 0; sample < 4; sample += 1) {
      latch.update(90.5);
    }
    expect(latch.update(90.5)).toBe(1);

    const observed = Array.from({ length: 40 }, (_, index) =>
      latch.update(index % 2 === 0 ? 89 : 90.5),
    );
    expect(new Set(observed)).toEqual(new Set([1]));

    for (let sample = 0; sample < 4; sample += 1) {
      latch.update(120);
    }
    expect(latch.update(120)).toBe(2);
  });

  it('describes staged cardinal and diagonal steering without noise drift', () => {
    expect(primedDirectionLabel(0.1, -0.1)).toBeNull();
    expect(primedDirectionLabel(1, 0)).toBe('Right');
    expect(primedDirectionLabel(-1, 0)).toBe('Left');
    expect(primedDirectionLabel(0, 1)).toBe('Upper');
    expect(primedDirectionLabel(0, -1)).toBe('Lower');
    expect(primedDirectionLabel(0.8, 0.8)).toBe('Upper right');
    expect(primedDirectionLabel(-0.8, -0.8)).toBe('Lower left');
  });
});
