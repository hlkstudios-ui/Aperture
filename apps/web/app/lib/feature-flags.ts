function enabled(value: string | undefined): boolean {
  return value === undefined || value.toLowerCase() === "true";
}

export const featureFlags = {
  sceneLens: enabled(process.env.NEXT_PUBLIC_FEATURE_SCENE_LENS_ENABLED),
  askMovie: enabled(process.env.NEXT_PUBLIC_FEATURE_ASK_MOVIE_ENABLED),
  community: enabled(process.env.NEXT_PUBLIC_FEATURE_COMMUNITY_ENABLED),
  watchParties: enabled(process.env.NEXT_PUBLIC_FEATURE_WATCH_PARTIES_ENABLED),
  experimentalRecommendations: enabled(
    process.env.NEXT_PUBLIC_FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED,
  ),
} as const;
