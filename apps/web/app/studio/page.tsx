import Link from "next/link";
import Image from "next/image";
import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie, Series } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import type { LaunchSetupRecord } from "@/app/studio/launch/launch-setup-types";

export const metadata = { title: "Studio" };

type AnalyticsSummary = {
  unique_viewers: number;
  watch_hours: number;
  completion_rate: number;
  totals: Record<string, number>;
  playback_quality: {
    average_startup_ms: number;
    error_rate_percent: number;
    fatal_errors: number;
  };
  daily: Array<{ day: string; event_type: string; event_count: number }>;
};

type OperationsSnapshot = {
  status: "healthy" | "alerting";
  queues: { media: number; scene: number };
  storage: { available: boolean; registered_bytes: number };
  processing: {
    states: Record<string, number>;
    failures_last_hour: number;
    average_transcode_seconds: number;
  };
  alerts: Array<{ code: string; severity: "warning" | "critical" }>;
};

type SupportCount = { total: number };
type MoneyAmount = { amount: number; currency: string };
type RevenueSnapshot = { connection: string; livemode: boolean | null; payouts_enabled: boolean; recorded_receipts_30d: MoneyAmount[]; available: MoneyAmount[]; pending: MoneyAmount[]; notice: string | null };
type TrendingTitle = { external_id: number; title: string; overview: string; release_date: string | null; poster_url: string | null; backdrop_url: string | null; popularity: number; vote_average: number };
type TrendingPulse = { available: boolean; movies: TrendingTitle[]; series: TrendingTitle[] };

function StudioLinkIcon({ name }: { name: "chart" | "pulse" | "catalog" | "revenue" | "search" | "upload" }) {
  const paths = {
    chart: <><path d="M4 18V9m6 9V5m6 13v-7m4 7H2" /></>,
    pulse: <><path d="M3 12h4l2.2-5 4.1 10 2.1-5H21" /></>,
    catalog: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M8 4v16m-5-5h5m8-11v16" /></>,
    revenue: <><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5c-.7-.7-1.8-1-3.2-1-1.8 0-3 .9-3 2.2 0 3.4 6.2 1.5 6.2 4.8 0 1.4-1.3 2.3-3.3 2.3-1.4 0-2.7-.4-3.7-1.3M12 5.5v13" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4M4 14v6h16v-6" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function ActionLink({ href, icon, children }: { href: string; icon: Parameters<typeof StudioLinkIcon>[0]["name"]; children: ReactNode }) {
  return <Link className="studio-action-link" href={href}><StudioLinkIcon name={icon} /><span>{children}</span><b aria-hidden="true">→</b></Link>;
}

function compactNumber(value: number) {
  return new Intl.NumberFormat("en-CA", {
    notation: value >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function storageLabel(value: number) {
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

function relativeDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function money(value: MoneyAmount | undefined) {
  if (!value) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: value.currency.toUpperCase() }).format(value.amount / 100);
}

function moneyList(values: MoneyAmount[]) {
  return values.length ? values.map((value) => money(value)).join(" · ") : "—";
}

export default async function Studio() {
  const admin = await requireAdminSession();
  if (process.env.APP_ENV !== "test") {
    const launchSetup = await adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand");
    if (!launchSetup.published_at) redirect("/studio/launch");
  }
  const [movies, series, analytics, operations, users, subscriptions, revenue, trending] =
    await Promise.all([
      adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
      adminCatalogFetch<Series[]>("/admin/catalog/series"),
      adminCatalogFetch<AnalyticsSummary>("/admin/analytics/summary?days=30"),
      adminCatalogFetch<OperationsSnapshot>("/admin/operations/observability"),
      adminCatalogFetch<SupportCount>("/admin/support/users?limit=1"),
      adminCatalogFetch<SupportCount>("/admin/support/subscriptions?limit=1"),
      adminCatalogFetch<RevenueSnapshot>("/admin/revenue"),
      adminCatalogFetch<TrendingPulse>("/admin/tmdb/trending").catch(() => ({ available: false, movies: [], series: [] })),
    ]);

  const titles = [...movies, ...series];
  const published = titles.filter((item) => item.status === "published").length;
  const ready = titles.filter((item) => item.status === "ready").length;
  const drafts = titles.filter((item) => item.status === "draft").length;
  const episodeCount = series.reduce(
    (total, show) => total + show.seasons.reduce(
      (seasonTotal, season) => seasonTotal + season.episodes.length,
      0,
    ),
    0,
  );
  const recentTitles = titles
    .toSorted((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 5);
  const playStarts = analytics.totals.play_start ?? 0;
  const dailyPlays = analytics.daily
    .filter((item) => item.event_type === "play_start")
    .toSorted((left, right) => left.day.localeCompare(right.day))
    .slice(-14);
  const maxDailyPlay = Math.max(1, ...dailyPlays.map((item) => item.event_count));
  const processingActive = Object.entries(operations.processing.states)
    .filter(([state]) => !["ready", "failed", "cancelled"].includes(state))
    .reduce((total, [, count]) => total + count, 0);

  return (
    <StudioShell
      admin={admin}
      active="dashboard"
      eyebrow="Executive overview"
      title="The projection room"
      actions={
        <div className={`studio-health ${operations.status}`}>
          <span /> {operations.status === "healthy" ? "All systems ready" : "Attention required"}
        </div>
      }
    >
      <section className="studio-command-hero" aria-labelledby="command-title">
        <div>
          <p className="eyebrow">Today in Aperture</p>
          <h2 id="command-title">Program the screen. Read the room.</h2>
          <p>
            A live view of the catalog, audience, and production pipeline—built
            from operational data, not simulated performance.
          </p>
          <div className="studio-command-actions">
            <Link className="studio-primary studio-command-action" href="/studio/movies/new"><StudioLinkIcon name="search" /><span>Discover a movie</span></Link>
            <Link className="studio-secondary studio-command-action" href="/studio/series/new"><StudioLinkIcon name="catalog" /><span>Build a series</span></Link>
            <Link className="studio-tertiary" href="/studio/uploads">Upload media →</Link>
          </div>
        </div>
        <dl className="studio-hero-ledger">
          <div><dt>Live titles</dt><dd>{published}</dd></div>
          <div><dt>In preparation</dt><dd>{drafts + ready}</dd></div>
          <div><dt>Audience profiles</dt><dd>{compactNumber(users.total)}</dd></div>
          <div><dt>Active subscriptions</dt><dd>{compactNumber(subscriptions.total)}</dd></div>
        </dl>
      </section>

      <section className="studio-metric-strip" aria-label="Thirty-day performance">
        <article><span>01</span><small>Unique viewers</small><strong>{compactNumber(analytics.unique_viewers)}</strong><p>Last 30 days</p></article>
        <article><span>02</span><small>Play starts</small><strong>{compactNumber(playStarts)}</strong><p>Qualified audience events</p></article>
        <article><span>03</span><small>Watch time</small><strong>{analytics.watch_hours.toFixed(1)}<em>h</em></strong><p>Across published programming</p></article>
        <article><span>04</span><small>Completion</small><strong>{analytics.completion_rate.toFixed(1)}<em>%</em></strong><p>Completed plays / starts</p></article>
      </section>

      <section className="studio-revenue-brief" aria-labelledby="revenue-brief-title">
        <header><div><p className="eyebrow">Subscription revenue</p><h2 id="revenue-brief-title">The box office</h2></div><ActionLink href="/studio/revenue" icon="revenue">Revenue desk</ActionLink></header>
        <dl>
          <div><dt>Recorded receipts · 30 days</dt><dd>{moneyList(revenue.recorded_receipts_30d)}<small>Successful verified subscription invoices</small></dd></div>
          <div><dt>Available at Stripe</dt><dd>{moneyList(revenue.available)}<small>{revenue.connection === "connected" ? "Eligible for payout" : "Connect Stripe to load"}</small></dd></div>
          <div><dt>Pending settlement</dt><dd>{moneyList(revenue.pending)}<small>{revenue.livemode === false ? "Stripe test mode" : revenue.livemode ? "Stripe live mode" : "Provider unavailable"}</small></dd></div>
        </dl>
        {revenue.notice && <p className="studio-revenue-notice">{revenue.notice}</p>}
      </section>

      <section className="studio-world-pulse" aria-labelledby="world-pulse-title">
        <header>
          <div><p className="eyebrow">Global discovery · powered by TMDB</p><h2 id="world-pulse-title">What the world is watching</h2><p>Today’s ranked attention signal across movies and television. Use it to spot demand, then acquire the metadata and attach your licensed CDN source.</p></div>
          <ActionLink href="/studio/movies/new" icon="search">Search TMDB movies</ActionLink>
        </header>
        {trending.available ? <div className="studio-trend-columns">
          {(["movies", "series"] as const).map((kind) => <section key={kind} aria-labelledby={`trend-${kind}`}>
            <div className="studio-trend-heading"><div><span>{kind === "movies" ? "01" : "02"}</span><h3 id={`trend-${kind}`}>Trending {kind}</h3></div><small>Updated every 10 min</small></div>
            <ol>{trending[kind].slice(0, 5).map((title, index) => <li key={title.external_id}>
              <div className="studio-trend-poster">{title.poster_url ? <Image src={title.poster_url} alt="" width={120} height={180} sizes="60px" /> : <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>}<b>{String(index + 1).padStart(2, "0")}</b></div>
              <div><small>{title.release_date?.slice(0, 4) ?? "Current"} · TMDB trend</small><strong>{title.title}</strong><p>{title.overview || "Global audience attention is rising."}</p><span>★ {title.vote_average.toFixed(1)} <i>Attention {Math.round(title.popularity)}</i></span></div>
              <Link aria-label={`${kind === "movies" ? "Acquire" : "Open series tools for"} ${title.title}`} href={kind === "movies" ? `/studio/movies/new?q=${encodeURIComponent(title.title)}` : "/studio/series/new"}>→</Link>
            </li>)}</ol>
          </section>)}
        </div> : <div className="studio-world-offline"><StudioLinkIcon name="pulse" /><div><strong>Global pulse is temporarily unavailable</strong><p>Your owned catalog and operations remain available. TMDB discovery will reconnect automatically.</p></div></div>}
      </section>

      <div className="studio-dashboard-grid">
        <section className="studio-dashboard-panel audience-panel" aria-labelledby="audience-title">
          <header><div><p className="eyebrow">Audience pulse</p><h2 id="audience-title">Daily starts</h2></div><ActionLink href="/studio/analytics" icon="chart">Full analytics</ActionLink></header>
          {dailyPlays.length ? (
            <div className="studio-spark-bars" aria-label="Play starts over the last 14 measured days">
              {dailyPlays.map((item) => (
                <div key={item.day} title={`${item.day}: ${item.event_count} play starts`}>
                  <i style={{ height: `${Math.max(6, item.event_count / maxDailyPlay * 100)}%` }} />
                  <span>{item.day.slice(5)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="studio-dashboard-empty"><strong>Awaiting the first screening</strong><p>Daily audience activity will appear after qualified playback begins.</p></div>
          )}
          <footer>
            <span>Startup <strong>{analytics.playback_quality.average_startup_ms.toFixed(0)} ms</strong></span>
            <span>Error rate <strong>{analytics.playback_quality.error_rate_percent.toFixed(2)}%</strong></span>
            <span>Fatal errors <strong>{analytics.playback_quality.fatal_errors}</strong></span>
          </footer>
        </section>

        <section className="studio-dashboard-panel operations-panel" aria-labelledby="operations-title">
          <header><div><p className="eyebrow">Projection booth</p><h2 id="operations-title">System readiness</h2></div><ActionLink href="/studio/operations" icon="pulse">Inspect</ActionLink></header>
          <div className={`studio-readiness-orb ${operations.status}`} aria-hidden="true"><span>{operations.status === "healthy" ? "READY" : "CHECK"}</span></div>
          <dl>
            <div><dt>Media queue</dt><dd>{operations.queues.media}</dd></div>
            <div><dt>Scene queue</dt><dd>{operations.queues.scene}</dd></div>
            <div><dt>Processing now</dt><dd>{processingActive}</dd></div>
            <div><dt>Storage</dt><dd>{operations.storage.available ? storageLabel(operations.storage.registered_bytes) : "Offline"}</dd></div>
          </dl>
          {operations.alerts.length > 0 && <p className="studio-alert-summary">{operations.alerts.length} active operational alert{operations.alerts.length === 1 ? "" : "s"}</p>}
        </section>

        <section className="studio-dashboard-panel catalog-panel" aria-labelledby="catalog-title">
          <header><div><p className="eyebrow">Program slate</p><h2 id="catalog-title">Catalog composition</h2></div><ActionLink href="/studio/content" icon="catalog">Manage all</ActionLink></header>
          <div className="studio-slate-summary">
            <div><strong>{movies.length}</strong><span>Movies</span></div>
            <div><strong>{series.length}</strong><span>Series</span></div>
            <div><strong>{episodeCount}</strong><span>Episodes</span></div>
          </div>
          <div className="studio-status-track" role="img" aria-label={`${published} published, ${ready} ready, ${drafts} draft`}>
            <span className="published" style={{ flexGrow: published || 0.15 }} />
            <span className="ready" style={{ flexGrow: ready || 0.15 }} />
            <span className="draft" style={{ flexGrow: drafts || 0.15 }} />
          </div>
          <ul className="studio-status-legend">
            <li><i className="published" />Published <strong>{published}</strong></li>
            <li><i className="ready" />Ready <strong>{ready}</strong></li>
            <li><i className="draft" />Draft <strong>{drafts}</strong></li>
          </ul>
        </section>

        <section className="studio-dashboard-panel activity-panel" aria-labelledby="activity-title">
          <header><div><p className="eyebrow">Latest cuts</p><h2 id="activity-title">Recently updated</h2></div></header>
          {recentTitles.length ? <ol>{recentTitles.map((item, index) => {
            const kind = "seasons" in item ? "series" : "movie";
            return <li key={`${kind}:${item.id}`}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.title}</strong><small>{kind} · {item.status}</small></div><time dateTime={item.updated_at}>{relativeDate(item.updated_at)}</time><Link aria-label={`Edit ${item.title}`} href={`/studio/${kind === "movie" ? "movies" : "series"}/${item.id}`}>Open</Link></li>;
          })}</ol> : <div className="studio-dashboard-empty"><strong>No titles in the slate</strong><p>Start with a movie or series draft.</p></div>}
        </section>
      </div>
    </StudioShell>
  );
}
