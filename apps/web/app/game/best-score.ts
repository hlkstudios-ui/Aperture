export const SIGNAL_RUN_BEST_KEY = 'signal-run-best';
export const SIGNAL_LOOM_BEST_KEY = 'signal-loom-best';

type ScoreStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function normalizeBestScore(value: unknown): number {
  const score = Number(value);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.floor(score);
}

export function readBestScore(
  storage: Pick<ScoreStorage, 'getItem'> | null,
  key = SIGNAL_RUN_BEST_KEY,
): number {
  if (!storage) return 0;
  try {
    return normalizeBestScore(storage.getItem(key));
  } catch {
    return 0;
  }
}

export function commitBestScore(
  storage: ScoreStorage | null,
  candidate: number,
  inMemoryBest: number,
  key = SIGNAL_RUN_BEST_KEY,
): number {
  const best = Math.max(
    normalizeBestScore(candidate),
    normalizeBestScore(inMemoryBest),
    readBestScore(storage, key),
  );
  try {
    storage?.setItem(key, String(best));
  } catch {
    // Storage may be denied; the caller still receives a session-safe best.
  }
  return best;
}
