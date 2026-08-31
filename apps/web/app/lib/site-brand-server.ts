import { DEFAULT_SITE_BRAND, isSiteBrand, type SiteBrand } from "@/app/lib/site-brand";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

export class SiteBrandUnavailableError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "SiteBrandUnavailableError";
  }
}

function unavailable(message: string, cause?: unknown): SiteBrand {
  if (process.env.NODE_ENV === "production") {
    throw new SiteBrandUnavailableError(message, { cause });
  }
  return DEFAULT_SITE_BRAND;
}

export async function getSiteBrand(): Promise<SiteBrand> {
  try {
    const response = await fetch(`${apiOrigin}/site/brand`, {
      next: { revalidate: 60, tags: ["site-brand"] },
    });
    if (!response.ok) return unavailable(`Brand service returned ${response.status}`);
    const payload: unknown = await response.json();
    return isSiteBrand(payload) ? payload : unavailable("Brand service returned an invalid payload");
  } catch (error) {
    if (error instanceof SiteBrandUnavailableError) throw error;
    return unavailable("Brand service could not be reached", error);
  }
}
