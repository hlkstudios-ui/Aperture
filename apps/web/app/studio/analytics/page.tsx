import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";

type Summary = {
  retention_days: number;
  totals: Record<string, number>;
  unique_viewers: number;
  watch_hours: number;
  completion_rate: number;
  playback_quality: {
    startup_samples: number;
    average_startup_ms: number;
    buffer_events: number;
    buffer_seconds: number;
    fatal_errors: number;
    error_rate_percent: number;
    quality_changes: number;
  };
  daily: Array<{ day: string; event_type: string; event_count: number }>;
  recent: Array<{
    id: string; event_type: string; title_label: string | null;
    profile_id: string; query: string | null; is_bot: boolean;
    is_internal: boolean; occurred_at: string;
  }>;
  titles: Array<{
    title_label: string; plays: number; completions: number; watch_hours: number;
  }>;
};

function label(value: string) { return value.replaceAll("_", " "); }
function compact(value: number) {
  return new Intl.NumberFormat("en-CA", {
    notation: value >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

export default async function AnalyticsPage() {
  const [admin, summary] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Summary>("/admin/analytics/summary?days=30"),
  ]);
  const days = new Map<string, { plays: number; completions: number; searches: number }>();
  for (const metric of summary.daily) {
    const day = days.get(metric.day) ?? { plays: 0, completions: 0, searches: 0 };
    if (metric.event_type === "play_start") day.plays += metric.event_count;
    if (metric.event_type === "completion") day.completions += metric.event_count;
    if (metric.event_type === "search") day.searches += metric.event_count;
    days.set(metric.day, day);
  }
  const timeline = [...days.entries()]
    .toSorted(([left], [right]) => left.localeCompare(right))
    .slice(-30);
  const maxDaily = Math.max(1, ...timeline.map(([, values]) =>
    Math.max(values.plays, values.completions, values.searches),
  ));

  return (
    <StudioShell
      admin={admin}
      active="analytics"
      eyebrow="Audience intelligence"
      title="Performance ledger"
    >
      <section className="studio-analytics-intro">
        <div>
          <p className="eyebrow">30-day intelligence window</p>
          <h2>See what earns attention—and what interrupts it.</h2>
          <p>Qualified audience events exclude identified bots and internal activity. Raw events remain restricted and are retained for {summary.retention_days} days.</p>
        </div>
        <dl><div><dt>Window</dt><dd>30 days</dd></div><div><dt>Privacy</dt><dd>Consent gated</dd></div><div><dt>Source</dt><dd>Daily aggregates</dd></div></dl>
      </section>

      <section className="studio-metric-strip analytics-ledger" aria-label="Audience performance summary">
        <article><span>01</span><small>Unique viewers</small><strong>{compact(summary.unique_viewers)}</strong><p>Qualified profiles</p></article>
        <article><span>02</span><small>Play starts</small><strong>{compact(summary.totals.play_start ?? 0)}</strong><p>Viewing sessions opened</p></article>
        <article><span>03</span><small>Watch time</small><strong>{summary.watch_hours.toFixed(1)}<em>h</em></strong><p>Measured progress</p></article>
        <article><span>04</span><small>Completion</small><strong>{summary.completion_rate.toFixed(1)}<em>%</em></strong><p>Completions / starts</p></article>
      </section>

      <section className="studio-dashboard-panel studio-audience-chart" aria-labelledby="trajectory-title">
        <header><div><p className="eyebrow">Audience trajectory</p><h2 id="trajectory-title">Starts, completions, and discovery</h2></div><ul><li><i className="plays" />Starts</li><li><i className="completions" />Completions</li><li><i className="searches" />Searches</li></ul></header>
        {timeline.length ? (
          <div className="studio-grouped-chart">
            {timeline.map(([day, values]) => (
              <div key={day} title={`${day}: ${values.plays} starts, ${values.completions} completions, ${values.searches} searches`}>
                <span>
                  <i className="plays" style={{ height: `${Math.max(values.plays ? 4 : 0, values.plays / maxDaily * 100)}%` }} />
                  <i className="completions" style={{ height: `${Math.max(values.completions ? 4 : 0, values.completions / maxDaily * 100)}%` }} />
                  <i className="searches" style={{ height: `${Math.max(values.searches ? 4 : 0, values.searches / maxDaily * 100)}%` }} />
                </span>
                <small>{day.slice(5)}</small>
              </div>
            ))}
          </div>
        ) : <div className="studio-dashboard-empty"><strong>No qualified events yet</strong><p>The trajectory begins when audience playback or discovery events are aggregated.</p></div>}
      </section>

      <div className="studio-quality-grid">
        <section className="studio-dashboard-panel studio-quality-panel" aria-labelledby="quality-title">
          <header><div><p className="eyebrow">Playback quality</p><h2 id="quality-title">Experience health</h2></div></header>
          <dl><div><dt>Average startup</dt><dd>{summary.playback_quality.average_startup_ms.toFixed(0)} <small>ms</small></dd></div><div><dt>Buffer time</dt><dd>{summary.playback_quality.buffer_seconds.toFixed(2)} <small>s</small></dd></div><div><dt>Error rate</dt><dd>{summary.playback_quality.error_rate_percent.toFixed(2)} <small>%</small></dd></div><div><dt>Quality shifts</dt><dd>{summary.playback_quality.quality_changes}</dd></div></dl>
          <p>{summary.playback_quality.startup_samples ? `${compact(summary.playback_quality.startup_samples)} startup samples inform this view.` : "Awaiting the first playback-quality sample."}</p>
        </section>
        <section className="studio-dashboard-panel studio-title-performance" aria-labelledby="titles-title">
          <header><div><p className="eyebrow">Program performance</p><h2 id="titles-title">Titles earning time</h2></div></header>
          {summary.titles.length ? <table className="analytics-table"><thead><tr><th>Title</th><th>Plays</th><th>Complete</th><th>Hours</th></tr></thead><tbody>{summary.titles.slice(0, 10).map((item) => <tr key={item.title_label}><td>{item.title_label}</td><td>{item.plays}</td><td>{item.completions}</td><td>{item.watch_hours.toFixed(2)}</td></tr>)}</tbody></table> : <div className="studio-dashboard-empty"><strong>No title ranking yet</strong><p>Playback will populate program-level performance.</p></div>}
        </section>
      </div>

      <section className="studio-dashboard-panel studio-event-ledger" aria-labelledby="events-title">
        <header><div><p className="eyebrow">Restricted event ledger</p><h2 id="events-title">Recent signals</h2></div><span>Administrator only</span></header>
        {summary.recent.length ? <ol>{summary.recent.slice(0, 20).map((event, index) => <li key={event.id}><span>{String(index + 1).padStart(2, "0")}</span><strong>{label(event.event_type)}</strong><p>{event.title_label ?? (event.query ? `“${event.query}”` : "Platform")}</p><small>{new Date(event.occurred_at).toLocaleString("en-CA")} · profile {event.profile_id.slice(0, 8)}{event.is_bot ? " · bot" : ""}{event.is_internal ? " · internal" : ""}</small></li>)}</ol> : <div className="studio-dashboard-empty"><strong>The event ledger is quiet</strong><p>No raw events are retained in this window.</p></div>}
      </section>
    </StudioShell>
  );
}
