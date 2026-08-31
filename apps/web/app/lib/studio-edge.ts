export const STUDIO_EDGE_HEADER = "x-aperture-studio-edge";

export function studioEdgeRequired(env: NodeJS.ProcessEnv = process.env): boolean {
  // A production web process must never expose Studio because an operator
  // forgot the explicit flag. Development and isolated tests retain their
  // local owner workflow unless the private boundary is deliberately enabled.
  return env.NODE_ENV === "production" || env.PRIVATE_STUDIO_REQUIRED === "true";
}

export function validStudioEdgeValue(
  supplied: string | null,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  if (!studioEdgeRequired(env)) return true;
  const expected = env.STUDIO_EDGE_SECRET ?? "";
  if (expected.length < 32 || supplied === null || supplied.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= expected.charCodeAt(index) ^ supplied.charCodeAt(index);
  }
  return difference === 0;
}

export function studioEdgeHeaders(env: NodeJS.ProcessEnv = process.env): Record<string, string> {
  if (!studioEdgeRequired(env)) return {};
  const secret = env.STUDIO_EDGE_SECRET ?? "";
  if (secret.length < 32) throw new Error("Private Studio edge secret is not configured");
  return { [STUDIO_EDGE_HEADER]: secret };
}
