import { render, screen } from "@testing-library/react";
import { CatalogCard, type CatalogCardModel } from "@/app/components/catalog-card";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={String(href)} {...props}>{children}</a> }));

const item: CatalogCardModel = {
  href: "/movies/example",
  title: "Example Film",
  kind: "movie",
  posterUrl: "https://image.tmdb.org/t/p/w342/example.jpg",
  description: "A disciplined story hook that belongs outside the poster artwork.",
  primaryMeta: "2026",
  secondaryMeta: "2h 14m · PG-13",
  genres: ["Drama", "Thriller"],
};

describe("CatalogCard", () => {
  it("renders the compact decision hierarchy without covering the artwork", () => {
    const { container } = render(<CatalogCard density="compact" item={item} />);
    expect(screen.getByRole("link", { name: "View Example Film" })).toHaveAttribute("href", "/movies/example");
    expect(screen.getByText("2026")).toBeInTheDocument();
    expect(screen.getByText("Drama · Thriller")).toBeInTheDocument();
    expect(screen.getByText("2h 14m · PG-13")).toBeInTheDocument();
    expect(screen.queryByText(item.description as string)).not.toBeInTheDocument();
    expect(container.querySelector(".card-art")?.textContent).toBe("");
  });

  it("adds a synopsis only in the detailed footer", () => {
    render(<CatalogCard density="detailed" item={item} />);
    expect(screen.getByText(item.description as string)).toHaveClass("catalog-card__description");
  });
});
