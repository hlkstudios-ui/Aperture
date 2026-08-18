import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UploadManager, type MediaAsset } from "./upload-manager";

function asset(overrides: Partial<MediaAsset>): MediaAsset {
  return {
    id: "asset-1",
    original_filename: "master.mp4",
    media_type: "video/mp4",
    size_bytes: 1024,
    checksum_sha256: "a".repeat(64),
    storage_key: "private/source/asset-1",
    state: "uploading",
    etag: null,
    failure_reason: null,
    created_at: "2026-08-16T00:00:00Z",
    completed_at: null,
    upload_strategy: "single",
    multipart_part_size: null,
    malware_scan_status: "pending",
    malware_scan_engine: null,
    malware_scan_signature: null,
    malware_scanned_at: null,
    ...overrides,
  };
}

describe("UploadManager malware quarantine", () => {
  it("offers retry but never processing when the scanner is unavailable", () => {
    render(<UploadManager initialAssets={[asset({ malware_scan_status: "error", failure_reason: "Scan unavailable; object quarantined" })]} />);

    expect(screen.getByText("Quarantined: scanner unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry malware scan" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Queue processing" })).not.toBeInTheDocument();
  });

  it("allows processing only after a clean persisted verdict", () => {
    render(<UploadManager initialAssets={[asset({ state: "completed", malware_scan_status: "clean", malware_scan_engine: "clamav", malware_scanned_at: "2026-08-16T01:00:00Z" })]} />);

    expect(screen.getByText(/Malware scan clean · clamav/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue processing" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry malware scan" })).not.toBeInTheDocument();
  });

  it("shows detected uploads as rejected and non-processable", () => {
    render(<UploadManager initialAssets={[asset({ state: "failed", malware_scan_status: "infected", malware_scan_signature: "Eicar-Signature" })]} />);

    expect(screen.getByText("Rejected: malware detected · Eicar-Signature")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Queue processing" })).not.toBeInTheDocument();
  });
});
