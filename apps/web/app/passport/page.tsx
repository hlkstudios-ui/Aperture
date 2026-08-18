import Link from "next/link";

import { SiteHeader } from "@/app/components/site-header";
import { passportFetch, type Distribution } from "@/app/lib/passport";

function DistributionList({ title, items }: { title: string; items: Distribution[] }) {
  return <section className="passport-panel"><p className="eyebrow">Distribution</p><h2>{title}</h2>{items.length ? <ol className="passport-bars">{items.map((item) => <li key={item.key}><div><strong>{item.label}</strong><span>{item.count} view{item.count === 1 ? "" : "s"} · {item.percentage}%</span></div><span style={{ width: `${item.percentage}%` }} /></li>)}</ol> : <p className="passport-empty-copy">Complete a title with this metadata to populate the distribution.</p>}</section>;
}

export default async function PassportPage({ searchParams }: { searchParams: Promise<{ year?: string }> }) {
  const params = await searchParams;
  const parsed = params.year ? Number(params.year) : undefined;
  const year = parsed && Number.isInteger(parsed) ? parsed : undefined;
  const report = await passportFetch(year);
  return <main className="catalog-page passport-page"><SiteHeader />
    <header className="library-heading"><p className="eyebrow">Private to your active profile</p><h1>Cinema Passport</h1><p>{report.year ? `${report.year} annual cinema report` : "Your durable personal cinema history, built only from persisted viewing activity."}</p></header>
    <nav className="passport-years" aria-label="Cinema report year"><Link className={!report.year ? "active" : ""} href="/passport">Lifetime</Link>{report.available_years.map((item) => <Link className={report.year === item ? "active" : ""} href={`/passport?year=${item}`} key={item}>{item}</Link>)}</nav>
    <section className="passport-stat-grid" aria-label="Viewing statistics"><article><strong>{report.films_watched}</strong><span>Films watched</span></article><article><strong>{report.episodes_watched}</strong><span>Episodes watched</span></article><article><strong>{report.observed_watch_hours}</strong><span>Observed hours</span></article><article><strong>{report.first_watches}</strong><span>First watches</span></article><article><strong>{report.rewatches}</strong><span>Rewatches</span></article><article><strong>{report.countries_explored}</strong><span>Countries explored</span></article></section>
    <section className="passport-disclosure"><strong>Activity-derived and private.</strong><span>Watch time is the bounded playback time reported by this profile—not an estimate from runtime. Annual reports are not public or shareable until explicit privacy controls exist.</span></section>
    <div className="passport-grid"><DistributionList title="Favorite genres" items={report.favorite_genres} /><DistributionList title="Countries explored" items={report.country_distribution} /><DistributionList title="Decades" items={report.decade_distribution} />
      <section className="passport-panel"><p className="eyebrow">People across completed titles</p><h2>Favorite creators</h2>{report.favorite_creators.length ? <ol className="creator-list">{report.favorite_creators.map((creator) => <li key={creator.person_id}><strong>{creator.name}</strong><span>{creator.roles.join(" · ")} · {creator.completed_views} completed view{creator.completed_views === 1 ? "" : "s"}</span></li>)}</ol> : <p className="passport-empty-copy">Creator rankings appear only when completed titles have credited people.</p>}</section>
      <section className="passport-panel passport-wide"><p className="eyebrow">First watch and rewatch ledger</p><h2>Viewing history</h2>{report.history.length ? <ol className="passport-history">{report.history.map((item) => <li key={`${item.kind}:${item.title}:${item.activity_number}:${item.started_at}`}><div><strong>{item.title}</strong>{item.parent_title ? <span>{item.parent_title}</span> : null}</div><span className={`history-state ${item.completed ? "completed" : "in-progress"}`}>{item.is_rewatch ? "Rewatch" : "First watch"} · {item.completed ? "Completed" : "In progress"}</span><time dateTime={item.started_at}>{new Date(item.started_at).toLocaleDateString()}</time></li>)}</ol> : <p className="passport-empty-copy">Start watching a title to stamp the first page of this Passport.</p>}</section>
    </div>
  </main>;
}
