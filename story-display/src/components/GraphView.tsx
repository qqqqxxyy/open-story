import { useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, Handle, Position,
  useNodesState, useReactFlow, BaseEdge, EdgeLabelRenderer } from '@xyflow/react';
import type { NodeProps, EdgeProps } from '@xyflow/react';
import type { Story, Chapter } from '../model/types.ts';
import { layoutStory } from '../graph/layout.ts';

function ChapterNode({data, selected}: NodeProps) {
  const chapter = data.chapter as Chapter;
  return <div className={`chapter-card ${selected ? 'is-selected' : ''} ${data.unread?'is-unread':''}`}>
    <Handle type="target" position={Position.Left}/>
    <div className="card-top"><span className="chapter-number">{String(chapter.turn).padStart(2,'0')}</span>
      {Boolean(data.unread) && <span className="update-tag">新</span>}
      {data.entry ? <span className="small-tag">故事起点</span> : Number(data.outgoing) > 1 ? <span className="small-tag branch">剧情分岔</span> : Number(data.incoming) > 1 ? <span className="small-tag">剧情汇合</span> : null}
      <span className="card-dot"/>
    </div>
    <div className="card-title">{chapter.summary || chapter.title || `第 ${chapter.turn} 幕`}</div>
    <div className="card-bottom"><span>⌖ {chapter.location || '未标注地点'}</span><span>{Number(data.outgoing) > 0 ? `${data.outgoing} 条后续` : '待续'}</span></div>
    <Handle type="source" position={Position.Right}/>
  </div>;
}
function SelfLoop({sourceX, sourceY, targetX, targetY, markerEnd, style, label}: EdgeProps) {
  const x = (sourceX + targetX) / 2, y = Math.min(sourceY, targetY) - 115;
  return <><BaseEdge path={`M ${sourceX},${sourceY} C ${sourceX+95},${y} ${targetX-95},${y} ${targetX},${targetY}`} markerEnd={markerEnd} style={style}/>
    {label && <EdgeLabelRenderer><div className="self-label" style={{transform:`translate(-50%, -50%) translate(${x}px,${y+30}px)`}}>{label}</div></EdgeLabelRenderer>}</>;
}
const nodeTypes = {chapter: ChapterNode}; const edgeTypes = {selfLoop: SelfLoop};
interface Props {story: Story; selectedId: string; onSelect: (id: string) => void; matches: Set<string> | null; unread:Set<string>}
function Canvas({story, selectedId, onSelect, matches, unread}: Props) {
  const initial = useMemo(() => layoutStory(story), [story]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [focus, setFocus] = useState(false);
  const flow = useReactFlow();
  const previousSelection = useRef(selectedId);
  const initialFocus = useRef([{id:selectedId}, ...story.graph.edges.filter(e => e.from===selectedId && e.to!==selectedId).slice(0,2).map(e=>({id:e.to}))]);
  useEffect(() => {
    if (previousSelection.current === selectedId) return;
    previousSelection.current = selectedId;
    const node = flow.getNode(selectedId);
    if (node) void flow.setCenter(node.position.x+119,node.position.y+74,{zoom:Math.max(flow.getZoom(),0.85),duration:300});
  },[selectedId,flow]);
  const neighbors = useMemo(() => new Set([selectedId, ...story.graph.edges.filter(e => e.from === selectedId || e.to === selectedId).flatMap(e => [e.from, e.to])]), [story, selectedId]);
  useEffect(() => { setNodes(current => current.map(node => ({...node, selected: node.id === selectedId,
    data:{...node.data,unread:unread.has(node.id)},
    style: {opacity: (focus && !neighbors.has(node.id)) || (matches && !matches.has(node.id) && node.id !== selectedId) ? 0.22 : 1},
  }))); }, [selectedId, focus, matches, neighbors, setNodes, unread]);
  const edges = initial.edges.map(edge => {
    const active = edge.source === selectedId || edge.target === selectedId;
    return {...edge, style: {...edge.style, stroke: active ? '#ad6745' : '#b5afa2', strokeWidth: active ? 2 : 1.5, opacity: focus && !active ? 0.13 : 1}};
  });
  function locate() { void flow.fitView({nodes:[{id:selectedId}], maxZoom:1, duration:350, padding:0.7}); }
  return <div className="graph-shell">
    <div className="canvas-top"><div><span className="eyebrow">STORY ATLAS</span><h2>每一次选择，都有去向。</h2></div>
      <div className="canvas-actions"><button onClick={locate} title="定位当前章节">⌖ 定位</button><button className={focus?'active':''} onClick={() => setFocus(!focus)}>相邻剧情</button></div>
    </div>
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange}
      onNodeClick={(_,node) => onSelect(node.id)} fitView fitViewOptions={{nodes:initialFocus.current,maxZoom:1, padding:0.12}}
      minZoom={0.06} maxZoom={1.6} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      aria-label="故事章节拓扑图">
      <Background color="#d5cfbf" gap={22} size={1}/><Controls showInteractive={false}/>
      <MiniMap nodeColor={node => node.id === selectedId ? '#a56143' : '#d9d1bf'} maskColor="rgba(248,246,240,.7)" pannable zoomable/>
    </ReactFlow>
    <div className="canvas-bottom"><span><i className="legend-dot"/> 时间切片 <span className="legend-line">⟶</span> 故事时间 <span className="muted">从左到右按叙事时间排列</span></span>
      <button onClick={() => { setNodes(initial.nodes.map(n => ({...n, selected:n.id===selectedId,data:{...n.data,unread:unread.has(n.id)}}))); setFocus(false); requestAnimationFrame(() => { void flow.fitView({duration:300,maxZoom:0.9}); }); }}>↻ 重新排布</button>
    </div>
  </div>;
}
export function GraphView(props: Props) { return <ReactFlowProvider><Canvas {...props}/></ReactFlowProvider>; }
