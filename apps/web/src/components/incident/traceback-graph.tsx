"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Edge,
  MarkerType,
  Node,
  Position,
  ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";
import { GraphEdge, GraphNode } from "@/lib/types";

const NODE_TYPES = {};
const EDGE_TYPES = {};

function layoutNodes(nodes: GraphNode[], edges: GraphEdge[]): Node[] {
  const incoming = new Map<string, number>();
  nodes.forEach((n) => incoming.set(n.id, 0));
  edges.forEach((e) => incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1));

  const level = new Map<string, number>();
  const roots = nodes.filter((n) => (incoming.get(n.id) ?? 0) === 0);
  roots.forEach((r) => level.set(r.id, 0));

  const adjacency = new Map<string, string[]>();
  edges.forEach((e) => {
    adjacency.set(e.source, [...(adjacency.get(e.source) ?? []), e.target]);
  });

  const queue = [...roots.map((r) => r.id)];
  while (queue.length) {
    const current = queue.shift()!;
    const currentLevel = level.get(current) ?? 0;
    for (const next of adjacency.get(current) ?? []) {
      const candidate = currentLevel + 1;
      if (level.get(next) === undefined || candidate > (level.get(next) ?? 0)) {
        level.set(next, candidate);
        queue.push(next);
      }
    }
  }

  const columns = new Map<number, string[]>();
  nodes.forEach((n) => {
    const lvl = level.get(n.id) ?? 0;
    columns.set(lvl, [...(columns.get(lvl) ?? []), n.id]);
  });

  return nodes.map((n) => {
    const lvl = level.get(n.id) ?? 0;
    const col = columns.get(lvl) ?? [];
    const idx = col.indexOf(n.id);
    const offset = (col.length - 1) / 2;

    return {
      id: n.id,
      data: { label: n.label },
      position: { x: lvl * 240, y: (idx - offset) * 110 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: n.failing
        ? {
            background: "oklch(0.27 0.1 25)",
            border: "1px solid oklch(0.65 0.2 25)",
            color: "oklch(0.9 0.05 25)",
            borderRadius: 10,
            padding: "10px 14px",
            fontSize: 12,
            fontWeight: 600,
            width: 180,
            boxShadow: "0 0 0 4px oklch(0.65 0.2 25 / 15%)",
          }
        : {
            background: "oklch(0.24 0 0)",
            border: "1px solid oklch(1 0 0 / 12%)",
            color: "oklch(0.9 0 0)",
            borderRadius: 10,
            padding: "10px 14px",
            fontSize: 12,
            fontWeight: 500,
            width: 180,
          },
    };
  });
}

export function TracebackGraph({
  nodes,
  edges,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}) {
  const flowNodes = useMemo(() => layoutNodes(nodes, edges), [nodes, edges]);

  const flowEdges: Edge[] = useMemo(
    () =>
      edges.map((e) => {
        const targetFailing = nodes.find((n) => n.id === e.target)?.failing;
        const sourceFailing = nodes.find((n) => n.id === e.source)?.failing;
        const isBlastPath = targetFailing || sourceFailing;
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: Boolean(isBlastPath),
          style: {
            stroke: isBlastPath ? "oklch(0.65 0.2 25)" : "oklch(1 0 0 / 25%)",
            strokeWidth: isBlastPath ? 2 : 1,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: isBlastPath ? "oklch(0.65 0.2 25)" : "oklch(1 0 0 / 40%)",
          },
        };
      }),
    [edges, nodes]
  );

  function handleInit(instance: ReactFlowInstance) {
    // The flex/grid parent settles its height a frame after mount, so the
    // fitView prop's initial measurement can run against a stale (0px)
    // container. Re-fit once layout has actually stabilized.
    requestAnimationFrame(() => instance.fitView({ padding: 0.3 }));
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onInit={handleInit}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnDrag
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="oklch(1 0 0 / 8%)" />
      </ReactFlow>
    </div>
  );
}
