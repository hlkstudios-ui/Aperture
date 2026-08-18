import { optimizedBackdrop } from "@/app/lib/images";

export function ResponsiveBackdrop({
  src,
  className,
  sizes = "100vw",
}: {
  src: string;
  className?: string;
  sizes?: string;
}) {
  const medium = optimizedBackdrop(src, 780) ?? src;
  const large = optimizedBackdrop(src, 1280) ?? src;
  const responsive = medium !== large;
  return (
    // TMDB performs the resize at its edge; proxying through next/image would burden the VPS.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className={className}
      src={large}
      srcSet={responsive ? `${medium} 780w, ${large} 1280w` : undefined}
      sizes={responsive ? sizes : undefined}
      alt=""
      aria-hidden="true"
      decoding="async"
      fetchPriority="high"
      width="1280"
      height="720"
    />
  );
}
