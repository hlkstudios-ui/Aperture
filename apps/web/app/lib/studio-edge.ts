export const STUDIO_EDGE_HEADER = "x-aperture-studio-edge";

export function studioEdgeRequired(): boolean {
  return process.env.PRIVATE_STUDIO_REQUIRED === "true";
}

export function validStudioEdgeValue(supplied: string | null): boolean {
  if (!studioEdgeRequired()) return true;
  const expected = process.env.STUDIO_EDGE_SECRET ?? "";
  if (expected.length < 32 || supplied === null || supplied.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= expected.charCodeAt(index) ^ supplied.charCodeAt(index);
  }
  return difference === 0;
}

export function studioEdgeHeaders(): Record<string, string> {
  if (!studioEdgeRequired()) return {};
  const secret = process.env.STUDIO_EDGE_SECRET ?? "";
  if (secret.length < 32) throw new Error("Private Studio edge secret is not configured");
  return { [STUDIO_EDGE_HEADER]: secret };
}
