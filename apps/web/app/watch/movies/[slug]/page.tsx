import Link from "next/link";
import { isPlaybackUnavailable, playbackFetch } from "@/app/lib/playback";
import { AdaptivePlayer } from "@/app/watch/components/adaptive-player";

export default async function WatchMoviePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const config = await playbackFetch(`/playback/movies/${encodeURIComponent(slug)}`);
  if (!config) return <main className="catalog-state full-state"><p className="eyebrow">Playback unavailable</p><h1>This film is not ready to stream.</h1><p>The catalog remains available while media preparation finishes.</p><Link className="action-link" href={`/movies/${slug}`}>Return to film</Link></main>;
  if (isPlaybackUnavailable(config)) return <main className="catalog-state full-state"><p className="eyebrow">Playback unavailable</p><h1>{config.error === "stream_limit" ? "Your account is already streaming." : "Playback cannot start right now."}</h1><p>{config.message} Stop playback on another device and try again. Inactive device slots expire automatically.</p><Link className="action-link" href={`/movies/${slug}`}>Return to film</Link></main>;
  return <AdaptivePlayer config={config} />;
}
