"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import {
  clearClientLibrary,
  readClientLibrary,
  type ClientLibrary,
  type ClientTitle,
} from "@/app/lib/client-state";

const empty: ClientLibrary = {
  viewed: [],
  saved: [],
  liked: [],
  searches: [],
  progress: [],
};

function TitleList({
  items,
  emptyMessage,
}: {
  items: ClientTitle[];
  emptyMessage: string;
}) {
  return items.length ? (
    <div className="activity-title-list">
      {items.map((item) => (
        <Link href={item.href} key={`${item.kind}:${item.id}`}>
          {item.poster_url ? (
            <ResponsivePoster src={item.poster_url} sizes="64px" />
          ) : (
            <span aria-hidden="true">{item.title[0]}</span>
          )}
          <span>
            <strong>{item.title}</strong>
            <small>
              {item.kind} · {new Date(item.touched_at).toLocaleDateString()}
            </small>
          </span>
        </Link>
      ))}
    </div>
  ) : (
    <p className="activity-empty">{emptyMessage}</p>
  );
}

export function ActivityLibrary() {
  const [library, setLibrary] = useState<ClientLibrary>(empty);
  useEffect(() => {
    const load = () => setLibrary(readClientLibrary());
    const timer = window.setTimeout(load, 0);
    window.addEventListener("aperture-library-change", load);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("aperture-library-change", load);
    };
  }, []);
  return (
    <>
      <section className="activity-grid">
        <article>
          <h2>Continue watching</h2>
          {library.progress.length ? (
            <div className="activity-progress-list">
              {library.progress.map((item) => (
                <div key={item.source_id}>
                  <strong>{item.title}</strong>
                  {item.subtitle ? <span>{item.subtitle}</span> : null}
                  <progress max="100" value={item.percentage} />
                  <small>{Math.round(item.percentage)}% watched</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="activity-empty">
              Playback progress will appear after you start watching.
            </p>
          )}
        </article>
        <article>
          <h2>Saved</h2>
          <TitleList
            items={library.saved}
            emptyMessage="Save a title to keep it on this device."
          />
        </article>
        <article>
          <h2>Liked</h2>
          <TitleList
            items={library.liked}
            emptyMessage="Titles you like will appear here."
          />
        </article>
        <article>
          <h2>Recently viewed</h2>
          <TitleList
            items={library.viewed.slice(0, 20)}
            emptyMessage="Open a movie or series to begin your history."
          />
        </article>
        <article>
          <h2>Recent searches</h2>
          {library.searches.length ? (
            <div className="activity-searches">
              {library.searches.map((item) => (
                <Link href={`/search?q=${encodeURIComponent(item)}`} key={item}>
                  {item}
                </Link>
              ))}
            </div>
          ) : (
            <p className="activity-empty">
              Your recent searches will appear here.
            </p>
          )}
        </article>
      </section>
      <button
        className="activity-clear"
        type="button"
        onClick={() => {
          clearClientLibrary();
          setLibrary(empty);
        }}
      >
        Clear device activity
      </button>
    </>
  );
}
