import { headers } from "next/headers";

const GEO_HEADERS = [
  "x-aperture-country",
  "x-aperture-geo-timestamp",
  "x-aperture-geo-signature",
] as const;

export async function forwardedGeoHeaders(): Promise<Record<string, string>> {
  const result: Record<string, string> = {};
  let incoming: Awaited<ReturnType<typeof headers>>;
  try {
    incoming = await headers();
  } catch {
    // Static rendering and isolated unit tests have no request context. Returning
    // no assertion remains fail-closed for every territory-restricted title.
    return result;
  }
  for (const name of GEO_HEADERS) {
    const value = incoming.get(name);
    if (value) result[name] = value;
  }
  return result;
}
