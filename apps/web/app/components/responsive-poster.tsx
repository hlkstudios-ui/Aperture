import { optimizedPoster } from "@/app/lib/images";

export function ResponsivePoster({
  src,
  sizes,
  alt = "",
  loading = "lazy",
  fetchPriority,
}: {
  src: string;
  sizes: string;
  alt?: string;
  loading?: "eager" | "lazy";
  fetchPriority?: "high" | "low" | "auto";
}) {
  const small = optimizedPoster(src, 185) ?? src;
  const medium = optimizedPoster(src, 342) ?? src;
  const large = optimizedPoster(src, 500) ?? src;
  const responsive = new Set([small, medium, large]).size > 1;

  return (
    // The upstream TMDB CDN performs the resize; using next/image would proxy it through the VPS.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={medium}
      srcSet={
        responsive ? `${small} 185w, ${medium} 342w, ${large} 500w` : undefined
      }
      sizes={responsive ? sizes : undefined}
      alt={alt}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding="async"
      width="342"
      height="513"
    />
  );
}
