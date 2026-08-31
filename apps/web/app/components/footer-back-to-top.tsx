"use client";

import { useEffect, useRef, type MouseEvent } from "react";

export function FooterBackToTop() {
  const linkRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const footer = linkRef.current?.closest<HTMLElement>(".closing-iris");
    const threshold = footer?.querySelector<HTMLElement>(".closing-iris__threshold");
    const stage = footer?.querySelector<HTMLElement>(".closing-iris__stage");
    const signature = footer?.querySelector<HTMLElement>(".closing-iris__signature");
    const ledger = footer?.querySelector<HTMLElement>(".closing-iris__ledger");
    if (!footer || !threshold || !stage || !signature || !ledger) return;

    const root = document.documentElement;
    const revealTargets = new Map<Element, string>([
      [threshold, "closing-iris--threshold-entered"],
      [stage, "closing-iris--stage-entered"],
      [signature, "closing-iris--signature-entered"],
    ]);
    const dockTargets = new Set<Element>([stage, signature, ledger]);
    const visibleDockTargets = new Set<Element>();
    const isInView = (element: Element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.bottom > 0 && bounds.top < window.innerHeight;
    };

    for (const [element, className] of revealTargets) {
      if (isInView(element)) footer.classList.add(className);
    }
    for (const element of dockTargets) {
      if (isInView(element)) visibleDockTargets.add(element);
    }
    root.classList.toggle("aperture-footer-open", visibleDockTargets.size > 0);
    footer.classList.add("closing-iris--motion-ready");

    if (!("IntersectionObserver" in window)) {
      for (const className of revealTargets.values()) footer.classList.add(className);
      return () => {
        root.classList.remove("aperture-footer-open");
        footer.classList.remove("closing-iris--motion-ready", ...revealTargets.values());
      };
    }

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (dockTargets.has(entry.target)) {
          if (entry.isIntersecting) visibleDockTargets.add(entry.target);
          else visibleDockTargets.delete(entry.target);
        }
        const className = revealTargets.get(entry.target);
        if (entry.isIntersecting && className) footer.classList.add(className);
      }
      root.classList.toggle("aperture-footer-open", visibleDockTargets.size > 0);
    }, { threshold: 0.01 });

    for (const element of revealTargets.keys()) observer.observe(element);
    observer.observe(ledger);

    return () => {
      observer.disconnect();
      root.classList.remove("aperture-footer-open");
      footer.classList.remove("closing-iris--motion-ready", ...revealTargets.values());
    };
  }, []);

  function returnToMain(event: MouseEvent<HTMLAnchorElement>) {
    const main = document.getElementById("main-content");
    if (!main) return;

    event.preventDefault();
    main.focus({ preventScroll: true });
    main.scrollIntoView({ block: "start", behavior: "auto" });
    window.history.replaceState(null, "", "#main-content");
  }

  return (
    <a className="closing-iris__top" href="#main-content" onClick={returnToMain} ref={linkRef}>
      <span>Back to top</span>
      <svg aria-hidden="true" viewBox="0 0 20 20">
        <path d="M10 16V4m0 0L5.5 8.5M10 4l4.5 4.5" />
      </svg>
    </a>
  );
}
