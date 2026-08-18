"use client";

import { useMemo, useState } from "react";

export type RelationshipGraphData = {
  nodes: Array<{ id: string; label: string; entity_type: string; current_character: boolean; first_reveal_seconds: number }>;
  edges: Array<{ id: string; source: string; target: string; label: string; reveal_seconds: number }>;
  effective_cutoff: number;
};

function at(value: number) {
  return `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, "0")}`;
}

export function RelationshipGraph({ data }: { data: RelationshipGraphData }) {
  const [zoom, setZoom] = useState(1);
  const positions = useMemo(() => new Map(data.nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(data.nodes.length, 1) - Math.PI / 2;
    return [node.id, { x: 200 + Math.cos(angle) * 135, y: 130 + Math.sin(angle) * 88 }];
  })), [data.nodes]);
  if (!data.nodes.length || !data.edges.length) return <p>No approved relationships are available at this timestamp.</p>;
  return <div className="relationship-graph">
    <div className="graph-controls" aria-label="Relationship graph zoom controls">
      <button aria-label="Zoom relationship graph out" disabled={zoom <= .75} onClick={() => setZoom((value) => Math.max(.75, value - .25))}>−</button>
      <span aria-live="polite">{Math.round(zoom * 100)}%</span>
      <button aria-label="Zoom relationship graph in" disabled={zoom >= 2} onClick={() => setZoom((value) => Math.min(2, value + .25))}>+</button>
    </div>
    <div className="graph-viewport" tabIndex={0} aria-label="Scrollable relationship graph">
      <svg role="img" aria-labelledby="relationship-graph-title relationship-graph-description" viewBox="0 0 400 260" style={{ width: `${zoom * 100}%` }}>
        <title id="relationship-graph-title">Spoiler-safe relationship graph</title>
        <desc id="relationship-graph-description">Known relationships through {at(data.effective_cutoff)}. Current characters use emphasized nodes.</desc>
        {data.edges.map((edge) => {
          const source = positions.get(edge.source); const target = positions.get(edge.target);
          if (!source || !target) return null;
          return <g key={edge.id}><line x1={source.x} y1={source.y} x2={target.x} y2={target.y} /><text className="edge-label" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>{edge.label}</text></g>;
        })}
        {data.nodes.map((node) => { const point = positions.get(node.id)!; return <g key={node.id} className={node.current_character ? "current" : ""}><circle cx={point.x} cy={point.y} r={node.current_character ? 29 : 25} /><text x={point.x} y={point.y + 4} textAnchor="middle">{node.label}</text>{node.current_character ? <title>{node.label}, current character</title> : null}</g>; })}
      </svg>
    </div>
    <details><summary>Accessible relationship list</summary><ul>{data.edges.map((edge) => {
      const source = data.nodes.find((node) => node.id === edge.source); const target = data.nodes.find((node) => node.id === edge.target);
      return <li key={edge.id}><span><strong>{source?.label}</strong> {edge.label} <strong>{target?.label}</strong> · known at {at(edge.reveal_seconds)}{source?.current_character || target?.current_character ? " · involves a current character" : ""}</span></li>;
    })}</ul></details>
  </div>;
}
