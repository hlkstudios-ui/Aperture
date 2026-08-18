export default function Loading() {
  return <main className="route-loading" aria-live="polite" aria-busy="true">
    <span className="route-loading-mark" aria-hidden="true" />
    <p className="eyebrow">Preparing your screen</p>
    <h1>Loading Aperture</h1>
    <div className="route-loading-grid" aria-hidden="true">{Array.from({ length: 8 }, (_, index) => <span key={index} />)}</div>
  </main>;
}
