// @vitest-environment node

import { createHash } from "node:crypto";
import { inflateSync } from "node:zlib";
import { createElement } from "react";
import { ImageResponse } from "next/og";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { generatedLogoGlyphs, generatedLogoVariants } from "@/app/lib/generated-logo";
import { generatedLogoGlyphOutlines } from "@/app/lib/generated-logo-glyph-paths";
import { DEFAULT_SITE_BRAND } from "@/app/lib/site-brand";

const brandLoader = vi.hoisted(() => vi.fn());

vi.mock("@/app/lib/site-brand-server", () => ({
  getSiteBrand: brandLoader,
}));

import Icon from "@/app/icon";
import AppleIcon from "@/app/apple-icon";

beforeEach(() => {
  brandLoader.mockReset();
});

function paeth(left: number, up: number, upperLeft: number): number {
  const estimate = left + up - upperLeft;
  const leftDistance = Math.abs(estimate - left);
  const upDistance = Math.abs(estimate - up);
  const upperLeftDistance = Math.abs(estimate - upperLeft);
  return leftDistance <= upDistance && leftDistance <= upperLeftDistance
    ? left
    : upDistance <= upperLeftDistance ? up : upperLeft;
}

function decodeRgbaPng(bytes: Uint8Array): { width: number; height: number; rgba: Uint8Array } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const width = view.getUint32(16);
  const height = view.getUint32(20);
  expect(bytes[24]).toBe(8);
  expect(bytes[25]).toBe(6);
  expect(bytes[28]).toBe(0);
  const chunks: Uint8Array[] = [];
  for (let offset = 8; offset < bytes.byteLength;) {
    const length = view.getUint32(offset);
    const type = String.fromCharCode(...bytes.slice(offset + 4, offset + 8));
    if (type === "IDAT") chunks.push(bytes.slice(offset + 8, offset + 8 + length));
    offset += length + 12;
  }
  const compressed = Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)));
  const raw = inflateSync(compressed);
  const stride = width * 4;
  const rgba = new Uint8Array(stride * height);
  let source = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[source];
    source += 1;
    for (let x = 0; x < stride; x += 1) {
      const encoded = raw[source];
      source += 1;
      const left = x >= 4 ? rgba[y * stride + x - 4] : 0;
      const up = y > 0 ? rgba[(y - 1) * stride + x] : 0;
      const upperLeft = y > 0 && x >= 4 ? rgba[(y - 1) * stride + x - 4] : 0;
      const predictor = filter === 0 ? 0
        : filter === 1 ? left
          : filter === 2 ? up
            : filter === 3 ? Math.floor((left + up) / 2)
              : paeth(left, up, upperLeft);
      rgba[y * stride + x] = (encoded + predictor) & 0xff;
    }
  }
  return { width, height, rgba };
}

async function glyphOpticalCenter(glyph: (typeof generatedLogoGlyphs)[number], pixelSize: number) {
  const response = new ImageResponse(
    createElement("div", {
      style: { background: "#fff", display: "flex", height: "100%", width: "100%" },
    }, createElement("svg", {
      height: pixelSize,
      viewBox: "0 0 104 104",
      width: pixelSize,
    }, createElement("path", { d: generatedLogoGlyphOutlines[glyph].d, fill: "#000" }))),
    { height: pixelSize, width: pixelSize },
  );
  const decoded = decodeRgbaPng(new Uint8Array(await response.arrayBuffer()));
  let left = decoded.width;
  let top = decoded.height;
  let right = -1;
  let bottom = -1;
  let mass = 0;
  let massX = 0;
  let massY = 0;
  for (let y = 0; y < decoded.height; y += 1) {
    for (let x = 0; x < decoded.width; x += 1) {
      const offset = (y * decoded.width + x) * 4;
      const weight = 255 - (decoded.rgba[offset] + decoded.rgba[offset + 1] + decoded.rgba[offset + 2]) / 3;
      if (weight <= 1) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x);
      bottom = Math.max(bottom, y);
      mass += weight;
      massX += (x + 0.5) * weight;
      massY += (y + 0.5) * weight;
    }
  }
  expect(mass).toBeGreaterThan(0);
  return {
    x: 0.65 * ((left + right + 1) / 2) + 0.35 * (massX / mass),
    y: 0.65 * ((top + bottom + 1) / 2) + 0.35 * (massY / mass),
  };
}

describe("runtime generated-logo favicon", () => {
  it("rasterizes every SVG construction through the real Next ImageResponse", async () => {
    for (const variant of generatedLogoVariants) {
      brandLoader.mockResolvedValueOnce({
        ...DEFAULT_SITE_BRAND,
        revision: 9,
        logo_mark: { renderer_version: 1, glyph: "q", variant: variant.id },
      });

      const response = await Icon();
      expect(response.headers.get("content-type")).toContain("image/png");
      const bytes = new Uint8Array(await response.arrayBuffer());
      expect(Array.from(bytes.slice(0, 8))).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
      expect(new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16)).toBe(64);
      expect(bytes.byteLength).toBeGreaterThan(200);
    }
  }, 20_000);

  it("renders a dedicated high-resolution Apple touch icon", async () => {
    brandLoader.mockResolvedValueOnce({
      ...DEFAULT_SITE_BRAND,
      revision: 9,
      logo_mark: { renderer_version: 1, glyph: "Q", variant: "orbit" },
    });

    const response = await AppleIcon();
    const bytes = new Uint8Array(await response.arrayBuffer());
    expect(response.headers.get("content-type")).toContain("image/png");
    expect(Array.from(bytes.slice(0, 8))).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
    expect(new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16)).toBe(180);
    expect(bytes.byteLength).toBeGreaterThan(200);
  });

  it("rasterizes all 52 pre-centered glyph outlines without font fallback", async () => {
    const hashes = new Set<string>();
    for (const glyph of generatedLogoGlyphs) {
      brandLoader.mockResolvedValueOnce({
        ...DEFAULT_SITE_BRAND,
        revision: 10,
        logo_mark: { renderer_version: 1, glyph, variant: "iris" },
      });

      const response = await Icon();
      const bytes = new Uint8Array(await response.arrayBuffer());
      expect(Array.from(bytes.slice(0, 8))).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
      expect(bytes.byteLength).toBeGreaterThan(200);
      hashes.add(createHash("sha256").update(bytes).digest("hex"));
    }
    expect(hashes).toHaveLength(52);
  }, 30_000);

  it("keeps visible ink optically centered at favicon and large-preview sizes", async () => {
    for (const pixelSize of [16, 176]) {
      for (const glyph of generatedLogoGlyphs) {
        const center = await glyphOpticalCenter(glyph, pixelSize);
        expect(Math.abs(center.x - pixelSize / 2), `${glyph} x=${center.x} at ${pixelSize}px`).toBeLessThanOrEqual(1);
        expect(Math.abs(center.y - pixelSize / 2), `${glyph} y=${center.y} at ${pixelSize}px`).toBeLessThanOrEqual(1);
      }
    }
  }, 30_000);
});
