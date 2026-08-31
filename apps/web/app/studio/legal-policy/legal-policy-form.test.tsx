import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LegalPolicyRecord } from "./legal-policy-types";

const mocks = vi.hoisted(() => ({ save: vi.fn() }));

vi.mock("./actions", () => ({
  saveLegalPolicyDraftAction: mocks.save,
}));

import { LegalPolicyForm } from "./legal-policy-form";

const record: LegalPolicyRecord = {
  schema_version: 1,
  revision: 7,
  status: "draft",
  legal_operator_name: "HLK Studios Inc.",
  country_code: "CA",
  region: "Ontario",
  support_email: "support@example.com",
  privacy_email: "privacy@example.com",
  copyright_email: "copyright@example.com",
  minimum_user_age: 13,
  governing_law_jurisdiction: "Ontario, Canada",
  updated_at: "2026-08-31T05:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.save.mockImplementation(async (state: unknown) => state);
});

describe("LegalPolicyForm", () => {
  it("loads every owner fact into a clearly private, non-approving draft", () => {
    render(<LegalPolicyForm initialRecord={record} />);

    expect(screen.getByLabelText(/Legal operator or business name/i)).toHaveValue("HLK Studios Inc.");
    expect(screen.getByLabelText(/Country/i)).toHaveValue("CA");
    expect(screen.getByLabelText(/Province or state/i)).toHaveValue("Ontario");
    expect(screen.getByLabelText(/Support email/i)).toHaveValue("support@example.com");
    expect(screen.getByLabelText(/Privacy email/i)).toHaveValue("privacy@example.com");
    expect(screen.getByLabelText(/Copyright and takedown email/i)).toHaveValue("copyright@example.com");
    expect(screen.getByLabelText(/Minimum user age/i)).toHaveValue(13);
    expect(screen.getByLabelText(/Governing-law jurisdiction/i)).toHaveValue("Ontario, Canada");
    expect(screen.getByRole("heading", { name: /does not approve or publish policies/i })).toBeInTheDocument();
    expect(screen.getByText(/does not generate legal text/i)).toBeInTheDocument();
    expect(screen.getByText(/does not.*automatically update or invalidate separately approved policy documents/i)).toBeInTheDocument();
    expect(screen.getByText("Last private save: Aug 31, 2026 at 05:00 UTC")).toBeInTheDocument();
    expect(screen.getAllByText("Optional draft field")).toHaveLength(8);
    expect(document.querySelector("[required]")).toBeNull();
  });

  it("submits the typed full draft through the action and announces the result", async () => {
    mocks.save.mockImplementationOnce(async (state: { sequence: number; revision: number }) => ({
      ...state,
      sequence: state.sequence + 1,
      revision: 8,
      updatedAt: "2026-08-31T06:00:00Z",
      error: "",
      notice: "Private draft saved. No policy was approved or published.",
    }));
    render(<LegalPolicyForm initialRecord={record} />);

    fireEvent.change(screen.getByLabelText(/Legal operator or business name/i), {
      target: { value: "Northstar Media Ltd." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save private draft" }));

    await waitFor(() => expect(mocks.save).toHaveBeenCalledOnce());
    const submitted = mocks.save.mock.calls[0]?.[1];
    expect(submitted).toBeInstanceOf(FormData);
    expect((submitted as FormData).get("legal_operator_name")).toBe("Northstar Media Ltd.");
    expect((submitted as FormData).get("revision")).toBe("7");
    expect(await screen.findByRole("status")).toHaveTextContent(/No policy was approved or published/i);
  });

  it("associates explanatory text with the jurisdiction and age controls", () => {
    render(<LegalPolicyForm initialRecord={{
      ...record,
      governing_law_jurisdiction: null,
      minimum_user_age: null,
    }} />);

    expect(screen.getByLabelText(/Governing-law jurisdiction/i)).toHaveAccessibleDescription(
      /does not choose it for you/i,
    );
    expect(screen.getByLabelText(/Minimum user age/i)).toHaveAccessibleDescription(
      /does not provide legal advice/i,
    );
  });

  it("remounts identical action feedback so repeated saves are announced again", async () => {
    mocks.save.mockImplementation(async (state: { sequence: number; revision: number }) => ({
      ...state,
      sequence: state.sequence + 1,
      revision: state.revision + 1,
      updatedAt: "2026-08-31T06:00:00Z",
      error: "",
      notice: "Private draft saved. No policy was approved or published.",
    }));
    render(<LegalPolicyForm initialRecord={record} />);

    fireEvent.click(screen.getByRole("button", { name: "Save private draft" }));
    const firstAnnouncement = await screen.findByRole("status");

    fireEvent.click(screen.getByRole("button", { name: "Save private draft" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole("status")).not.toBe(firstAnnouncement));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Private draft saved. No policy was approved or published.",
    );
  });
});
