import { optimizedStill } from "@/app/lib/images";

export function ResponsiveStill({
  src,
  sizes,
}: {
  src: string;
  sizes: string;
}) {
  const small = optimizedStill(src, 300) ?? src;
  const large = optimizedStill(src, 500) ?? src;
  const responsive = small !== large;
  return (
    // TMDB performs the resize at its edge; proxying through next/image would burden the VPS.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={small}
      srcSet={responsive ? `${small} 300w, ${large} 500w` : undefined}
      sizes={responsive ? sizes : undefined}
      alt=""
      loading="lazy"
      decoding="async"
      width="500"
      height="281"
    />
  );
}
