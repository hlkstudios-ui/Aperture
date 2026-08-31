"use client";

import { useId, useMemo, useState } from "react";
import { useFormStatus } from "react-dom";

export type ExploreTitleOption = {
  value: string;
  label: string;
};

function AttachButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button className="secondary" disabled={disabled || pending} type="submit">
      {pending ? "Adding card..." : "Add pinned card"}
    </button>
  );
}

export function ExploreCardPicker({
  options,
  attachAction,
}: {
  options: ExploreTitleOption[];
  attachAction: (form: FormData) => Promise<void>;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const visibleOptions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const matches = normalized
      ? options.filter((option) => option.label.toLocaleLowerCase().includes(normalized))
      : options;
    const selectedOption = options.find((option) => option.value === selected);
    return [
      ...new Map(
        [...(selectedOption ? [selectedOption] : []), ...matches.slice(0, 80)]
          .map((option) => [option.value, option]),
      ).values(),
    ];
  }, [options, query, selected]);
  const hasOptions = options.length > 0;
  const helpId = `${id}-help`;

  return (
    <form action={attachAction} className="explore-card-picker">
      <label className="explore-card-search" htmlFor={`${id}-search`}>
        Search movies and series
        <input
          id={`${id}-search`}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Start typing a catalog title..."
          disabled={!hasOptions}
        />
      </label>
      <label className="explore-card-select" htmlFor={`${id}-title`}>
        Card to pin
        <select
          id={`${id}-title`}
          name="title"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          aria-describedby={helpId}
          disabled={!hasOptions}
          required
        >
          <option value="" disabled>
            {hasOptions ? "Choose a movie or series" : "Every catalog title is already pinned"}
          </option>
          {visibleOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <AttachButton disabled={!hasOptions || !selected} />
      <small className="explore-card-picker-help" id={helpId}>
        Pinned cards lead this view. Its saved filters fill the remaining feed automatically without duplicates.
      </small>
    </form>
  );
}
