"use client";

import { useEffect } from "react";
import styles from "./domains.module.css";

export default function DomainsError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("Studio domains route failed", error);
  }, [error]);
  return <main className={styles.routeState} role="alert">
    <span className={styles.errorMark} aria-hidden="true">!</span>
    <h1>Domains could not be loaded</h1>
    <p>No routing settings were changed. Try loading this owner-only workspace again.</p>
    <button className="studio-primary" onClick={retry} type="button">Try again</button>
  </main>;
}
