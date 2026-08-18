"use client";

import Hls, { Events, ErrorTypes } from "hls.js";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { PlaybackConfig } from "@/app/lib/playback";
import { trackAnalytics } from "@/app/lib/analytics-client";
import { featureFlags } from "@/app/lib/feature-flags";
import { SceneLens } from "./scene-lens";
import { AfterCreditsRoom } from "./after-credits-room";
import { clientProgress, saveClientProgress } from "@/app/lib/client-state";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
function clock(value: number) {
  if (!Number.isFinite(value)) return "0:00";
  const minutes = Math.floor(value / 60);
  return `${minutes}:${Math.floor(value % 60).toString().padStart(2, "0")}`;
}
const languageAliases: Record<string, string> = { eng: "en", fra: "fr", fre: "fr", spa: "es", ara: "ar", jpn: "ja" };
function languageMatches(track: string | undefined, preferred: string | null) {
  if (!track || !preferred) return false;
  const normalize = (value: string) => languageAliases[value.toLowerCase()] ?? value.toLowerCase().split("-")[0];
  return normalize(track) === normalize(preferred);
}

export function AdaptivePlayer({ config }: { config: PlaybackConfig }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const lastSaved = useRef(0);
  const lastAnalyticsPosition = useRef(config.progress?.position_seconds ?? 0);
  const playStartSent = useRef(false);
  const mountedAt = useRef(0);
  const startupSent = useRef(false);
  const bufferStartedAt = useRef<number | null>(null);
  const playbackErrorSent = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(config.progress?.position_seconds ?? 0);
  const [duration, setDuration] = useState(config.duration_seconds);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [quality, setQuality] = useState(-1);
  const [levels, setLevels] = useState<Array<{ index: number; height: number }>>([]);
  const [audioTracks, setAudioTracks] = useState<Array<{ index: number; name: string; lang?: string }>>([]);
  const [audioTrack, setAudioTrack] = useState(0);
  const preferredSubtitleIndex = config.subtitles_enabled
    ? config.subtitle_tracks.findIndex(
        (track) => languageMatches(track.language, config.preferred_subtitle_language),
      )
    : -1;
  const preferredSecondarySubtitleIndex = config.subtitles_enabled
    ? config.subtitle_tracks.findIndex(
        (track, index) => index !== preferredSubtitleIndex && languageMatches(track.language, config.preferred_secondary_subtitle_language),
      )
    : -1;
  const [subtitleTrack, setSubtitleTrack] = useState(preferredSubtitleIndex);
  const [secondarySubtitleTrack, setSecondarySubtitleTrack] = useState(preferredSecondarySubtitleIndex);
  const [status, setStatus] = useState<"loading" | "ready" | "buffering" | "error">("loading");
  const [error, setError] = useState("");
  const [progressState, setProgressState] = useState<"idle" | "saving" | "saved">("idle");
  const [lensOpen, setLensOpen] = useState(false);
  const [lensReady, setLensReady] = useState(false);
  const [afterCreditsOpen, setAfterCreditsOpen] = useState(false);

  useEffect(() => {
    mountedAt.current = performance.now();
  }, []);

  const openLens = useCallback(() => {
    if (!featureFlags.sceneLens) return;
    setLensOpen(true); setLensReady(false);
    void trackAnalytics({ event_type: "scenelens_open", movie_id: config.movie_id, episode_id: config.episode_id, position_seconds: videoRef.current?.currentTime ?? time, duration_seconds: duration });
  }, [config.episode_id, config.movie_id, duration, time]);

  const saveProgress = useCallback(async (force = false) => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(video.duration) || video.duration <= 0) return;
    const distanceFromLastSave = Math.abs(video.currentTime - lastSaved.current);
    if ((!force && distanceFromLastSave < 10) || (force && distanceFromLastSave < 0.25)) return;
    lastSaved.current = video.currentTime;
    saveClientProgress({ source_id: config.source_id, title: config.title, subtitle: config.subtitle, position_seconds: video.currentTime, duration_seconds: video.duration });
    setProgressState("saving");
    const watched = Math.max(0, Math.min(30, video.currentTime - lastAnalyticsPosition.current));
    try {
      const response = await fetch(`${apiOrigin}/playback/sources/${config.source_id}/progress`, {
        method: "PUT", credentials: "include",
        keepalive: force,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_seconds: video.currentTime, duration_seconds: video.duration, watched_seconds_delta: watched }),
      });
      setProgressState(response.ok ? "saved" : "idle");
      if (response.ok) {
        lastAnalyticsPosition.current = video.currentTime;
        void trackAnalytics({
          event_type: "progress", movie_id: config.movie_id, episode_id: config.episode_id,
          position_seconds: video.currentTime, duration_seconds: video.duration, value: watched,
          properties: { quality_height: video.videoHeight || null },
        });
      }
    } catch {
      setProgressState("idle");
    }
  }, [config.episode_id, config.movie_id, config.source_id, config.subtitle, config.title]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const mediaUsesApiSession = new URL(config.manifest_url, window.location.href).origin
      === new URL(apiOrigin, window.location.href).origin;
    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        xhrSetup: (xhr) => { xhr.withCredentials = mediaUsesApiSession; },
      });
      hlsRef.current = hls;
      hls.attachMedia(video);
      hls.on(Events.MEDIA_ATTACHED, () => hls.loadSource(config.manifest_url));
      hls.on(Events.MANIFEST_PARSED, (_, data) => {
        setLevels(data.levels.map((level, index) => ({ index, height: level.height })));
        setAudioTracks(hls.audioTracks.map((track, index) => ({ index, name: track.name, lang: track.lang })));
        const preferredAudio = config.preferred_audio_language ?? config.original_language_code;
        const originalTrack = preferredAudio
          ? hls.audioTracks.findIndex((track) => languageMatches(track.lang, preferredAudio))
          : -1;
        if (originalTrack >= 0) { hls.audioTrack = originalTrack; setAudioTrack(originalTrack); }
        const hlsPreferredCaptions = config.subtitles_enabled
          ? hls.subtitleTracks.findIndex((track) => languageMatches(track.lang, config.preferred_subtitle_language))
          : -1;
        hls.subtitleTrack = hlsPreferredCaptions;
        setSubtitleTrack(preferredSubtitleIndex);
        setSecondarySubtitleTrack(preferredSecondarySubtitleIndex);
        setStatus("ready");
      });
      hls.on(Events.ERROR, (_, data) => {
        if (!data.fatal) return;
        setStatus("error"); setError("Playback interrupted. Retry the stream.");
        if (!playbackErrorSent.current) {
          playbackErrorSent.current = true;
          void trackAnalytics({
            event_type: "playback_error", movie_id: config.movie_id, episode_id: config.episode_id,
            position_seconds: video.currentTime, duration_seconds: video.duration || config.duration_seconds,
            properties: { error_code: `${data.type}:${data.details}`, source: "hls.js" },
          });
        }
        if (data.type === ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
      });
      return () => { void saveProgress(true); hls.destroy(); hlsRef.current = null; };
    }
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = config.manifest_url;
      video.crossOrigin = mediaUsesApiSession ? "use-credentials" : "anonymous";
      setStatus("ready");
    } else { setStatus("error"); setError("Adaptive playback is not supported in this browser."); }
  }, [config.duration_seconds, config.episode_id, config.manifest_url, config.movie_id, config.original_language_code, config.preferred_audio_language, config.preferred_subtitle_language, config.subtitles_enabled, preferredSubtitleIndex, preferredSecondarySubtitleIndex, saveProgress]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement)?.matches("input,select,button")) return;
      const video = videoRef.current; if (!video) return;
      if (event.code === "Space") { event.preventDefault(); void (video.paused ? video.play() : video.pause()); }
      if (event.key === "ArrowRight") video.currentTime = Math.min(video.duration, video.currentTime + 10);
      if (event.key === "ArrowLeft") video.currentTime = Math.max(0, video.currentTime - 10);
      if (event.key.toLowerCase() === "m") video.muted = !video.muted;
      if (event.key.toLowerCase() === "f") void shellRef.current?.requestFullscreen();
      if (featureFlags.sceneLens && event.key.toLowerCase() === "l") { event.preventDefault(); setLensOpen((value) => !value); setLensReady(false); }
    };
    window.addEventListener("keydown", onKey);
    const onHide = () => void saveProgress(true);
    window.addEventListener("pagehide", onHide);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("pagehide", onHide); };
  }, [saveProgress]);

  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: config.title,
      album: config.subtitle ?? "Aperture",
    });
    const video = () => videoRef.current;
    navigator.mediaSession.setActionHandler("play", () => void video()?.play());
    navigator.mediaSession.setActionHandler("pause", () => video()?.pause());
    navigator.mediaSession.setActionHandler("seekbackward", (detail) => {
      const target = video();
      if (target) target.currentTime = Math.max(0, target.currentTime - (detail.seekOffset ?? 10));
    });
    navigator.mediaSession.setActionHandler("seekforward", (detail) => {
      const target = video();
      if (target) target.currentTime = Math.min(target.duration, target.currentTime + (detail.seekOffset ?? 10));
    });
    navigator.mediaSession.setActionHandler("seekto", (detail) => {
      const target = video();
      if (target && detail.seekTime !== undefined) target.currentTime = detail.seekTime;
    });
    return () => {
      for (const action of ["play", "pause", "seekbackward", "seekforward", "seekto"] as MediaSessionAction[]) {
        navigator.mediaSession.setActionHandler(action, null);
      }
    };
  }, [config.subtitle, config.title]);

  const marker = config.intro && time >= config.intro[0] && time < config.intro[1] ? { label: "Skip intro", end: config.intro[1] } : config.recap && time >= config.recap[0] && time < config.recap[1] ? { label: "Skip recap", end: config.recap[1] } : config.credits_start_seconds !== null && time >= config.credits_start_seconds ? { label: "Skip credits", end: duration } : null;
  function retry() { setError(""); setStatus("loading"); hlsRef.current?.startLoad(); void videoRef.current?.play(); }
  function chooseQuality(value: number) {
    setQuality(value); if (hlsRef.current) hlsRef.current.currentLevel = value;
    const selected = levels.find((level) => level.index === value);
    const video = videoRef.current;
    if (video && video.duration > 0) void trackAnalytics({
      event_type: "quality_change", movie_id: config.movie_id, episode_id: config.episode_id,
      position_seconds: video.currentTime, duration_seconds: video.duration,
      properties: { quality_height: selected?.height ?? null, action: value < 0 ? "auto" : "manual" },
    });
  }
  function chooseAudio(value: number) { setAudioTrack(value); if (hlsRef.current) hlsRef.current.audioTrack = value; }
  function applySubtitleTracks(primary: number, secondary: number) { Array.from(videoRef.current?.textTracks ?? []).forEach((track, index) => { track.mode = index === primary || index === secondary ? "showing" : "disabled"; }); }
  function chooseSubtitle(value: number) { const secondary = value === secondarySubtitleTrack ? -1 : secondarySubtitleTrack; setSubtitleTrack(value); setSecondarySubtitleTrack(secondary); if (hlsRef.current) hlsRef.current.subtitleTrack = value; applySubtitleTracks(value, secondary); }
  function chooseSecondarySubtitle(value: number) { const secondary = value === subtitleTrack ? -1 : value; setSecondarySubtitleTrack(secondary); applySubtitleTracks(subtitleTrack, secondary); }

  return <main className="watch-page"><div className={`player-shell captions-${config.caption_size} captions-${config.caption_background} captions-${config.caption_position}`} ref={shellRef}>
    <video ref={videoRef} playsInline preload="metadata" crossOrigin="use-credentials"
      onLoadedMetadata={(event) => { const video = event.currentTarget; setDuration(video.duration); const localResume = clientProgress(config.source_id)?.position_seconds ?? 0; const resume = config.progress?.position_seconds ?? localResume; if (resume > 0 && resume < video.duration - 1) video.currentTime = resume; }}
      onPlay={(event) => { setPlaying(true); setLensReady(false); if (!playStartSent.current) { playStartSent.current = true; const video = event.currentTarget; void trackAnalytics({ event_type: "play_start", movie_id: config.movie_id, episode_id: config.episode_id, position_seconds: video.currentTime, duration_seconds: video.duration, properties: { source: "customer_player" } }); } }}
      onPause={(event) => { setPlaying(false); setLensReady(true); void saveProgress(true); const video = event.currentTarget; if (video.duration > 0) void trackAnalytics({ event_type: "pause", movie_id: config.movie_id, episode_id: config.episode_id, position_seconds: video.currentTime, duration_seconds: video.duration }); }}
      onEnded={(event) => { const video = event.currentTarget; void (async () => { await saveProgress(true); setAfterCreditsOpen(true); })(); void trackAnalytics({ event_type: "completion", movie_id: config.movie_id, episode_id: config.episode_id, position_seconds: video.duration, duration_seconds: video.duration }); }}
      onTimeUpdate={(event) => { setTime(event.currentTarget.currentTime); void saveProgress(); }}
      onVolumeChange={(event) => { setVolume(event.currentTarget.volume); setMuted(event.currentTarget.muted); }}
      onWaiting={() => {
        setStatus("buffering");
        if (playStartSent.current && bufferStartedAt.current === null) bufferStartedAt.current = performance.now();
      }}
      onPlaying={(event) => {
        setStatus("ready");
        const video = event.currentTarget;
        if (!startupSent.current) {
          startupSent.current = true;
          void trackAnalytics({
            event_type: "playback_startup", movie_id: config.movie_id, episode_id: config.episode_id,
            position_seconds: video.currentTime, duration_seconds: video.duration,
            value: Math.max(0, performance.now() - mountedAt.current), properties: { source: "customer_player" },
          });
        }
        if (bufferStartedAt.current !== null) {
          const bufferedSeconds = Math.max(0, (performance.now() - bufferStartedAt.current) / 1000);
          bufferStartedAt.current = null;
          void trackAnalytics({
            event_type: "playback_buffer", movie_id: config.movie_id, episode_id: config.episode_id,
            position_seconds: video.currentTime, duration_seconds: video.duration,
            value: bufferedSeconds, properties: { buffered_seconds: bufferedSeconds },
          });
        }
      }}
      onError={(event) => {
        const video = event.currentTarget;
        if (!playbackErrorSent.current && video.duration > 0) {
          playbackErrorSent.current = true;
          void trackAnalytics({
            event_type: "playback_error", movie_id: config.movie_id, episode_id: config.episode_id,
            position_seconds: video.currentTime, duration_seconds: video.duration,
            properties: { error_code: String(video.error?.code ?? "media"), source: "html-media" },
          });
        }
      }}>
      {config.subtitle_tracks.map((track, index) => <track key={track.url} kind="subtitles" src={track.url} srcLang={track.language} label={track.title ?? track.language.toUpperCase()} default={index === preferredSubtitleIndex} />)}
    </video>
    <div className="player-top"><Link href={config.subtitle ? "/series" : "/movies"}>← Exit player</Link><div><strong>{config.title}</strong>{config.subtitle && <span>{config.subtitle}</span>}</div>{progressState !== "idle" && <small className="progress-save-state">{progressState === "saving" ? "Saving progress…" : "Progress saved"}</small>}</div>
    {(status === "loading" || status === "buffering") && <div className="player-state" role="status">{status === "loading" ? "Preparing adaptive stream…" : "Buffering…"}</div>}
    {status === "error" && <div className="player-state error" role="alert"><p>{error}</p><button onClick={retry}>Retry playback</button></div>}
    {marker && <button className="skip-button" onClick={() => { if (videoRef.current) videoRef.current.currentTime = marker.end; }}>{marker.label}</button>}
    {featureFlags.sceneLens && lensReady && !lensOpen ? <button className="scene-lens-ready" onClick={openLens}>SceneLens ready</button> : null}
    {featureFlags.sceneLens ? <SceneLens sourceId={config.source_id} movieId={config.movie_id} episodeId={config.episode_id} duration={duration} timestamp={time} open={lensOpen} onClose={() => setLensOpen(false)} askEnabled={featureFlags.askMovie} /> : null}
    <AfterCreditsRoom sourceId={config.source_id} open={afterCreditsOpen} onClose={() => setAfterCreditsOpen(false)} />
    <section className="player-controls" aria-label="Video controls">
      <input aria-label="Seek" className="player-seek" type="range" min="0" max={duration || 0} step="0.1" value={Math.min(time, duration || 0)} onChange={(event) => { const next = Number(event.target.value); if (videoRef.current) videoRef.current.currentTime = next; setTime(next); if (duration > 0) void trackAnalytics({ event_type: "seek", movie_id: config.movie_id, episode_id: config.episode_id, position_seconds: next, duration_seconds: duration }); }} />
      <div className="control-row"><button aria-label={playing ? "Pause" : "Play"} onClick={() => { const video = videoRef.current; if (video) void (video.paused ? video.play() : video.pause()); }}>{playing ? "❚❚" : "▶"}</button><span>{clock(time)} / {clock(duration)}</span>
      <button aria-label={muted ? "Unmute" : "Mute"} onClick={() => { if (videoRef.current) videoRef.current.muted = !videoRef.current.muted; }}>{muted ? "Muted" : "Volume"}</button><input aria-label="Volume" type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => { if (videoRef.current) videoRef.current.volume = Number(event.target.value); }} />
      <label>Speed<select aria-label="Playback speed" defaultValue="1" onChange={(event) => { if (videoRef.current) videoRef.current.playbackRate = Number(event.target.value); }}><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label>
      <label>Quality<select aria-label="Quality" value={quality} onChange={(event) => chooseQuality(Number(event.target.value))}><option value="-1">Auto</option>{levels.map((level) => <option key={level.index} value={level.index}>{level.height}p</option>)}</select></label>
      <label>Audio<select aria-label="Audio track" value={audioTrack} disabled={audioTracks.length < 2} onChange={(event) => chooseAudio(Number(event.target.value))}>{audioTracks.length ? audioTracks.map((track) => <option key={track.index} value={track.index}>{track.name || track.lang || `Track ${track.index + 1}`}</option>) : <option>Default</option>}</select></label>
      <label>Subtitles<select aria-label="Subtitles" value={subtitleTrack} disabled={!config.subtitle_tracks.length} onChange={(event) => chooseSubtitle(Number(event.target.value))}><option value="-1">Off</option>{config.subtitle_tracks.map((track, index) => <option key={track.url} value={index}>{track.title ?? track.language.toUpperCase()}</option>)}</select></label>
      <label>Second subtitles<select aria-label="Second subtitles" value={secondarySubtitleTrack} disabled={config.subtitle_tracks.length < 2 || subtitleTrack < 0} onChange={(event) => chooseSecondarySubtitle(Number(event.target.value))}><option value="-1">Off</option>{config.subtitle_tracks.map((track, index) => <option key={track.url} value={index} disabled={index === subtitleTrack}>{track.title ?? track.language.toUpperCase()}</option>)}</select></label>
      {config.next_episode_id && <Link className="player-button" href={`/watch/episodes/${config.next_episode_id}`}>Next episode</Link>}
      {featureFlags.sceneLens ? <button aria-label="Open SceneLens" title="SceneLens (L)" onClick={openLens}>Lens</button> : null}
      <button aria-label="Picture in picture" disabled={typeof document === "undefined" || !document.pictureInPictureEnabled} onClick={() => videoRef.current?.requestPictureInPicture()}>PiP</button><button aria-label="Fullscreen" onClick={() => shellRef.current?.requestFullscreen()}>⛶</button></div>
    </section>
  </div></main>;
}
