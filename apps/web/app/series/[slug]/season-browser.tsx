"use client";

import { useState } from "react";
import { ResponsiveStill } from "@/app/components/responsive-still";
import type { Season } from "@/app/lib/catalog";

function runtimeLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder}m` : `${minutes}m`;
}

export function SeasonBrowser({ seasons }: { seasons: Season[] }) {
  const [seasonId, setSeasonId] = useState(seasons[0]?.id ?? "");
  const season = seasons.find((item) => item.id === seasonId) ?? seasons[0];
  if (!season)
    return (
      <div className="catalog-state compact">
        <h3>No seasons are published.</h3>
        <p>This series is still being prepared.</p>
      </div>
    );
  return (
    <>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Episodes</p>
          <h2>{season.title ?? `Season ${season.number}`}</h2>
        </div>
        <label>
          Season{" "}
          <select
            aria-label="Choose season"
            value={season.id}
            onChange={(event) => setSeasonId(event.target.value)}
          >
            {seasons.map((item) => (
              <option value={item.id} key={item.id}>
                Season {item.number}
              </option>
            ))}
          </select>
        </label>
      </div>
      {season.episodes.length ? (
        <ol className="episode-list">
          {season.episodes.map((episode) => (
            <li key={episode.id}>
              <div className="episode-number">
                {episode.number.toString().padStart(2, "0")}
              </div>
              <div className="episode-still" aria-hidden="true">
                {episode.still_url ? (
                  <ResponsiveStill
                    src={episode.still_url}
                    sizes="(max-width: 700px) 100vw, 240px"
                  />
                ) : (
                  <span>{episode.number}</span>
                )}
              </div>
              <div>
                <div className="episode-title-row">
                  <h3>{episode.title}</h3>
                  <strong>{runtimeLabel(episode.runtime_minutes)}</strong>
                </div>
                <p>{episode.synopsis}</p>
                <span>
                  {episode.release_date
                    ? new Date(episode.release_date).toLocaleDateString(
                        "en-CA",
                        {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                          timeZone: "UTC",
                        },
                      )
                    : "Air date unavailable"}{" "}
                  · Not started
                </span>
              </div>
              <button
                type="button"
                disabled
                title="No licensed video asset attached"
              >
                Play soon
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <div className="catalog-state compact">
          <h3>No episodes are published.</h3>
          <p>This season is still being prepared.</p>
        </div>
      )}
    </>
  );
}
