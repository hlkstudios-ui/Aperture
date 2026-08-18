import { ContentCard } from "@/app/components/content-card";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, Movie } from "@/app/lib/catalog";

export const metadata = { title: "Movies" };

export default async function MoviesPage(){
  const movies = await catalogFetch<Movie[]>("/catalog/movies?limit=100");
  return <main className="catalog-page"><SiteHeader/><header className="library-heading"><p className="eyebrow">Feature films</p><h1>Movies</h1><p>Distinct worlds, selected with intention.</p></header>{movies.length ? <section className="catalog-grid" aria-label="Published movies">{movies.map(movie=><ContentCard title={movie} kind="movie" key={movie.id}/>)}</section> : <section className="catalog-state compact"><h2>No films are published yet.</h2><p>Check back when the next reel is ready.</p></section>}</main>;
}
