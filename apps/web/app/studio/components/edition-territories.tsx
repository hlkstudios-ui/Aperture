import { updateEditionTerritoriesAction } from "@/app/studio/actions";

export type EditionRights = {
  id: string;
  movie_id: string | null;
  name: string;
  allowed_territories: string[];
};

export function EditionTerritories({ editions }: { editions: EditionRights[] }) {
  if (!editions.length) return null;
  return (
    <section className="studio-editor-section">
      <div className="form-section-heading">
        <div>
          <p className="eyebrow">Edition overrides</p>
          <h2>Cut-specific territories</h2>
        </div>
      </div>
      <p className="field-hint">
        Each playable edition must independently permit the viewer territory.
        Blank means the edition itself is global; title rights still apply.
      </p>
      {editions.map((edition) => (
        <form
          className="homepage-rail-form"
          action={updateEditionTerritoriesAction.bind(null, edition.id)}
          key={edition.id}
        >
          <label>
            {edition.name}
            <input
              name="allowed_territories"
              defaultValue={edition.allowed_territories.join(", ")}
              placeholder="CA, US"
            />
          </label>
          <button type="submit">Save edition rights</button>
        </form>
      ))}
    </section>
  );
}
