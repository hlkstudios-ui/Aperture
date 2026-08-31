import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ViewerPlan } from "./monetization-types";

const mocks = vi.hoisted(() => ({ archive: vi.fn(), create: vi.fn() }));

vi.mock("./plan-actions", () => ({
  archiveViewerPlanAction: mocks.archive,
  createViewerPlanAction: mocks.create,
}));

import { ViewerPlanManager } from "./viewer-plan-manager";

function plan(overrides: Partial<ViewerPlan> = {}): ViewerPlan {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    code: "cinema-monthly",
    name: "Cinema Monthly",
    description: "Two streams with the complete catalogue.",
    price_cents: 1299,
    currency: "CAD",
    interval: "month",
    max_streams: 2,
    max_resolution: "1080p",
    is_active: true,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.archive.mockImplementation(async (state: unknown) => state);
  mocks.create.mockImplementation(async (state: unknown) => state);
});

describe("ViewerPlanManager", () => {
  it("presents an accessible create form without implying paid access is active", () => {
    render(<ViewerPlanManager plans={[]} />);

    expect(screen.getByRole("group", { name: "Create a viewer plan" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Plan code/i)).toHaveAccessibleDescription(/Spaces become hyphens/i);
    expect(screen.getByLabelText("Customer-facing name")).toBeRequired();
    expect(screen.getByLabelText("Description")).toBeRequired();
    expect(screen.getByRole("textbox", { name: /^Price\b/i })).toHaveAccessibleDescription(/two decimal places/i);
    const currency = screen.getByLabelText(/Currency/i);
    expect(currency).toHaveValue("CAD");
    expect(currency).toHaveAccessibleDescription(/AUD, CAD, EUR, GBP, and USD/i);
    expect(within(currency).getAllByRole("option").map((option) => option.getAttribute("value")))
      .toEqual(["AUD", "CAD", "EUR", "GBP", "USD"]);
    expect(screen.getByLabelText("Billing interval")).toHaveValue("month");
    expect(screen.getByLabelText("Simultaneous streams")).toHaveValue(1);
    expect(screen.getByLabelText("Maximum resolution")).toHaveValue("1080p");
    expect(screen.getByText(/does not turn on subscription-required access/i)).toBeInTheDocument();
    expect(screen.getByText(/does not turn on .*customer checkout/i)).toBeInTheDocument();
    expect(screen.getByText(/storefront remains free/i)).toBeInTheDocument();
  });

  it("lists active and archived plans with immutable historical terms", () => {
    render(<ViewerPlanManager plans={[
      plan(),
      plan({
        id: "22222222-2222-4222-8222-222222222222",
        code: "cinema-annual-legacy",
        name: "Cinema Annual Legacy",
        price_cents: 9900,
        interval: "year",
        is_active: false,
      }),
    ]} />);

    expect(screen.getByText(/Published price and terms are immutable/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cinema Monthly" })).toBeInTheDocument();
    expect(screen.getByText("$12.99 / month")).toBeInTheDocument();
    expect(screen.getByText(/Archived plans/)).toHaveTextContent("1");
    fireEvent.click(screen.getByText(/Archived plans/));
    expect(screen.getByRole("heading", { name: "Cinema Annual Legacy" })).toBeInTheDocument();
    expect(screen.getByText(/Unavailable to new viewers/i)).toBeInTheDocument();
  });

  it("submits only the plan id and owner-entered confirmation after the client convenience check", async () => {
    render(<ViewerPlanManager plans={[plan()]} />);
    fireEvent.click(screen.getByText("Archive plan", { selector: "summary" }));
    const confirmation = screen.getByLabelText(/Type cinema-monthly to confirm/i);
    const button = screen.getByRole("button", { name: "Archive this plan" });
    expect(button).toBeDisabled();
    fireEvent.change(confirmation, { target: { value: "cinema-monthly" } });
    expect(button).toBeEnabled();
    fireEvent.click(button);

    await waitFor(() => expect(mocks.archive).toHaveBeenCalledOnce());
    const submitted = mocks.archive.mock.calls[0]?.[1];
    expect(submitted).toBeInstanceOf(FormData);
    expect((submitted as FormData).get("plan_id")).toBe("11111111-1111-4111-8111-111111111111");
    expect((submitted as FormData).get("confirmation")).toBe("cinema-monthly");
    expect((submitted as FormData).has("plan_code")).toBe(false);
  });

  it("submits every create field through the server action", async () => {
    render(<ViewerPlanManager plans={[]} />);
    const group = screen.getByRole("group", { name: "Create a viewer plan" });
    fireEvent.change(within(group).getByLabelText(/Plan code/i), { target: { value: "festival monthly" } });
    fireEvent.change(within(group).getByLabelText("Customer-facing name"), { target: { value: "Festival Monthly" } });
    fireEvent.change(within(group).getByLabelText("Description"), { target: { value: "Festival access." } });
    fireEvent.change(within(group).getByRole("textbox", { name: /^Price\b/i }), { target: { value: "8.50" } });
    fireEvent.click(screen.getByRole("button", { name: "Create active plan" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledOnce());
    const submitted = mocks.create.mock.calls[0]?.[1];
    expect(submitted).toBeInstanceOf(FormData);
    expect((submitted as FormData).get("code")).toBe("festival monthly");
    expect((submitted as FormData).get("price")).toBe("8.50");
    expect((submitted as FormData).get("currency")).toBe("CAD");
    expect((submitted as FormData).get("max_resolution")).toBe("1080p");
  });
});
