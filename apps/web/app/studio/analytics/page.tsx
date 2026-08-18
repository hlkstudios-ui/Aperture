import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";

type Summary = {
  retention_days: number; totals: Record<string, number>; unique_viewers: number;
  watch_hours: number; completion_rate: number;
  playback_quality: { startup_samples: number; average_startup_ms: number; buffer_events: number; buffer_seconds: number; fatal_errors: number; error_rate_percent: number; quality_changes: number };
  daily: Array<{ day: string; event_type: string; event_count: number }>;
  recent: Array<{ id: string; event_type: string; title_label: string | null; profile_id: string; position_seconds: number | null; query: string | null; result_count: number | null; is_bot: boolean; is_internal: boolean; occurred_at: string }>;
  titles: Array<{ title_label: string; plays: number; completions: number; watch_hours: number }>;
};
function label(value: string) { return value.replaceAll("_", " "); }
export default async function AnalyticsPage() {
  const [admin, summary] = await Promise.all([
    requireAdminSession(), adminCatalogFetch<Summary>("/admin/analytics/summary?days=30"),
  ]);
  const maxDaily = Math.max(1, ...summary.daily.map((item) => item.event_count));
  return <StudioShell admin={admin} active="analytics" eyebrow="Audience signals" title="Analytics">
    <p className="editor-intro">Customer events are idempotent, rate-limited, payload-bounded, and retained raw for {summary.retention_days} days. The cards below use separate daily aggregates and exclude identified bots/internal activity.</p>
    <section className="analytics-kpis" aria-label="Platform analytics summary">
      <article><small>Unique viewers</small><strong>{summary.unique_viewers}</strong></article>
      <article><small>Play starts</small><strong>{summary.totals.play_start ?? 0}</strong></article>
      <article><small>Watch hours</small><strong>{summary.watch_hours.toFixed(2)}</strong></article>
      <article><small>Completion</small><strong>{summary.completion_rate.toFixed(1)}%</strong></article>
      <article><small>Searches</small><strong>{summary.totals.search ?? 0}</strong></article>
    </section>
    <section className="analytics-kpis" aria-label="Playback quality summary">
      <article><small>Average startup</small><strong>{summary.playback_quality.average_startup_ms.toFixed(0)} ms</strong></article>
      <article><small>Startup samples</small><strong>{summary.playback_quality.startup_samples}</strong></article>
      <article><small>Buffering</small><strong>{summary.playback_quality.buffer_seconds.toFixed(2)} s</strong></article>
      <article><small>Fatal error rate</small><strong>{summary.playback_quality.error_rate_percent.toFixed(2)}%</strong></article>
      <article><small>Quality changes</small><strong>{summary.playback_quality.quality_changes}</strong></article>
    </section>
    <section className="editor-panel analytics-panel"><div className="form-section-heading"><div><p className="eyebrow">Aggregated metrics</p><h2>Last 30 days</h2></div><span>{summary.daily.length} dimensions</span></div>
      {summary.daily.length ? <div className="analytics-bars">{summary.daily.slice(0, 30).map((item, index) => <div key={`${item.day}:${item.event_type}:${index}`}><span>{item.day.slice(5)} · {label(item.event_type)}</span><i style={{ width: `${Math.max(4, item.event_count / maxDaily * 100)}%` }} /><strong>{item.event_count}</strong></div>)}</div> : <p className="studio-empty-inline">No customer events have been aggregated yet.</p>}
    </section>
    <div className="editor-columns analytics-columns">
      <section className="editor-panel"><div className="form-section-heading"><div><p className="eyebrow">Title performance</p><h2>Plays & completion</h2></div></div>
        {summary.titles.length ? <table className="analytics-table"><thead><tr><th>Title</th><th>Plays</th><th>Complete</th><th>Hours</th></tr></thead><tbody>{summary.titles.map((item) => <tr key={item.title_label}><td>{item.title_label}</td><td>{item.plays}</td><td>{item.completions}</td><td>{item.watch_hours.toFixed(2)}</td></tr>)}</tbody></table> : <p className="studio-empty-inline">Playback will populate per-title aggregates.</p>}
      </section>
      <section className="editor-panel"><div className="form-section-heading"><div><p className="eyebrow">Restricted raw stream</p><h2>Recent events</h2></div><span>Admin only</span></div>
        {summary.recent.length ? <ul className="analytics-events">{summary.recent.slice(0, 20).map((event) => <li key={event.id}><div><strong>{label(event.event_type)}</strong><span>{event.title_label ?? (event.query ? `“${event.query}”` : "Platform")}</span></div><small>{new Date(event.occurred_at).toLocaleString()} · profile {event.profile_id.slice(0, 8)}{event.is_bot ? " · bot" : ""}{event.is_internal ? " · internal" : ""}</small></li>)}</ul> : <p className="studio-empty-inline">No raw events in the selected window.</p>}
      </section>
    </div>
  </StudioShell>;
}
