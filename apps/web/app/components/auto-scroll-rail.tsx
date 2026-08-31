"use client";

import { useEffect, useRef } from "react";

import { HomepageTitleCard } from "@/app/components/homepage-title-card";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import type { HomepageTitle } from "@/app/lib/homepage";

function DecorativeCard({ title, position }: { title: HomepageTitle; position: number }) {
  return <span className="content-card auto-scroll-clone">
    <span className="card-art" aria-hidden="true">{title.poster_url ? <ResponsivePoster src={title.poster_url} sizes="(max-width: 700px) 170px, 240px" /> : title.title[0]}<i className="marathon-order">{String(position).padStart(2, "0")}</i></span>
    <span className="card-copy"><strong>{title.title}</strong><small>{title.kind === "movie" ? "Film" : "Series"}</small></span>
  </span>;
}

export function AutoScrollRail({ label, titles, reverse = false }: { label: string; titles: HomepageTitle[]; reverse?: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const firstSetRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const resumeTimerRef = useRef<number | null>(null);
  const dragRef = useRef({ pointerId: -1, startX: 0, startScroll: 0, moved: false });
  const suppressClickUntilRef = useRef(0);

  useEffect(() => {
    const viewport = viewportRef.current;
    const firstSet = firstSetRef.current;
    if (!viewport || !firstSet || titles.length < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    let lastTime = performance.now();
    let visible = true;
    const width = () => firstSet.getBoundingClientRect().width;
    if (reverse) viewport.scrollLeft = width();
    const animate = (time: number) => {
      const delta = Math.min(50, time - lastTime);
      lastTime = time;
      const loopWidth = width();
      if (visible && !pausedRef.current && loopWidth > viewport.clientWidth) {
        viewport.scrollLeft += (reverse ? -1 : 1) * delta * 0.026;
        if (!reverse && viewport.scrollLeft >= loopWidth) viewport.scrollLeft -= loopWidth;
        if (reverse && viewport.scrollLeft <= 0) viewport.scrollLeft += loopWidth;
      }
      frame = window.requestAnimationFrame(animate);
    };
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { rootMargin: "160px" });
    observer.observe(viewport);
    frame = window.requestAnimationFrame(animate);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
      if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
    };
  }, [reverse, titles.length]);

  const pause = () => {
    pausedRef.current = true;
    if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
  };
  const resume = (delay = 0) => {
    if (resumeTimerRef.current !== null) window.clearTimeout(resumeTimerRef.current);
    resumeTimerRef.current = window.setTimeout(() => { pausedRef.current = false; }, delay);
  };
  const beginDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    pause();
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startScroll: event.currentTarget.scrollLeft, moved: false };
  };
  const moveDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (drag.pointerId !== event.pointerId || event.pointerType !== "mouse") return;
    const distance = event.clientX - drag.startX;
    if (Math.abs(distance) > 5 && !drag.moved) {
      drag.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      event.currentTarget.dataset.dragging = "true";
    }
    if (drag.moved) {
      event.preventDefault();
      event.currentTarget.scrollLeft = drag.startScroll - distance;
    }
  };
  const finishDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragRef.current.pointerId !== event.pointerId) return;
    if (dragRef.current.moved) suppressClickUntilRef.current = performance.now() + 350;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    delete event.currentTarget.dataset.dragging;
    dragRef.current.pointerId = -1;
    dragRef.current.moved = false;
    resume(2400);
  };
  const nudge = (direction: -1 | 1) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    pause();
    viewport.scrollBy({ left: direction * Math.min(viewport.clientWidth * 0.82, 760), behavior: "smooth" });
    resume(2600);
  };
  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    pause();
    if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
      event.preventDefault();
      event.currentTarget.scrollLeft += event.deltaY;
    }
    resume(2400);
  };

  return <div className="auto-scroll-frame" onMouseEnter={pause} onMouseLeave={() => { if (dragRef.current.pointerId < 0) resume(); }}>
    <div className="card-rail auto-scroll-rail" ref={viewportRef} aria-label={`${label}. Automatically scrolling. Use Previous and Next, the mouse wheel, or click and drag to browse.`} onFocusCapture={pause} onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) resume(); }} onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onClickCapture={(event) => { if (performance.now() < suppressClickUntilRef.current) { event.preventDefault(); event.stopPropagation(); } }} onWheel={handleWheel}>
      <div className="auto-scroll-set" ref={firstSetRef}>{titles.map((title, index) => <HomepageTitleCard title={title} position={index + 1} key={`${title.kind}:${title.id}`} />)}</div>
      <div className="auto-scroll-set" aria-hidden="true">{titles.map((title, index) => <DecorativeCard title={title} position={index + 1} key={`echo:${title.kind}:${title.id}`} />)}</div>
    </div>
    <div className="auto-scroll-controls" aria-label={`${label} carousel controls`}>
      <button type="button" onClick={() => nudge(-1)} aria-label={`Previous titles in ${label}`}><span aria-hidden="true">←</span></button>
      <button type="button" onClick={() => nudge(1)} aria-label={`Next titles in ${label}`}><span aria-hidden="true">→</span></button>
    </div>
  </div>;
}
