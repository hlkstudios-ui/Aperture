import Link from "next/link";
import { isPlaybackUnavailable, playbackFetch } from "@/app/lib/playback";
import { AdaptivePlayer } from "@/app/watch/components/adaptive-player";

export default async function WatchEpisodePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const config = await playbackFetch(`/playback/episodes/${encodeURIComponent(id)}`);
  if (!config) return <main className="catalog-state full-state"><h1>This episode is not ready.</h1><Link className="action-link" href="/series">Return to series</Link></main>;
  if (isPlaybackUnavailable(config)) return <main className="catalog-state full-state"><p className="eyebrow">Playback unavailable</p><h1>{config.error === "stream_limit" ? "Your account is already streaming." : "Playback cannot start right now."}</h1><p>{config.message} Stop playback on another device and try again. Inactive device slots expire automatically.</p><Link className="action-link" href="/series">Return to series</Link></main>;
  return <AdaptivePlayer config={config} />;
}
