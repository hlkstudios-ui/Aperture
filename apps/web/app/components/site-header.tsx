import { HeaderNavigation } from "@/app/components/header-navigation";
import { featureFlags } from "@/app/lib/feature-flags";

export function SiteHeader() {
  return <HeaderNavigation recommendationsEnabled={featureFlags.experimentalRecommendations} />;
}
