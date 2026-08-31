import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ViewerAccount, ViewerProfile } from "@/app/lib/customer-session";

import { ProfileSelector } from "./profile-selector";

const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function profile(id: string, name: string, overrides: Partial<ViewerProfile> = {}): ViewerProfile {
  return {
    id,
    name,
    avatar_key: null,
    maturity_level: "adult",
    language: "en",
    is_kids: false,
    preference: {
      autoplay_next: true,
      autoplay_previews: true,
      preferred_audio_language: null,
      preferred_subtitle_language: null,
      preferred_secondary_subtitle_language: null,
      subtitles_enabled: false,
      timezone: "America/Toronto",
      caption_size: "medium",
      caption_background: "shadow",
      caption_position: "bottom",
      cinephile_mode: false,
      rewatch_intelligence_enabled: true,
      analytics_enabled: true,
      consent_updated_at: null,
      homepage_mode: "curated",
    },
    ...overrides,
  };
}

function account(profiles = [profile("profile-1", "Harjot")]): ViewerAccount {
  return { id: "account-1", email: "viewer@example.com", profiles, active_profile_id: profiles[0]?.id ?? null };
}

afterEach(() => {
  cleanup();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

describe("ProfileSelector", () => {
  it("presents profile selection and creation controls accessibly", () => {
    render(<ProfileSelector account={account()} />);

    expect(screen.getByRole("button", { name: /Harjot Normal Mode Watching now/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Create a profile" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Profile name" })).toHaveAttribute("maxlength", "50");
    expect(screen.getByRole("checkbox", { name: /Kids profile/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Add profile" })).toBeEnabled();
  });

  it("submits a Kids profile with the expected maturity contract", async () => {
    const created = profile("profile-2", "Little Viewer", { is_kids: true, maturity_level: "kids" });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => created });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProfileSelector account={account()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Profile name" }), { target: { value: "Little Viewer" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Kids profile/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add profile" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/profiles$/);
    expect(request.credentials).toBe("include");
    expect(JSON.parse(request.body as string)).toEqual({ name: "Little Viewer", is_kids: true, maturity_level: "kids" });
    expect(await screen.findByRole("button", { name: /Little Viewer Kids profile/ })).toBeInTheDocument();
  });

  it("hides profile creation after the five-profile limit", () => {
    const profiles = Array.from({ length: 5 }, (_, index) => profile(`profile-${index}`, `Viewer ${index + 1}`));
    render(<ProfileSelector account={account(profiles)} />);

    expect(screen.queryByRole("heading", { name: "Create a profile" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add profile" })).not.toBeInTheDocument();
  });
});
