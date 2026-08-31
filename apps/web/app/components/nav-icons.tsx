import type { SVGProps } from "react";

export type NavIconName =
  | "account"
  | "activity"
  | "bookmark"
  | "browse"
  | "chevron"
  | "close"
  | "film"
  | "game"
  | "home"
  | "menu"
  | "passport"
  | "search"
  | "series";

export function NavIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: NavIconName }) {
  const common = {
    "aria-hidden": true,
    fill: "none",
    viewBox: "0 0 24 24",
    xmlns: "http://www.w3.org/2000/svg",
    ...props,
  };

  if (name === "home") return <svg {...common}><path d="m3.5 10.5 8.5-7 8.5 7v9a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
  if (name === "browse") return <svg {...common}><circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" /><path d="m15.7 8.3-2.1 5.3-5.3 2.1 2.1-5.3z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><circle cx="12" cy="12" fill="currentColor" r="1" /></svg>;
  if (name === "film") return <svg {...common}><rect height="15" rx="2" stroke="currentColor" strokeWidth="1.7" width="18" x="3" y="4.5" /><path d="M7 4.5v15m10-15v15M3 9h4m10 0h4M3 15h4m10 0h4" stroke="currentColor" strokeWidth="1.7" /></svg>;
  if (name === "series") return <svg {...common}><rect height="13" rx="2" stroke="currentColor" strokeWidth="1.7" width="18" x="3" y="7" /><path d="m8 3.5 4 3.5 4-3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /><path d="M7 11h7m-7 4h7m3-4v4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></svg>;
  if (name === "search") return <svg {...common}><circle cx="10.7" cy="10.7" r="6.7" stroke="currentColor" strokeWidth="1.8" /><path d="m15.6 15.6 4.4 4.4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /></svg>;
  if (name === "bookmark") return <svg {...common}><path d="M6.5 4.5a1.5 1.5 0 0 1 1.5-1.5h8a1.5 1.5 0 0 1 1.5 1.5V21L12 17.4 6.5 21z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
  if (name === "account") return <svg {...common}><circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.7" /><path d="M5.5 20c.5-4 2.7-6 6.5-6s6 2 6.5 6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></svg>;
  if (name === "activity") return <svg {...common}><path d="M4 12h3l2-5 4 10 2-5h5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
  if (name === "passport") return <svg {...common}><rect height="18" rx="2" stroke="currentColor" strokeWidth="1.7" width="14" x="5" y="3" /><circle cx="12" cy="11" r="3.2" stroke="currentColor" strokeWidth="1.5" /><path d="M8.8 11h6.4M12 7.8c1 1 1.4 2 1.4 3.2S13 13.2 12 14.2c-1-1-1.4-2-1.4-3.2S11 8.8 12 7.8Z" stroke="currentColor" strokeWidth="1.2" /></svg>;
  if (name === "game") return <svg {...common}><path d="M7.5 8h9a4.5 4.5 0 0 1 4.2 6.1l-1.3 3.4a2 2 0 0 1-3.3.7L14.5 17h-5l-1.6 1.2a2 2 0 0 1-3.3-.7l-1.3-3.4A4.5 4.5 0 0 1 7.5 8Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M8 11v4m-2-2h4m6.5-.5h.01m2 2h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></svg>;
  if (name === "menu") return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /></svg>;
  if (name === "close") return <svg {...common}><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /></svg>;
  if (name === "chevron") return <svg {...common}><path d="m7 9 5 5 5-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
  return null;
}
