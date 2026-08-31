export default function StudioLoading() {
  return <main className="studio-route-loading" aria-label="Loading Studio section" aria-busy="true">
    <aside aria-hidden="true"><div className="loading-brand" />{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</aside>
    <section><div className="studio-loading-progress" /><header><span /><h1>Preparing workspace</h1><p>Loading only the section you requested…</p></header><div className="studio-loading-grid" aria-hidden="true"><article /><article /><article /><article /></div></section>
  </main>;
}
