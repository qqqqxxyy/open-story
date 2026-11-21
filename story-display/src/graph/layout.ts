import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { Story } from '../model/types.ts';

export function layoutStory(story: Story): { nodes: Node[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: 'LR', nodesep: 42, ranksep: 110, marginx: 45, marginy: 45 });
  for (const chapter of story.chapters) graph.setNode(chapter.id, {width: 238, height: 148});
  for (const edge of story.graph.edges) graph.setEdge(edge.from, edge.to);
  dagre.layout(graph);
  const nodes: Node[] = story.chapters.map(chapter => {
    const p = graph.node(chapter.id);
    return { id: chapter.id, type: 'chapter', position: {x: 45 + chapter.timelineOrder * 348, y: p.y - 74},
      data: { chapter, entry: story.graph.entryNodeIds.includes(chapter.id),
        outgoing: story.graph.edges.filter(e => e.from === chapter.id).length,
        incoming: story.graph.edges.filter(e => e.to === chapter.id).length },
    };
  });
  const edges: Edge[] = story.graph.edges.map(edge => {
    const from = story.chapters.find(chapter => chapter.id === edge.from)!;
    const to = story.chapters.find(chapter => chapter.id === edge.to)!;
    const backward = to.timelineOrder <= from.timelineOrder;
    return { id: edge.id, source: edge.from, target: edge.to, label: edge.label,
      type: edge.from === edge.to ? 'selfLoop' : 'default', markerEnd: {type: MarkerType.ArrowClosed, color: '#b5afa2', width: 17, height: 17},
      style: {stroke: '#b5afa2', strokeWidth: 1.5, ...(backward ? {strokeDasharray: '6 5'} : {})},
      labelStyle: {fontSize: 11, fill: '#746b59'}, labelBgStyle: {fill: '#f8f6f0'},
    };
  });
  return {nodes, edges};
}
