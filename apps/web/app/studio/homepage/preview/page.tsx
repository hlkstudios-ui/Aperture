import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { PublicHomepage } from "@/app/lib/homepage";
import { requireAdminSession } from "@/app/lib/admin-session";
import { HomepageTitleCard } from "@/app/components/homepage-title-card";
import { StudioShell } from "@/app/studio/components/studio-shell";

export default async function HomepagePreviewPage() {
  const [admin, preview] = await Promise.all([
    requireAdminSession(), adminCatalogFetch<PublicHomepage>("/admin/homepage/preview"),
  ]);
  return <StudioShell admin={admin} active="homepage" eyebrow="Unpublished preview" title="Homepage draft">
    {!preview.hero ? <div className="empty-panel"><h2>No hero selected</h2></div> : <section className="hero catalog-hero"><div className="hero-monogram" aria-hidden="true">{preview.hero.title[0]}</div><p className="eyebrow">Draft hero · {preview.hero.kind}</p><h2>{preview.hero.title}</h2><p>{preview.hero.short_description}</p></section>}
    <section className="catalog-rails">{preview.rails.map((rail) => <div className="rail" key={rail.id}><div className="rail-heading"><div><p className="eyebrow">{rail.eyebrow ?? "Editorial rail"}</p><h2>{rail.title}</h2></div></div><div className="card-rail">{rail.items.map((title) => <HomepageTitleCard title={title} key={`${title.kind}:${title.id}`} />)}</div></div>)}</section>
  </StudioShell>;
}
