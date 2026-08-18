import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";

type Snapshot = {
  status: "healthy" | "alerting";
  queues: { media: number; scene: number };
  storage: { available: boolean; registered_bytes: number };
  processing: {
    states: Record<string, number>;
    oldest_queued_seconds: number;
    failures_last_hour: number;
    average_transcode_seconds: number;
  };
  scene_jobs: Record<string, number>;
  alerts: Array<{ code: string; severity: "warning" | "critical" }>;
};

function bytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

export default async function OperationsPage() {
  const [admin, snapshot] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Snapshot>("/admin/operations/observability"),
  ]);
  return <StudioShell admin={admin} active="operations" eyebrow="Production signals" title="Operations">
    <p className="editor-intro">Live queue, storage, processing, and alert signals. Prometheus metrics are separately bearer-protected for the monitoring network.</p>
    <section className="analytics-kpis" aria-label="Operational summary">
      <article><small>Overall state</small><strong>{snapshot.status}</strong></article>
      <article><small>Media backlog</small><strong>{snapshot.queues.media}</strong></article>
      <article><small>Scene backlog</small><strong>{snapshot.queues.scene}</strong></article>
      <article><small>Registered media</small><strong>{bytes(snapshot.storage.registered_bytes)}</strong></article>
      <article><small>Average transcode</small><strong>{snapshot.processing.average_transcode_seconds.toFixed(1)} s</strong></article>
    </section>
    <div className="editor-columns analytics-columns">
      <section className="editor-panel"><p className="eyebrow">Alert boundary</p><h2>Active alerts</h2>
        {snapshot.alerts.length ? <ul className="analytics-events">{snapshot.alerts.map((alert) => <li key={alert.code}><strong>{alert.code.replaceAll("_", " ")}</strong><small>{alert.severity}</small></li>)}</ul> : <p className="studio-empty-inline">No queue, processing, or storage threshold is breached.</p>}
      </section>
      <section className="editor-panel"><p className="eyebrow">Worker state</p><h2>Media processing</h2>
        <dl>{Object.entries(snapshot.processing.states).map(([state, count]) => <div key={state}><dt>{state}</dt><dd>{count}</dd></div>)}</dl>
        <p>Oldest queued job: {snapshot.processing.oldest_queued_seconds.toFixed(1)} seconds</p>
        <p>Failures in the last hour: {snapshot.processing.failures_last_hour}</p>
        <p>Object storage: {snapshot.storage.available ? "available" : "unavailable"}</p>
      </section>
    </div>
  </StudioShell>;
}
