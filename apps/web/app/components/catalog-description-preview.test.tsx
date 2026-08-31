import { act, fireEvent, render, screen } from "@testing-library/react";
import { CatalogDescriptionPreview } from "@/app/components/catalog-description-preview";

describe("CatalogDescriptionPreview",()=>{
  afterEach(()=>vi.useRealTimers());

  it("opens the full cinematic synopsis only after 1.25 seconds",()=>{
    vi.useFakeTimers();
    render(<CatalogDescriptionPreview title="The Last House" description="The complete synopsis belongs in the delayed preview."/>);
    fireEvent.mouseEnter(screen.getByText("The complete synopsis belongs in the delayed preview."));
    act(()=>vi.advanceTimersByTime(1249));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    act(()=>vi.advanceTimersByTime(1));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Full synopsis");
    expect(screen.getByRole("tooltip")).toHaveTextContent("The Last House");
    expect(screen.getByRole("tooltip")).toHaveTextContent("The complete synopsis belongs in the delayed preview.");
  });

  it("cancels a pending preview when the pointer leaves",()=>{
    vi.useFakeTimers();
    render(<CatalogDescriptionPreview title="Example" description="A complete description."/>);
    const description=screen.getByText("A complete description.");
    fireEvent.mouseEnter(description);
    fireEvent.mouseLeave(description);
    act(()=>vi.advanceTimersByTime(1300));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
