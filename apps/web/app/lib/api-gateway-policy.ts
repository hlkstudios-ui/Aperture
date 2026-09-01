export const browserApiPrefixes = [
  "account",
  "admin",
  "analytics",
  "auth",
  "cinephile",
  "clubs",
  "community",
  "curation",
  "playback",
  "platform",
  "profiles",
  "recommendations",
  "scene-intelligence",
] as const;

const browserApiPrefixSet = new Set<string>(browserApiPrefixes);

export function isBrowserApiPrefix(value: string | undefined): boolean {
  return value !== undefined && browserApiPrefixSet.has(value);
}
