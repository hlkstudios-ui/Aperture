import Link from "next/link";
import { CuratedTitle } from "@/app/lib/curation";

export function CuratedTitleList({ items }: { items: CuratedTitle[] }) {
  return (
    <ol className="curated-title-list">
      {items.map((item) => (
        <li key={item.item_id}>
          <Link href={`/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`}>
            <span className="curated-order">{String(item.position + 1).padStart(2, "0")}</span>
            <span>
              <strong>{item.title}</strong>
              <small>{item.note ?? item.short_description}</small>
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
