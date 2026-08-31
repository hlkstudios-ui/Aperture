import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LaunchSetupWizard, onAccentColor } from "./launch-setup-wizard";
import { defaultLaunchSetup, type LaunchSetupRecord } from "./launch-setup-types";

const actionMocks = vi.hoisted(() => ({
  assist: vi.fn(),
  mutate: vi.fn(async (state: unknown, form?: FormData) => {
    void form;
    return state;
  }),
  upload: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("./actions", () => ({
  assistBrandCopyAction: actionMocks.assist,
  mutateLaunchSetupAction: actionMocks.mutate,
  uploadLaunchLogoAction: actionMocks.upload,
  removeLaunchLogoAction: actionMocks.remove,
}));

function setup(overrides: Partial<LaunchSetupRecord> = {}): LaunchSetupRecord {
  return {
    ...defaultLaunchSetup,
    config: {
      ...defaultLaunchSetup.config,
      business_name: "Northstar Cinema",
      short_name: "Northstar",
      tagline: "Films that leave the light on.",
    },
    ...overrides,
  };
}

describe("LaunchSetupWizard", () => {
  const suggestions = [
    {
      short_name: "Northstar",
      tagline: "The screen, seen differently.",
      description: "A considered home for daring films, essential series, and the people who love them.",
      tone_direction: "Editorial and assured",
    },
    {
      short_name: "Northstar House",
      tagline: "Stay for the final frame.",
      description: "Cinema with a point of view, gathered for viewers who want more than an algorithm.",
      tone_direction: "Intimate and cinematic",
    },
    {
      short_name: "Northstar",
      tagline: "Your next obsession starts here.",
      description: "A vivid destination for cult discoveries, modern classics, and stories worth sharing.",
      tone_direction: "Bold and contemporary",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    actionMocks.assist.mockReset();
  });

  it("presents a private, staged and resumable launch file", () => {
    render(<LaunchSetupWizard initialSetup={setup()} />);

    expect(screen.getByRole("heading", { name: /turn the template into your screen/i })).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Launch setup stages" });
    expect(within(navigation).getAllByRole("button")).toHaveLength(5);
    expect(screen.getByText("Owner-only workspace")).toBeInTheDocument();
    expect(screen.getByText("Nothing here is shown publicly until you approve the final frame.")).toBeInTheDocument();
    expect(screen.getByLabelText("0% of launch setup complete")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Live brand preview" })).toBeInTheDocument();
  });

  it("updates the customer preview as the buyer names the business", () => {
    render(<LaunchSetupWizard initialSetup={setup()} />);

    fireEvent.change(screen.getByLabelText(/Business name/), { target: { value: "Lumen House" } });
    expect(screen.getByRole("heading", { name: "Tonight belongs to Lumen House." })).toBeInTheDocument();
  });

  it("invokes AI explicitly and applies an edited direction only to the unsaved draft", async () => {
    actionMocks.assist.mockResolvedValueOnce({ error: "", suggestions });
    render(<LaunchSetupWizard initialSetup={setup()} />);

    expect(actionMocks.assist).not.toHaveBeenCalled();
    expect(screen.getByText(/are sent to OpenAI/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Who is this for?"), {
      target: { value: "Curious viewers who seek independent cinema" },
    });
    fireEvent.change(screen.getByLabelText("Voice"), { target: { value: "refined" } });
    fireEvent.click(screen.getByRole("button", { name: "Create three directions" }));

    expect(await screen.findByLabelText("Tagline, direction 1")).toHaveValue("The screen, seen differently.");
    expect(actionMocks.assist).toHaveBeenCalledWith(expect.objectContaining({
      business_name: "Northstar Cinema",
      audience: "Curious viewers who seek independent cinema",
      tone: "refined",
    }));
    expect(screen.getByPlaceholderText("Films that leave the light on.")).toHaveValue("Films that leave the light on.");
    expect(actionMocks.mutate).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Tagline, direction 1"), {
      target: { value: "Every frame has a pulse." },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Apply this direction" })[0]);

    expect(screen.getByPlaceholderText("Films that leave the light on.")).toHaveValue("Every frame has a pulse.");
    expect(screen.getByRole("status")).toHaveTextContent(/unsaved draft/i);
    expect(actionMocks.mutate).not.toHaveBeenCalled();
  });

  it("keeps AI failures retryable without replacing current copy", async () => {
    actionMocks.assist
      .mockResolvedValueOnce({ error: "AI writing assistance is not available yet. Configure the writing service, then retry.", suggestions: [] })
      .mockResolvedValueOnce({ error: "", suggestions });
    render(<LaunchSetupWizard initialSetup={setup()} />);

    fireEvent.click(screen.getByRole("button", { name: "Create three directions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("AI writing assistance is not available yet.");
    expect(screen.getByPlaceholderText("Films that leave the light on.")).toHaveValue("Films that leave the light on.");

    const retry = screen.getByRole("button", { name: "Try again" });
    await waitFor(() => expect(retry).toBeEnabled());
    fireEvent.click(retry);
    await waitFor(() => expect(actionMocks.assist).toHaveBeenCalledTimes(2));
    expect(await screen.findByLabelText("Tagline, direction 1")).toBeInTheDocument();
  });

  it("locks the brief, stage navigation, and draft save while generation is pending", async () => {
    let resolveAssist!: (value: { error: string; suggestions: typeof suggestions }) => void;
    actionMocks.assist.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAssist = resolve;
    }));
    render(<LaunchSetupWizard initialSetup={setup()} />);

    fireEvent.click(screen.getByRole("button", { name: "Create three directions" }));

    await waitFor(() => expect(screen.getByLabelText(/Business name/)).toBeDisabled());
    expect(screen.getByLabelText("Voice")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Identity/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save & continue" })).toBeDisabled();

    await act(async () => resolveAssist({ error: "AI writing assistance is not available yet.", suggestions: [] }));
    await waitFor(() => expect(screen.getByLabelText(/Business name/)).toBeEnabled());
  });

  it("offers every letter case through a curated SVG atelier without a file or URL input", () => {
    render(<LaunchSetupWizard initialSetup={setup({ current_step: 5, completed_steps: [1, 2, 3, 4] })} />);

    fireEvent.click(screen.getByRole("button", { name: /Signature/ }));
    expect(screen.getByRole("heading", { name: "Choose a mark that survives every screen." })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Uppercase A" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Lowercase/ }));
    expect(screen.getByRole("radio", { name: "Lowercase z" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio", { name: /style|cut|light|split|orbit|frame|eclipse|block|echo|portal|monolith|ribbon|beam/i })).toHaveLength(12);
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(document.querySelector('input[type="url"]')).toBeNull();
  });

  it("keeps a chosen lowercase recipe private until the normal stage save", async () => {
    render(<LaunchSetupWizard initialSetup={setup({ current_step: 5, completed_steps: [1, 2, 3, 4] })} />);

    fireEvent.click(screen.getByRole("button", { name: /Signature/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Lowercase/ }));
    fireEvent.click(screen.getByRole("radio", { name: "Lowercase q" }));
    fireEvent.click(screen.getByRole("radio", { name: "Ribbon loop, lowercase q" }));

    expect(actionMocks.mutate).not.toHaveBeenCalled();
    expect(document.querySelector('[data-logo-glyph="q"][data-logo-variant="ribbon"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));

    await waitFor(() => expect(actionMocks.mutate).toHaveBeenCalledTimes(1));
    const form = actionMocks.mutate.mock.calls[0]?.[1];
    expect(form).toBeInstanceOf(FormData);
    if (!(form instanceof FormData)) throw new Error("Expected the launch form payload");
    const payload = JSON.parse(String(form.get("payload"))) as { logo_mark: unknown };
    expect(payload.logo_mark).toEqual({ renderer_version: 1, glyph: "q", variant: "ribbon" });
  });

  it("describes the home market honestly without treating it as a rights territory", () => {
    render(<LaunchSetupWizard initialSetup={setup({ current_step: 5, completed_steps: [1, 2, 3, 4] })} />);

    fireEvent.click(screen.getByRole("button", { name: /Home market/ }));
    expect(screen.getByText("Your business base—not a rights declaration.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Default language" })).toHaveValue("en-US");
    expect(screen.getByLabelText("Display currency")).toHaveValue("USD");
  });

  it("requires explicit approval before publication", () => {
    render(<LaunchSetupWizard initialSetup={setup({ current_step: 5, completed_steps: [1, 2, 3, 4] })} />);

    fireEvent.click(screen.getByRole("button", { name: "Publish my brand" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Confirm that the preview is ready to become the public identity.");
  });

  it("requires a fresh approval after the selected mark changes", () => {
    render(<LaunchSetupWizard initialSetup={setup({ current_step: 5, completed_steps: [1, 2, 3, 4] })} />);

    const approval = screen.getByRole("checkbox", { name: /I approve this identity/i });
    fireEvent.click(approval);
    expect(approval).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /Signature/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Lowercase/ }));
    fireEvent.click(screen.getByRole("button", { name: /Premiere/ }));

    expect(screen.getByRole("checkbox", { name: /I approve this identity/i })).not.toBeChecked();
  });

  it("derives one accessible text color for normal and hover accent buttons", () => {
    expect(onAccentColor(defaultLaunchSetup.config.palette)).toBe("#000000");
    expect(onAccentColor({
      ...defaultLaunchSetup.config.palette,
      accent: "#6f6f6f",
      accent_hover: "#808080",
    })).toBeNull();
  });
});
