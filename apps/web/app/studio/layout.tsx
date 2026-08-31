import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noarchive: true,
      noimageindex: true,
      nosnippet: true,
    },
  },
};

export default function StudioLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div data-hide-public-footer>{children}</div>;
}
