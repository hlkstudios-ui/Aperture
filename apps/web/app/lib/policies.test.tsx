import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SiteFooter } from "@/app/components/site-footer";
import { approvedPolicies, approvedPolicy } from "./policies";

describe("policy publication boundary", () => {
  it("does not publish or link owner-pending policy placeholders", () => {
    expect(approvedPolicies()).toEqual([]);
    expect(approvedPolicy("privacy")).toBeUndefined();
    render(<SiteFooter />);
    expect(screen.queryByRole("navigation", { name: "Policies" })).not.toBeInTheDocument();
    expect(screen.queryByText("Policy documents appear only after accountable owner approval."))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /credits/i })).not.toBeInTheDocument();
  });
});
