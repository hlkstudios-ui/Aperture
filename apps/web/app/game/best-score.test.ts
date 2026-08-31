import { describe, expect, it } from 'vitest';
import {
  SIGNAL_RUN_BEST_KEY,
  SIGNAL_LOOM_BEST_KEY,
  commitBestScore,
  normalizeBestScore,
  readBestScore,
} from './best-score';

function memoryStorage(initial = '0') {
  let value: string | null = initial;
  return {
    getItem: () => value,
    setItem: (_key: string, next: string) => {
      value = next;
    },
    value: () => value,
  };
}

describe('Signal Run best-score persistence', () => {
  it('never lets a stale tab overwrite a newer record', () => {
    const storage = memoryStorage('100');
    expect(commitBestScore(storage, 500, 100)).toBe(500);
    expect(commitBestScore(storage, 300, 100)).toBe(500);
    expect(storage.value()).toBe('500');
  });

  it('keeps the session record when storage reads and writes are denied', () => {
    const denied = {
      getItem: () => {
        throw new DOMException('Denied', 'SecurityError');
      },
      setItem: () => {
        throw new DOMException('Denied', 'SecurityError');
      },
    };
    expect(readBestScore(denied)).toBe(0);
    expect(commitBestScore(denied, 300, 240)).toBe(300);
  });

  it('normalizes malformed, negative, and fractional values', () => {
    expect(normalizeBestScore('not-a-score')).toBe(0);
    expect(normalizeBestScore(-12)).toBe(0);
    expect(normalizeBestScore('421.9')).toBe(421);
    expect(SIGNAL_RUN_BEST_KEY).toBe('signal-run-best');
    expect(SIGNAL_LOOM_BEST_KEY).toBe('signal-loom-best');
  });

  it('can isolate a new game mode from the legacy score scale', () => {
    const values = new Map<string, string>([
      [SIGNAL_RUN_BEST_KEY, '9000'],
      [SIGNAL_LOOM_BEST_KEY, '1200'],
    ]);
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };

    expect(readBestScore(storage, SIGNAL_LOOM_BEST_KEY)).toBe(1200);
    expect(commitBestScore(storage, 1800, 0, SIGNAL_LOOM_BEST_KEY)).toBe(1800);
    expect(values.get(SIGNAL_RUN_BEST_KEY)).toBe('9000');
  });
});
