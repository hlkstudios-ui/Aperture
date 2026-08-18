"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { optimizedBackdrop } from "@/app/lib/images";

function runtimeLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder}m` : `${minutes}m`;
}

export type HeroSlide = {
  id: string;
  kind: "movie" | "series";
  title: string;
  slug: string;
  short_description: string;
  maturity_rating: string | null;
  runtime_minutes: number | null;
  backdrop_url: string | null;
  metadata_provider: string | null;
  release_date: string | null;
  original_title: string | null;
  country_code: string | null;
  genres: Array<{ name: string }>;
};

export function HeroSlideshow({ slides }: { slides: HeroSlide[] }) {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const slide = slides[active];

  useEffect(() => {
    const connection = (
      navigator as Navigator & {
        connection?: { saveData?: boolean; effectiveType?: string };
      }
    ).connection;
    const constrained =
      connection?.saveData ||
      connection?.effectiveType === "slow-2g" ||
      connection?.effectiveType === "2g";
    if (
      paused ||
      constrained ||
      slides.length < 2 ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const timer = window.setInterval(
      () => setActive((current) => (current + 1) % slides.length),
      7000,
    );
    return () => window.clearInterval(timer);
  }, [paused, slides.length]);

  if (!slide) return null;

  return (
    <section
      className="hero catalog-hero hero-slideshow"
      aria-roledescription="carousel"
      aria-label="Latest movies and ongoing series"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      {slide.backdrop_url ? (
        // TMDB serves these variants directly; proxying them through next/image burdens the VPS.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="hero-backdrop active"
          src={slide.backdrop_url}
          srcSet={`${optimizedBackdrop(slide.backdrop_url, 780)} 780w, ${optimizedBackdrop(slide.backdrop_url, 1280)} 1280w`}
          sizes="100vw"
          alt=""
          aria-hidden="true"
          decoding="async"
          fetchPriority="high"
          width="1280"
          height="720"
          key={`backdrop:${slide.kind}:${slide.id}`}
        />
      ) : null}
      <div className="hero-slide-shade" aria-hidden="true" />
      {slides.length > 1 ? (
        <button
          className="hero-arrow hero-arrow-left"
          type="button"
          aria-label="Previous slide"
          onClick={() =>
            setActive((active - 1 + slides.length) % slides.length)
          }
        >
          ‹
        </button>
      ) : null}
      <div className="hero-slide-copy" key={`copy:${slide.kind}:${slide.id}`}>
        <div className="eyebrow">
          {slide.kind === "movie" ? "Latest movie" : "Ongoing series"}
        </div>
        <h1>{slide.title}</h1>
        {slide.original_title ? (
          <p className="hero-original-title">
            Original title · {slide.original_title}
          </p>
        ) : null}
        <p>{slide.short_description}</p>
        <div className="hero-meta" aria-label="Title details">
          {slide.release_date ? (
            <span>{new Date(slide.release_date).getUTCFullYear()}</span>
          ) : null}
          <span>{slide.maturity_rating ?? "Not rated"}</span>
          {slide.runtime_minutes ? (
            <span>{runtimeLabel(slide.runtime_minutes)}</span>
          ) : null}
          {slide.country_code ? <span>{slide.country_code}</span> : null}
          {slide.genres.slice(0, 3).map((genre) => (
            <span key={genre.name}>{genre.name}</span>
          ))}
        </div>
        <div className="hero-actions">
          <Link
            className="primary action-link"
            href={`/${slide.kind === "movie" ? "movies" : "series"}/${slide.slug}`}
          >
            View {slide.kind === "movie" ? "film" : "series"}
          </Link>
          <Link className="secondary action-link" href="/search">
            Explore the catalog
          </Link>
        </div>
      </div>
      {slides.length > 1 ? (
        <button
          className="hero-arrow hero-arrow-right"
          type="button"
          aria-label="Next slide"
          onClick={() => setActive((active + 1) % slides.length)}
        >
          ›
        </button>
      ) : null}
      {slides.length > 1 ? (
        <div className="hero-carousel-controls">
          <span className="hero-slide-count">
            {String(active + 1).padStart(2, "0")} /{" "}
            {String(slides.length).padStart(2, "0")}
          </span>
          <div
            className="hero-carousel-dots"
            role="group"
            aria-label="Choose slide"
          >
            {slides.map((item, index) => (
              <button
                type="button"
                className={index === active ? "active" : ""}
                aria-label={`Show slide ${index + 1}: ${item.title}`}
                aria-current={index === active ? "true" : undefined}
                onClick={() => setActive(index)}
                key={`dot:${item.kind}:${item.id}:${index}`}
              />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
