import styles from "./domains.module.css";

export default function DomainsLoading() {
  return <main className={styles.routeState} aria-busy="true" aria-live="polite">
    <span className={styles.loadingMark} aria-hidden="true" />
    <p>Loading domain connections…</p>
    <div className={styles.loadingCards} aria-hidden="true"><i /><i /><i /></div>
  </main>;
}
