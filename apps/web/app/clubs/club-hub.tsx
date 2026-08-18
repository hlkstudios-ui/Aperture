"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
const api = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
type Movie = { id: string; title: string };
type Club = {
  id: string;
  name: string;
  description: string;
  role: string;
  invite_token: string | null;
  members: Array<{ profile_id: string; name: string; role: string }>;
  scheduled_watches: Array<{
    id: string;
    title: string;
    scheduled_at: string;
    status: string;
  }>;
  polls: Array<{
    id: string;
    question: string;
    options: Array<{ id: string; label: string; votes: number }>;
  }>;
  discussion: Array<{
    id: string;
    profile_name: string;
    body: string;
    contains_spoilers: boolean;
  }>;
};
async function request<T>(path: string, init?: RequestInit) {
  const response = await fetch(`${api}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => null))?.detail ?? "Club action failed",
    );
  return response.json() as Promise<T>;
}
export function ClubHub({
  initial,
  movies,
  watchPartiesEnabled,
}: {
  initial: Club[];
  movies: Movie[];
  watchPartiesEnabled: boolean;
}) {
  const router = useRouter();
  const [clubs, setClubs] = useState(initial);
  const [selected, setSelected] = useState(initial[0]?.id ?? "");
  const [notice, setNotice] = useState("");
  const club = clubs.find((x) => x.id === selected);
  const replace = (next: Club) => {
    setClubs((all) => [next, ...all.filter((x) => x.id !== next.id)]);
    setSelected(next.id);
  };
  const submit = async (
    event: FormEvent<HTMLFormElement>,
    path: string,
    body: (form: FormData) => object,
  ) => {
    event.preventDefault();
    try {
      replace(
        await request<Club>(path, {
          method: "POST",
          body: JSON.stringify(body(new FormData(event.currentTarget))),
        }),
      );
      setNotice("Saved.");
    } catch (error) {
      setNotice((error as Error).message);
    }
  };
  const createParty = async (id: string) => {
    try {
      const party = await request<{ id: string; access_token: string }>(
        `/clubs/${selected}/parties`,
        { method: "POST", body: JSON.stringify({ scheduled_watch_id: id }) },
      );
      sessionStorage.setItem(`party:${party.id}`, party.access_token);
      router.push(`/clubs/parties/${party.id}`);
    } catch (error) {
      setNotice((error as Error).message);
    }
  };
  return (
    <div className="club-layout">
      <section className="editor-panel">
        <h2>Create or join</h2>
        <form
          onSubmit={(e) =>
            void submit(e, "/clubs", (f) => ({
              name: f.get("name"),
              description: f.get("description"),
            }))
          }
        >
          <label>
            Club name
            <input name="name" required />
          </label>
          <label>
            Description
            <textarea name="description" />
          </label>
          <button className="primary">Create private club</button>
        </form>
        <form
          onSubmit={(e) =>
            void submit(e, "/clubs/join", (f) => ({
              invite_token: f.get("invite"),
            }))
          }
        >
          <label>
            Invitation token
            <input name="invite" required />
          </label>
          <button className="secondary">Join club</button>
        </form>
        <label>
          Your clubs
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choose a club</option>
            {clubs.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </label>
        {notice && <p role="status">{notice}</p>}
      </section>
      {club && (
        <section className="club-workspace">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{club.role}</p>
              <h2>{club.name}</h2>
              <p>{club.description}</p>
            </div>
          </div>
          {club.invite_token && (
            <div className="invite-token">
              <strong>Private invitation token</strong>
              <code>{club.invite_token}</code>
              <small>Share only with intended members.</small>
            </div>
          )}
          <div className="club-columns">
            <article>
              <h3>Members</h3>
              <ul>
                {club.members.map((x) => (
                  <li key={x.profile_id}>
                    {x.name}
                    <small>{x.role}</small>
                  </li>
                ))}
              </ul>
            </article>
            <article>
              <h3>Schedule a film</h3>
              <form
                onSubmit={(e) =>
                  void submit(e, `/clubs/${club.id}/schedule`, (f) => ({
                    movie_id: f.get("movie_id"),
                    title: f.get("title"),
                    scheduled_at: new Date(
                      String(f.get("scheduled_at")),
                    ).toISOString(),
                  }))
                }
              >
                <label>
                  Film
                  <select name="movie_id">
                    {movies.map((x) => (
                      <option value={x.id} key={x.id}>
                        {x.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Event title
                  <input name="title" required />
                </label>
                <label>
                  Local date and time
                  <input type="datetime-local" name="scheduled_at" required />
                </label>
                <button className="primary">Schedule</button>
              </form>
            </article>
          </div>
          <div className="club-columns">
            <article>
              <h3>Scheduled watches</h3>
              {club.scheduled_watches.map((x) => (
                <div className="club-row" key={x.id}>
                  <span>
                    <strong>{x.title}</strong>
                    <small>{new Date(x.scheduled_at).toLocaleString()}</small>
                  </span>
                    {watchPartiesEnabled && club.role !== "member" && (
                    <button onClick={() => void createParty(x.id)}>
                      Start party
                    </button>
                  )}
                </div>
              ))}
            </article>
            <article>
              <h3>Start a poll</h3>
              <form
                onSubmit={(e) =>
                  void submit(e, `/clubs/${club.id}/polls`, (f) => ({
                    question: f.get("question"),
                    options: [
                      { label: f.get("first") },
                      { label: f.get("second") },
                    ],
                  }))
                }
              >
                <label>
                  Question
                  <input name="question" required />
                </label>
                <label>
                  Option one
                  <input name="first" required />
                </label>
                <label>
                  Option two
                  <input name="second" required />
                </label>
                <button>Publish poll</button>
              </form>
              {club.polls.map((p) => (
                <div key={p.id}>
                  <strong>{p.question}</strong>
                  {p.options.map((o) => (
                    <button
                      key={o.id}
                      onClick={async () =>
                        replace(
                          await request<Club>(
                            `/clubs/${club.id}/polls/${p.id}/vote`,
                            {
                              method: "PUT",
                              body: JSON.stringify({ option_id: o.id }),
                            },
                          ),
                        )
                      }
                    >
                      {o.label} · {o.votes}
                    </button>
                  ))}
                </div>
              ))}
            </article>
          </div>
          <article className="editor-panel">
            <h3>Private discussion</h3>
            <form
              onSubmit={(e) =>
                void submit(e, `/clubs/${club.id}/discussion`, (f) => ({
                  body: f.get("body"),
                  contains_spoilers: f.get("spoilers") === "on",
                }))
              }
            >
              <label>
                Message
                <textarea name="body" required />
              </label>
              <label className="check-line">
                <input type="checkbox" name="spoilers" /> Contains spoilers
              </label>
              <button>Post</button>
            </form>
            {club.discussion.map((p) => (
              <div className="club-post" key={p.id}>
                <strong>{p.profile_name}</strong>
                {p.contains_spoilers ? (
                  <details>
                    <summary>Spoiler — reveal</summary>
                    <p>{p.body}</p>
                  </details>
                ) : (
                  <p>{p.body}</p>
                )}
              </div>
            ))}
          </article>
        </section>
      )}
    </div>
  );
}
