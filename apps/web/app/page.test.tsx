import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import Home from "./page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}));

const movie = { id:"movie-1",title:"The Lantern Sea",slug:"the-lantern-sea",original_title:null,short_description:"A cartographer follows a light.",synopsis:"Original demo.",release_date:"2026-08-15",runtime_minutes:104,maturity_rating:"PG",status:"published",original_language_code:"en",country_code:"CA",franchise_id:null,genres:[],themes:[],tags:[],created_at:"2026-08-15",updated_at:"2026-08-15" };

it("renders backend catalog data and primary navigation", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    const body = url.includes("/homepage")
      ? { hero: null, rails: [], published_at: null }
      : url.includes("/movies") ? [movie] : [];
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  render(await Home());
  expect(screen.getByRole("heading", { level: 1, name: "The Lantern Sea" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View film" })).toHaveAttribute("href", "/movies/the-lantern-sea");
  fireEvent.click(screen.getByRole("button", { name: "Profile and account" }));
  expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});
