"use client";

import { createSHA256 } from "hash-wasm";
import { ChangeEvent, useRef, useState, useSyncExternalStore } from "react";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
const acceptedTypes = ["video/mp4", "video/webm", "video/quicktime"];

export type MediaAsset = {
  id: string; original_filename: string; media_type: string; size_bytes: number;
  checksum_sha256: string; storage_key: string;
  state: "uploading" | "completed" | "failed" | "cancelled";
  etag: string | null; failure_reason: string | null; created_at: string;
  completed_at: string | null;
  upload_strategy: "single" | "multipart"; multipart_part_size: number | null;
  malware_scan_status: "pending" | "scanning" | "clean" | "infected" | "error";
  malware_scan_engine: string | null; malware_scan_signature: string | null;
  malware_scanned_at: string | null;
};
type UploadTicket = { asset: MediaAsset; upload_url: string; method: "PUT"; headers: Record<string, string> };
type MultipartTicket = { asset: MediaAsset; part_size: number; total_parts: number };
type MultipartStatus = { asset: MediaAsset; uploaded_parts: number[]; uploaded_bytes: number; total_parts: number };
type PartTicket = { part_number: number; upload_url: string; method: "PUT" };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiOrigin}${path}`, {
    ...init, credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Request failed (${response.status})`);
  return body as T;
}

async function sha256(file: File, onProgress: (value: number) => void) {
  const hasher = await createSHA256();
  const chunkSize = 4 * 1024 * 1024;
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    const chunk = await file.slice(offset, offset + chunkSize).arrayBuffer();
    hasher.update(new Uint8Array(chunk));
    onProgress(Math.round((Math.min(offset + chunkSize, file.size) / file.size) * 100));
  }
  return hasher.digest("hex");
}

function putFile(ticket: UploadTicket, file: File, onProgress: (value: number) => void, register: (request: XMLHttpRequest) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    register(request); request.open(ticket.method, ticket.upload_url);
    Object.entries(ticket.headers).forEach(([name, value]) => request.setRequestHeader(name, value));
    request.upload.onprogress = (event) => event.lengthComputable && onProgress(Math.round((event.loaded / event.total) * 100));
    request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error(`Object storage rejected the transfer (${request.status})`));
    request.onerror = () => reject(new Error("The object-storage transfer failed"));
    request.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    request.send(file);
  });
}

function putPart(ticket: PartTicket, body: Blob, onProgress: (loaded: number) => void, register: (request: XMLHttpRequest) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest(); register(request); request.open(ticket.method, ticket.upload_url);
    request.upload.onprogress = (event) => onProgress(event.loaded);
    request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error(`Object storage rejected part ${ticket.part_number} (${request.status})`));
    request.onerror = () => reject(new Error("The object-storage part transfer failed"));
    request.onabort = () => reject(new DOMException("Upload paused", "AbortError"));
    request.send(body);
  });
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function UploadManager({ initialAssets }: { initialAssets: MediaAsset[] }) {
  const [assets, setAssets] = useState(initialAssets);
  const hydrated = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<"idle" | "hashing" | "uploading" | "verifying">("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [multipartActive, setMultipartActive] = useState(false);
  const requestRef = useRef<XMLHttpRequest | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const assetRef = useRef<string | null>(null);
  const multipartRef = useRef(false);
  const replace = (asset: MediaAsset) => setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null;
    setError("");
    if (next && !acceptedTypes.includes(next.type)) {
      setFile(null); setError("Choose an MP4, WebM, or QuickTime video."); return;
    }
    setFile(next);
  }

  async function start() {
    if (!file) return;
    setError("");
    let transferCompleted = false;
    try {
      setPhase("hashing"); setProgress(0);
      const checksum = await sha256(file, setProgress);
      if (file.size > 16 * 1024 * 1024) {
        multipartRef.current = true;
        setMultipartActive(true);
        const existing = assets.find((asset) => asset.state === "uploading" && asset.upload_strategy === "multipart" && asset.original_filename === file.name && asset.size_bytes === file.size && asset.checksum_sha256 === checksum);
        const session = existing
          ? await api<MultipartStatus>(`/admin/uploads/${existing.id}/multipart`)
          : await api<MultipartTicket>("/admin/uploads/initialize-multipart", { method: "POST", body: JSON.stringify({ original_filename: file.name, media_type: file.type, size_bytes: file.size, checksum_sha256: checksum }) });
        const multipartAsset = session.asset;
        assetRef.current = multipartAsset.id; replace(multipartAsset);
        const partSize = multipartAsset.multipart_part_size!;
        const uploaded = new Set("uploaded_parts" in session ? session.uploaded_parts : []);
        let committed = "uploaded_bytes" in session ? session.uploaded_bytes : 0;
        setPhase("uploading"); setProgress(Math.round((committed / file.size) * 100));
        for (let number = 1; number <= session.total_parts; number += 1) {
          if (uploaded.has(number)) continue;
          const start = (number - 1) * partSize;
          const body = file.slice(start, Math.min(start + partSize, file.size));
          const signed = await api<PartTicket>(`/admin/uploads/${multipartAsset.id}/multipart/parts/${number}`, { method: "POST" });
          await putPart(signed, body, (loaded) => setProgress(Math.round(((committed + loaded) / file.size) * 100)), (request) => (requestRef.current = request));
          committed += body.size;
        }
        setPhase("verifying");
        replace(await api<MediaAsset>(`/admin/uploads/${multipartAsset.id}/multipart/complete`, { method: "POST" }));
        setFile(null); setProgress(100); if (inputRef.current) inputRef.current.value = "";
        return;
      }
      const ticket = await api<UploadTicket>("/admin/uploads/initialize", {
        method: "POST",
        body: JSON.stringify({ original_filename: file.name, media_type: file.type, size_bytes: file.size, checksum_sha256: checksum }),
      });
      assetRef.current = ticket.asset.id; replace(ticket.asset);
      setPhase("uploading"); setProgress(0);
      await putFile(ticket, file, setProgress, (request) => (requestRef.current = request));
      transferCompleted = true;
      setPhase("verifying");
      replace(await api<MediaAsset>(`/admin/uploads/${ticket.asset.id}/complete`, { method: "POST" }));
      setFile(null); setProgress(100);
      if (inputRef.current) inputRef.current.value = "";
    } catch (reason) {
      const cancelled = reason instanceof DOMException && reason.name === "AbortError";
      const message = reason instanceof Error ? reason.message : "Upload failed";
      setError(cancelled ? "Upload cancelled." : message);
      if (assetRef.current && !multipartRef.current && !transferCompleted) {
        const asset = cancelled
          ? await api<MediaAsset>(`/admin/uploads/${assetRef.current}`, { method: "DELETE" })
          : await api<MediaAsset>(`/admin/uploads/${assetRef.current}/fail`, { method: "POST", body: JSON.stringify({ reason: message }) }).catch(() => null);
        if (asset) replace(asset);
      } else if (multipartRef.current) {
        setNotice("Multipart upload retained. Choose the same file and start again to resume completed parts.");
      }
    } finally {
      setPhase("idle"); requestRef.current = null; assetRef.current = null; multipartRef.current = false; setMultipartActive(false);
    }
  }

  async function queueProcessing(assetId: string) {
    setError(""); setNotice("");
    try {
      await api(`/admin/processing/${assetId}`, { method: "POST" });
      setNotice("Processing job queued. Track it in Processing.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not queue processing");
    }
  }

  async function retryScan(assetId: string, multipart: boolean) {
    setError(""); setNotice("");
    try {
      const suffix = multipart ? "/multipart/complete" : "/complete";
      const asset = await api<MediaAsset>(`/admin/uploads/${assetId}${suffix}`, { method: "POST" });
      replace(asset);
      setNotice(asset.malware_scan_status === "clean" ? "Malware scan passed. The asset is ready for processing." : "Malware scan updated.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retry malware scan");
    }
  }

  function scanLabel(asset: MediaAsset) {
    if (asset.malware_scan_status === "clean") {
      const scanned = asset.malware_scanned_at ? ` · ${asset.malware_scanned_at.replace("T", " ").replace("Z", " UTC")}` : "";
      return `Malware scan clean${asset.malware_scan_engine ? ` · ${asset.malware_scan_engine}` : ""}${scanned}`;
    }
    if (asset.malware_scan_status === "infected") return `Rejected: malware detected${asset.malware_scan_signature ? ` · ${asset.malware_scan_signature}` : ""}`;
    if (asset.malware_scan_status === "error") return "Quarantined: scanner unavailable";
    return "Quarantined: malware scan pending";
  }

  const busy = phase !== "idle";
  const phaseLabel = phase === "hashing" ? "Calculating integrity checksum" : phase === "uploading" ? "Transferring to object storage" : "Verifying stored object";
  return <div className="upload-layout">
    <section className="upload-drop studio-editor-section">
      <div className="form-section-heading"><div><p className="eyebrow">Direct transfer</p><h2>Upload a source video</h2></div><span>MP4 · WebM · MOV · 5 GiB max</span></div>
      <label className="file-picker"><span>{file ? file.name : "Choose a permitted source file"}</span><small>{file ? `${formatBytes(file.size)} · ${file.type}` : "The original filename is retained as metadata only."}</small><input ref={inputRef} type="file" accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov" onChange={choose} disabled={!hydrated || busy} /></label>
      {busy && <div className="upload-progress" aria-live="polite"><div><span>{phaseLabel}</span><strong>{progress}%</strong></div><progress max="100" value={progress} /></div>}
      {error && <p className="studio-form-error" role="alert">{error}</p>}
      {notice && <p className="studio-form-success" role="status">{notice}</p>}
      <div className="upload-actions"><button className="studio-primary" type="button" disabled={!file || busy} onClick={start}>Start secure upload</button>{phase === "uploading" && <button className="studio-secondary" type="button" onClick={() => requestRef.current?.abort()}>{multipartActive ? "Pause transfer" : "Cancel transfer"}</button>}</div>
    </section>
    <section className="studio-editor-section">
      <div className="form-section-heading"><div><p className="eyebrow">Asset registry</p><h2>Recent source assets</h2></div><span>{assets.length} {assets.length === 1 ? "record" : "records"}</span></div>
      {assets.length === 0 ? <p className="studio-empty-inline">No source assets have been initialized.</p> : <ul className="upload-list">{assets.map((asset) => <li key={asset.id}><div><strong>{asset.original_filename}</strong><small>{formatBytes(asset.size_bytes)} · {asset.media_type}<br />{asset.storage_key}</small></div><div><span className={`catalog-badge ${asset.state}`}>{asset.state}</span><small>{scanLabel(asset)}</small>{asset.state === "completed" && asset.malware_scan_status === "clean" && <button className="queue-link" type="button" onClick={() => queueProcessing(asset.id)}>Queue processing</button>}{asset.malware_scan_status === "error" && <button className="queue-link" type="button" onClick={() => retryScan(asset.id, asset.upload_strategy === "multipart")}>Retry malware scan</button>}{asset.failure_reason && <small>{asset.failure_reason}</small>}</div></li>)}</ul>}
    </section>
  </div>;
}
