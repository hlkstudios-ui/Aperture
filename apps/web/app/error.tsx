"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="route-error" role="alert">
    <p className="eyebrow">The projector stopped</p>
    <h1>We couldn’t load this page.</h1>
    <p>Your account and selections are safe. Try loading the page again.</p>
    <button type="button" onClick={reset}>Try again</button>
  </main>;
}
