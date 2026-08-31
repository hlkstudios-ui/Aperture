"use client";

import type { CSSProperties, KeyboardEvent, PointerEvent, WheelEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { CatalogCard } from "@/app/components/catalog-card";
import type { BrowseItem, BrowseSection } from "@/app/browse/browse-types";

function releaseYear(date: string | null) {
  return date?.slice(0, 4) || "Coming soon";
}

function runtimeLabel(minutes: number | null) {
  if (!minutes) return null;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder}m` : `${minutes}m`;
}

function primaryFacts(item: BrowseItem) {
  const rating = item.vote_average && item.vote_average > 0
    ? `★ ${item.vote_average.toFixed(1)}`
    : null;
  return [releaseYear(item.release_date), rating].filter(Boolean).join(" · ");
}

function secondaryFacts(item: BrowseItem) {
  const facts = item.kind === "movie"
    ? [runtimeLabel(item.duration_minutes), item.maturity_rating]
    : [
      item.season_count ? `${item.season_count} ${item.season_count === 1 ? "season" : "seasons"}` : null,
      item.is_ongoing === true ? "Ongoing" : item.maturity_rating,
    ];
  return facts.filter(Boolean).join(" · ");
}

export function BrowseSpecialistRail({ section, index }: { section: BrowseSection; index: number }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const userPausedRef = useRef(false);
  const [userPaused, setUserPaused] = useState(false);
  const visibleRef = useRef(false);
  const directionRef = useRef(index % 3 === 1 ? -1 : 1);
  const frameRef = useRef(0);
  const lastTimeRef = useRef(0);
  const resumeTimerRef = useRef<number | null>(null);
  const suppressClickUntilRef = useRef(0);
  const dragRef = useRef({ pointerId: -1, startX: 0, startScroll: 0, moved: false });

  const prewarmPosters = () => {
    const viewport = viewportRef.current;
    if (!viewport || viewport.dataset.postersWarmed === "true") return;
    viewport.querySelectorAll<HTMLImageElement>('img[loading="lazy"]').forEach((image) => {
      // Native lazy loading only watches the page viewport reliably. These cards
      // move inside a horizontal scroller, so fetch the rail once it approaches.
      image.loading = "eager";
    });
    viewport.dataset.postersWarmed = "true";
  };

  const stopAnimation = () => {
    if (viewportRef.current) delete viewportRef.current.dataset.autoMoving;
    if (!frameRef.current) return;
    window.cancelAnimationFrame(frameRef.current);
    frameRef.current = 0;
  };

  const startAnimation = () => {
    if (frameRef.current || pausedRef.current || !visibleRef.current) return;
    const viewport = viewportRef.current;
    if (!viewport || viewport.scrollWidth <= viewport.clientWidth) return;
    viewport.dataset.autoMoving = "true";
    lastTimeRef.current = performance.now();
    const animate = (time: number) => {
      const current = viewportRef.current;
      if (!current || pausedRef.current || !visibleRef.current) {
        frameRef.current = 0;
        return;
      }
      const delta = Math.min(50, time - lastTimeRef.current);
      lastTimeRef.current = time;
      const maximum = Math.max(0, current.scrollWidth - current.clientWidth);
      const next = current.scrollLeft + directionRef.current * delta * 0.022;
      if (next >= maximum) {
        current.scrollLeft = maximum;
        directionRef.current = -1;
      } else if (next <= 0) {
        current.scrollLeft = 0;
        directionRef.current = 1;
      } else {
        current.scrollLeft = next;
      }
      frameRef.current = window.requestAnimationFrame(animate);
    };
    frameRef.current = window.requestAnimationFrame(animate);
  };

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || section.items.length < 2) return;
    if (typeof IntersectionObserver === "undefined") {
      prewarmPosters();
      return;
    }
    const automaticMotionAllowed = typeof window.matchMedia !== "function"
      || (!window.matchMedia("(prefers-reduced-motion: reduce)").matches && !window.matchMedia("(pointer: coarse)").matches);
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) prewarmPosters();
      visibleRef.current = automaticMotionAllowed && entry.isIntersecting;
      if (visibleRef.current) startAnimation();
      else stopAnimation();
    }, { rootMargin: "180px 0px" });
    observer.observe(viewport);
    return () => {
      observer.disconnect();
      visibleRef.current = false;
      stopAnimation();
      if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
    };
  }, [section.id, section.items.length]);

  const pause = () => {
    pausedRef.current = true;
    stopAnimation();
    if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
  };

  const resume = (delay = 0) => {
    if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
    resumeTimerRef.current = window.setTimeout(() => {
      if (userPausedRef.current) return;
      pausedRef.current = false;
      startAnimation();
    }, delay);
  };

  const nudge = (direction: -1 | 1) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    prewarmPosters();
    pause();
    viewport.scrollBy({ left: direction * Math.min(viewport.clientWidth * 0.82, 840), behavior: "smooth" });
    resume(2600);
  };

  const beginDrag = (event: PointerEvent<HTMLDivElement>) => {
    prewarmPosters();
    pause();
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startScroll: event.currentTarget.scrollLeft, moved: false };
  };

  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (drag.pointerId !== event.pointerId) return;
    const distance = event.clientX - drag.startX;
    if (Math.abs(distance) > 5 && !drag.moved) {
      drag.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      event.currentTarget.dataset.dragging = "true";
    }
    if (!drag.moved) return;
    event.preventDefault();
    event.currentTarget.scrollLeft = drag.startScroll - distance;
  };

  const finishDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "mouse") {
      resume(2400);
      return;
    }
    if (dragRef.current.pointerId !== event.pointerId) return;
    if (dragRef.current.moved) suppressClickUntilRef.current = performance.now() + 350;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    delete event.currentTarget.dataset.dragging;
    dragRef.current.pointerId = -1;
    dragRef.current.moved = false;
    resume(2400);
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!event.shiftKey && Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
    pause();
    event.preventDefault();
    event.currentTarget.scrollLeft += event.deltaX || event.deltaY;
    resume(2200);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      nudge(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      nudge(1);
    }
  };

  const toggleMotion = () => {
    const next = !userPausedRef.current;
    userPausedRef.current = next;
    setUserPaused(next);
    if (next) {
      pausedRef.current = true;
      stopAnimation();
    } else {
      pausedRef.current = false;
      startAnimation();
    }
  };

  return <section
    className="browse-specialist-rail"
    aria-labelledby={`browse-section-${section.id}`}
    style={{ "--browse-section-index": String(Math.min(index, 7)) } as CSSProperties}
  >
    <header className="browse-specialist-rail__heading">
      <div>
        <p className="browse-experience__eyebrow">{section.eyebrow}</p>
        <h2 id={`browse-section-${section.id}`}>{section.title}</h2>
        <p>{section.description}</p>
      </div>
      <div className="browse-specialist-rail__controls" role="group" aria-label={`${section.title} carousel controls`}>
        <span>{String(index + 1).padStart(2, "0")}</span>
        <button className="browse-specialist-rail__motion-toggle" type="button" onClick={toggleMotion} aria-label={`${userPaused ? "Resume" : "Pause"} automatic movement in ${section.title}`}>{userPaused ? "▶" : "Ⅱ"}</button>
        <button type="button" onClick={() => nudge(-1)} aria-label={`Previous titles in ${section.title}`}>←</button>
        <button type="button" onClick={() => nudge(1)} aria-label={`Next titles in ${section.title}`}>→</button>
      </div>
    </header>
    {section.items.length ? <div
      className="browse-specialist-rail__viewport"
      ref={viewportRef}
      role="region"
      aria-label={`${section.title}. ${section.items.length} titles. Use arrow keys, controls, touch, or mouse drag to browse.`}
      tabIndex={0}
      onMouseEnter={pause}
      onMouseLeave={() => { if (dragRef.current.pointerId < 0) resume(); }}
      onFocusCapture={pause}
      onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) resume(); }}
      onPointerDown={beginDrag}
      onPointerMove={moveDrag}
      onPointerUp={finishDrag}
      onPointerCancel={finishDrag}
      onClickCapture={(event) => {
        if (performance.now() < suppressClickUntilRef.current) {
          event.preventDefault();
          event.stopPropagation();
        }
      }}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
    >
      {section.items.map((item) => <CatalogCard density="detailed" item={{
        href: item.href || `/titles/${item.kind}/${encodeURIComponent(item.id)}`,
        title: item.title,
        kind: item.kind,
        posterUrl: item.poster_url,
        description: item.short_description,
        primaryMeta: primaryFacts(item),
        secondaryMeta: secondaryFacts(item),
        genres: item.genres,
      }} key={`${section.id}:${item.kind}:${item.id}`}/>) }
    </div> : <div className="browse-specialist-rail__unavailable" role="status">
      <strong>This collection is between screenings.</strong>
      <span>This shelf could not load yet. The next collection is ready below.</span>
    </div>}
  </section>;
}
