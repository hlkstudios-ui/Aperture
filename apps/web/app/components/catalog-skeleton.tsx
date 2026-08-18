export function CatalogSkeleton() {
  return (
    <main
      className="catalog-page skeleton-page"
      aria-busy="true"
      aria-label="Loading catalog"
    >
      <div className="skeleton hero-skeleton" />
      <div className="skeleton-line" />
      <div className="skeleton-grid">
        {Array.from({ length: 4 }, (_, i) => (
          <div className="skeleton card-skeleton" key={i} />
        ))}
      </div>
    </main>
  );
}
