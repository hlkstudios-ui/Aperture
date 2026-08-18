export type ClientTitle = { id: string; kind: "movie" | "series"; title: string; href: string; poster_url?: string | null; touched_at: string };
export type ClientProgress = { source_id: string; title: string; subtitle: string | null; position_seconds: number; duration_seconds: number; percentage: number; touched_at: string };
export type ClientLibrary = { viewed: ClientTitle[]; saved: ClientTitle[]; liked: ClientTitle[]; searches: string[]; progress: ClientProgress[] };

const KEY = "aperture-client-library-v1";
const EMPTY: ClientLibrary = { viewed: [], saved: [], liked: [], searches: [], progress: [] };

export function readClientLibrary(): ClientLibrary {
  if (typeof window === "undefined") return EMPTY;
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<ClientLibrary>;
    return { viewed: value.viewed ?? [], saved: value.saved ?? [], liked: value.liked ?? [], searches: value.searches ?? [], progress: value.progress ?? [] };
  } catch { return EMPTY; }
}

function write(value: ClientLibrary) {
  localStorage.setItem(KEY, JSON.stringify(value));
  window.dispatchEvent(new CustomEvent("aperture-library-change"));
}

export function rememberTitle(list: "viewed" | "saved" | "liked", title: Omit<ClientTitle, "touched_at">, enabled = true) {
  const library = readClientLibrary();
  const current = library[list].filter((item) => !(item.id === title.id && item.kind === title.kind));
  library[list] = enabled ? [{ ...title, touched_at: new Date().toISOString() }, ...current].slice(0, 100) : current;
  write(library);
}

export function hasClientTitle(list: "saved" | "liked", id: string, kind: ClientTitle["kind"]) {
  return readClientLibrary()[list].some((item) => item.id === id && item.kind === kind);
}

export function saveClientProgress(progress: Omit<ClientProgress, "touched_at" | "percentage">) {
  const library = readClientLibrary();
  const next = { ...progress, percentage: progress.duration_seconds > 0 ? Math.min(100, progress.position_seconds / progress.duration_seconds * 100) : 0, touched_at: new Date().toISOString() };
  library.progress = [next, ...library.progress.filter((item) => item.source_id !== progress.source_id)].slice(0, 50);
  write(library);
}

export function clientProgress(sourceId: string) {
  return readClientLibrary().progress.find((item) => item.source_id === sourceId) ?? null;
}

export function rememberClientSearch(search: string) {
  const clean = search.trim();
  if (!clean) return;
  const library = readClientLibrary();
  library.searches = [clean, ...library.searches.filter((item) => item.toLocaleLowerCase() !== clean.toLocaleLowerCase())].slice(0, 20);
  write(library);
}

export function clearClientLibrary() { write({ ...EMPTY }); }
