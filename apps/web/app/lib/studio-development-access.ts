const STUDIO_ROOT = "/studio";
const STUDIO_LOGIN = "/studio/login";
const STUDIO_DEV_ACCESS = "/studio/dev-access";

export function studioDevelopmentAccessEnabled(
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  return (
    env.NODE_ENV === "development" &&
    env.APP_ENV === "development" &&
    env.STUDIO_DEV_AUTO_LOGIN === "true"
  );
}

export function safeStudioDestination(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return STUDIO_ROOT;

  try {
    const destination = new URL(value, "http://studio.local");
    const path = destination.pathname;
    const isStudioPath = path === STUDIO_ROOT || path.startsWith(`${STUDIO_ROOT}/`);
    const createsBootstrapLoop =
      path === STUDIO_LOGIN ||
      path.startsWith(`${STUDIO_LOGIN}/`) ||
      path === STUDIO_DEV_ACCESS ||
      path.startsWith(`${STUDIO_DEV_ACCESS}/`);

    if (!isStudioPath || createsBootstrapLoop) return STUDIO_ROOT;
    return `${path}${destination.search}`;
  } catch {
    return STUDIO_ROOT;
  }
}

export function studioDevelopmentAccessPath(next: string | null | undefined): string {
  const params = new URLSearchParams({ next: safeStudioDestination(next) });
  return `${STUDIO_DEV_ACCESS}?${params.toString()}`;
}
