const TMDB_PATTERN = /^https:\/\/image\.tmdb\.org\/t\/p\/(?:original|w\d+)\//;

export function optimizedPoster(url: string | null, width: 185 | 342 | 500 = 342): string | null {
  return url?.replace(TMDB_PATTERN, `https://image.tmdb.org/t/p/w${width}/`) ?? null;
}

export function optimizedBackdrop(url: string | null, width: 780 | 1280 = 1280): string | null {
  return url?.replace(TMDB_PATTERN, `https://image.tmdb.org/t/p/w${width}/`) ?? null;
}

export function optimizedStill(url: string | null, width: 300 | 500 = 300): string | null {
  return url?.replace(TMDB_PATTERN, `https://image.tmdb.org/t/p/w${width}/`) ?? null;
}
