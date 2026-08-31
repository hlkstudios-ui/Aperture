import Link from "next/link";

import type { FilmKnowledgeGraph } from "@/app/lib/catalog";

export function FilmKnowledgeGraphView({ graph }: { graph: FilmKnowledgeGraph }) {
  const root = graph.nodes.find((node) => node.id === graph.root_id);
  const connected = graph.nodes.filter((node) => node.id !== graph.root_id);
  function labels(nodeId: string) {
    return graph.edges
      .filter((edge) => edge.source === nodeId || edge.target === nodeId)
      .map((edge) => edge.label)
      .filter((value, index, values) => values.indexOf(value) === index)
      .join(" · ");
  }
  return <section className="film-universe" aria-labelledby="film-universe-title">
    <p className="eyebrow">Film knowledge graph</p>
    <h2 id="film-universe-title">The universe around {root?.label}</h2>
    <p>Every connection below comes from normalized catalog credits and metadata. Unknown influences are not inferred.</p>
    {connected.length ? <div className="knowledge-node-grid">{connected.map((node) => {
      const content = <><small>{node.kind.replaceAll("_", " ")} · {labels(node.id)}</small><strong>{node.label}</strong>{node.detail ? <span>{node.detail}</span> : null}</>;
      return node.href
        ? <Link key={node.id} href={node.href} className={`knowledge-node ${node.kind}`}>{content}</Link>
        : <article key={node.id} className={`knowledge-node ${node.kind}`}>{content}</article>;
    })}</div> : <p className="empty-inline">Verified connections will appear as catalog metadata is added.</p>}
  </section>;
}
