"use client";
import { useActionState } from "react";
import type { Movie, NamedRecord } from "@/app/lib/catalog";
import { createMovieAction, updateMovieAction } from "@/app/studio/actions";
import { initialFormState } from "./form-state";
import { SubmitButton } from "./form-status";

export function MovieForm({
  movie,
  genres,
  themes,
  tags,
}: {
  movie?: Movie;
  genres: NamedRecord[];
  themes: NamedRecord[];
  tags: NamedRecord[];
}) {
  const action = movie
    ? updateMovieAction.bind(null, movie.id)
    : createMovieAction;
  const [state, formAction] = useActionState(action, initialFormState);
  const selected = (
    items: NamedRecord[],
    current: NamedRecord[] | undefined,
  ) => (
    <div className="check-grid">
      {items.map((item) => (
        <label key={item.id}>
          <input
            type="checkbox"
            name={`${items === genres ? "genre" : items === themes ? "theme" : "tag"}_ids`}
            value={item.id}
            defaultChecked={current?.some((value) => value.id === item.id)}
          />
          {item.name}
        </label>
      ))}
    </div>
  );
  return (
    <form className="studio-form" action={formAction}>
      <section>
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Metadata</p>
            <h2>Identity & discovery</h2>
          </div>
          <span>Required fields marked *</span>
        </div>
        <div className="form-grid">
          <label>
            Title *
            <input
              name="title"
              defaultValue={movie?.title}
              required
              maxLength={250}
            />
          </label>
          <label>
            URL slug *
            <input
              name="slug"
              defaultValue={movie?.slug}
              required
              pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
            />
          </label>
          <label>
            Original title
            <input
              name="original_title"
              defaultValue={movie?.original_title ?? ""}
            />
          </label>
          <label>
            Release date
            <input
              name="release_date"
              type="date"
              defaultValue={movie?.release_date ?? ""}
            />
          </label>
          <label>
            Runtime (minutes) *
            <input
              name="runtime_minutes"
              type="number"
              min="1"
              max="1440"
              defaultValue={movie?.runtime_minutes ?? 90}
              required
            />
          </label>
          <label>
            Certification
            <input
              name="maturity_rating"
              defaultValue={movie?.maturity_rating ?? ""}
              maxLength={32}
            />
          </label>
          <label>
            Original language code
            <input
              name="original_language_code"
              defaultValue={movie?.original_language_code ?? ""}
              placeholder="en"
            />
          </label>
          <label>
            Country code
            <input
              name="country_code"
              defaultValue={movie?.country_code ?? ""}
              placeholder="CA"
              minLength={2}
              maxLength={2}
            />
          </label>
          <label className="span-2">
            Licensed viewer territories
            <input
              name="allowed_territories"
              defaultValue={movie?.allowed_territories.join(", ") ?? ""}
              placeholder="CA, US (leave blank for global rights)"
              aria-describedby="territory-help"
            />
            <small id="territory-help">
              Comma-separated ISO country codes. Blank means globally licensed.
            </small>
          </label>
          <label className="span-2">
            Short description *
            <textarea
              name="short_description"
              required
              maxLength={500}
              rows={2}
              defaultValue={movie?.short_description}
            />
          </label>
          <label className="span-2">
            Full synopsis *
            <textarea
              name="synopsis"
              required
              rows={7}
              defaultValue={movie?.synopsis}
            />
          </label>
        </div>
      </section>
      <section>
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Classification</p>
            <h2>Genres, themes & tags</h2>
          </div>
        </div>
        <fieldset>
          <legend>Genres</legend>
          {selected(genres, movie?.genres)}
        </fieldset>
        <fieldset>
          <legend>Themes</legend>
          {selected(themes, movie?.themes)}
        </fieldset>
        <fieldset>
          <legend>Tags</legend>
          {selected(tags, movie?.tags)}
        </fieldset>
      </section>
      {state.error && (
        <p className="studio-form-error" role="alert">
          {state.error}
        </p>
      )}
      {state.success && (
        <p className="studio-form-success" role="status">
          {state.success}
        </p>
      )}
      <div className="sticky-actions">
        <SubmitButton>
          {movie ? "Save metadata" : "Create draft movie"}
        </SubmitButton>
      </div>
    </form>
  );
}
