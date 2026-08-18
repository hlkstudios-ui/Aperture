"use client";
import { useActionState } from "react";
import type { NamedRecord, Season } from "@/app/lib/catalog";
import {
  addEpisodeAction,
  addSeasonAction,
  bulkEpisodesAction,
  createSeriesAction,
  updateSeriesTerritoriesAction,
} from "@/app/studio/actions";
import { initialFormState } from "./form-state";
import { SubmitButton } from "./form-status";

function State({ state }: { state: { error: string; success?: string } }) {
  return (
    <>
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
    </>
  );
}
export function SeriesCreateForm({ genres }: { genres: NamedRecord[] }) {
  const [state, action] = useActionState(createSeriesAction, initialFormState);
  return (
    <form className="studio-form" action={action}>
      <section>
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Series metadata</p>
            <h2>Create the series container</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Title *<input name="title" required />
          </label>
          <label>
            URL slug *
            <input name="slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" />
          </label>
          <label>
            Release date
            <input name="release_date" type="date" />
          </label>
          <label>
            Certification
            <input name="maturity_rating" />
          </label>
          <label className="span-2">
            Licensed viewer territories
            <input
              name="allowed_territories"
              placeholder="CA, US (leave blank for global rights)"
            />
          </label>
          <label className="span-2">
            Short description *
            <textarea name="short_description" required maxLength={500} />
          </label>
          <label className="span-2">
            Synopsis *<textarea name="synopsis" required rows={7} />
          </label>
        </div>
        <fieldset>
          <legend>Genres</legend>
          <div className="check-grid">
            {genres.map((item) => (
              <label key={item.id}>
                <input type="checkbox" name="genre_ids" value={item.id} />
                {item.name}
              </label>
            ))}
          </div>
        </fieldset>
      </section>
      <State state={state} />
      <div className="sticky-actions">
        <SubmitButton>Create draft series</SubmitButton>
      </div>
    </form>
  );
}
export function SeriesTerritoriesForm({
  seriesId,
  territories,
}: {
  seriesId: string;
  territories: string[];
}) {
  const [state, action] = useActionState(
    updateSeriesTerritoriesAction.bind(null, seriesId),
    initialFormState,
  );
  return (
    <section className="studio-editor-section">
      <div className="form-section-heading">
        <div>
          <p className="eyebrow">Distribution</p>
          <h2>Licensed viewer territories</h2>
        </div>
      </div>
      <form className="studio-form compact-form" action={action}>
        <label>
          ISO country allowlist
          <input
            name="allowed_territories"
            defaultValue={territories.join(", ")}
            placeholder="CA, US (leave blank for global rights)"
          />
        </label>
        <p className="field-hint">
          Blank means globally licensed. Production country metadata is separate.
        </p>
        <State state={state} />
        <SubmitButton>Save territories</SubmitButton>
      </form>
    </section>
  );
}
export function SeasonForm({
  seriesId,
  nextNumber,
}: {
  seriesId: string;
  nextNumber: number;
}) {
  const [state, action] = useActionState(
    addSeasonAction.bind(null, seriesId),
    initialFormState,
  );
  return (
    <form className="studio-form compact-form" action={action}>
      <div className="form-grid">
        <label>
          Season number
          <input
            name="number"
            type="number"
            min="0"
            defaultValue={nextNumber}
            required
          />
        </label>
        <label>
          Title
          <input name="title" />
        </label>
        <label className="span-2">
          Synopsis
          <textarea name="synopsis" rows={3} />
        </label>
      </div>
      <State state={state} />
      <SubmitButton>Create season</SubmitButton>
    </form>
  );
}
export function EpisodeForm({
  seriesId,
  seasons,
}: {
  seriesId: string;
  seasons: Season[];
}) {
  const [state, action] = useActionState(
    addEpisodeAction.bind(null, seriesId),
    initialFormState,
  );
  return (
    <form className="studio-form compact-form" action={action}>
      <div className="form-grid">
        <label>
          Season
          <select name="season_id" required>
            {seasons.map((item) => (
              <option value={item.id} key={item.id}>
                Season {item.number}
              </option>
            ))}
          </select>
        </label>
        <label>
          Episode number
          <input name="number" type="number" min="0" required />
        </label>
        <label>
          Title
          <input name="title" required />
        </label>
        <label>
          Runtime (minutes)
          <input name="runtime_minutes" type="number" min="1" required />
        </label>
        <label className="span-2">
          Synopsis
          <textarea name="synopsis" required rows={3} />
        </label>
        <label>
          Release date
          <input name="release_date" type="date" />
        </label>
      </div>
      <State state={state} />
      <SubmitButton>Create episode</SubmitButton>
    </form>
  );
}
export function BulkEpisodeForm({
  seriesId,
  seasons,
}: {
  seriesId: string;
  seasons: Season[];
}) {
  const [state, action] = useActionState(
    bulkEpisodesAction.bind(null, seriesId),
    initialFormState,
  );
  return (
    <form className="studio-form compact-form" action={action}>
      <label>
        Season
        <select name="season_id" required>
          {seasons.map((item) => (
            <option value={item.id} key={item.id}>
              Season {item.number}
            </option>
          ))}
        </select>
      </label>
      <label>
        Episode rows
        <textarea
          name="episodes"
          rows={7}
          placeholder={
            "1 | Pilot | 42 | Episode synopsis\n2 | Second Light | 44 | Episode synopsis"
          }
          required
        />
      </label>
      <p className="field-hint">
        One row per episode: number | title | runtime minutes | synopsis. Rows
        are validated and created in order.
      </p>
      <State state={state} />
      <SubmitButton>Create episode batch</SubmitButton>
    </form>
  );
}
