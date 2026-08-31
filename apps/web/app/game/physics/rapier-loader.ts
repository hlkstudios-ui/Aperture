export type RapierApi = (typeof import('@dimforge/rapier3d-compat'))['default'];

let rapierPromise: Promise<RapierApi> | null = null;

/**
 * Loads and initializes Rapier exactly once for this browser realm.
 *
 * Keeping the import behind this function gives Next.js a route-local async
 * chunk instead of adding Rapier's inlined WASM to Aperture's shared bundle.
 * A failed attempt is deliberately retryable (for example after a transient
 * chunk-load failure), while concurrent calls share the same initialization.
 */
export function loadRapier(): Promise<RapierApi> {
  if (rapierPromise) return rapierPromise;

  const pending = import('@dimforge/rapier3d-compat').then(
    async ({ default: RAPIER }) => {
      await RAPIER.init();
      return RAPIER;
    },
  );

  rapierPromise = pending;
  void pending.catch(() => {
    if (rapierPromise === pending) rapierPromise = null;
  });
  return pending;
}

/** Starts route-local loading without making callers handle the promise. */
export function preloadRapier(): void {
  void loadRapier().catch(() => {
    // The explicit create call reports initialization failures to the caller.
  });
}
