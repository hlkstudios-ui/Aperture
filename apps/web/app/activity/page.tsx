import { SiteHeader } from "@/app/components/site-header";
import { ActivityLibrary } from "./activity-library";

export const metadata = { title: "Your Activity" };
export default function ActivityPage() {
  return <main className="catalog-page"><SiteHeader /><header className="library-heading"><p className="eyebrow">Saved on this device</p><h1>Your activity</h1><p>Continue watching, revisit searches, and find titles you saved or liked.</p></header><ActivityLibrary /></main>;
}
