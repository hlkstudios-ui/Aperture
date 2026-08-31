"use client";

import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_SITE_BRAND, type SiteBrand } from "@/app/lib/site-brand";

const SiteBrandContext = createContext<SiteBrand>(DEFAULT_SITE_BRAND);

export function SiteBrandProvider({ brand, children }: { brand: SiteBrand; children: ReactNode }) {
  return <SiteBrandContext.Provider value={brand}>{children}</SiteBrandContext.Provider>;
}

export function useSiteBrand(): SiteBrand {
  return useContext(SiteBrandContext);
}

export function SiteBrandWordmark({ className }: { className?: string }) {
  const brand = useSiteBrand();
  return <span className={className}>{brand.short_name.toUpperCase()}</span>;
}
