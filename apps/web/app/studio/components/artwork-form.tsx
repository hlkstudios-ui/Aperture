"use client";
import { useActionState } from "react";
import { addArtworkAction } from "@/app/studio/actions";
import { initialFormState } from "./form-state";
import { SubmitButton } from "./form-status";
export function ArtworkForm({ movieId }: { movieId: string }) {
  const [state, action] = useActionState(
    addArtworkAction.bind(null, movieId),
    initialFormState,
  );
  return (
    <form className="studio-form compact-form" action={action}>
      <div className="form-grid">
        <label>
          Artwork type
          <select name="kind" defaultValue="poster">
            <option value="poster">Poster</option>
            <option value="landscape">Landscape card</option>
            <option value="backdrop">Hero backdrop</option>
            <option value="logo">Title logo</option>
            <option value="mobile">Mobile</option>
            <option value="still">Still</option>
          </select>
        </label>
        <label>
          Storage key *
          <input
            name="storage_key"
            required
            placeholder="catalog/movie/poster.webp"
          />
        </label>
        <label className="span-2">
          Accessible alt text *
          <input name="alt_text" required maxLength={500} />
        </label>
        <label>
          Width
          <input name="width" type="number" min="1" />
        </label>
        <label>
          Height
          <input name="height" type="number" min="1" />
        </label>
      </div>
      <p className="field-hint">
        This references an already-authorized object. File upload arrives in the
        dedicated upload phase.
      </p>
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
      <SubmitButton>Add artwork reference</SubmitButton>
    </form>
  );
}
