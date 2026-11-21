import { Children, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode, PointerEvent, KeyboardEvent } from 'react';

type Side = 'left' | 'right';
const minimum = {left:180, right:260};
const maximum = {left:520, right:760};
const canvasMinimum = 320;
const gutterWidth = 20;

/** Side panels retain their contents and preferred widths when folded. */
export function SplitWorkspace({children}: {children:ReactNode}) {
  const slots = Children.toArray(children);
  const workspace = useRef<HTMLDivElement>(null);
  const [available,setAvailable] = useState(window.innerWidth);
  const [preferred,setPreferred] = useState(() => window.innerWidth >= 1600 ? {left:270,right:445} : window.innerWidth <= 1150 ? {left:205,right:325} : {left:250,right:390});
  const [folded,setFolded] = useState({left:false,right:false});
  const [dragging,setDragging] = useState<Side|null>(null);
  const drag = useRef<{side:Side;x:number;width:number}|null>(null);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => setAvailable(entry.contentRect.width));
    observer.observe(workspace.current!);
    return () => observer.disconnect();
  },[]);
  let left = folded.left ? 0 : preferred.left;
  let right = folded.right ? 0 : preferred.right;
  const room = Math.max(0,available-canvasMinimum-gutterWidth);
  const leftMinimum = folded.left ? 0 : minimum.left;
  const rightMinimum = folded.right ? 0 : minimum.right;
  const excess = Math.max(0,left+right-room);
  const shrinkable = left-leftMinimum+right-rightMinimum;
  if (excess && shrinkable>0) {
    const ratio = Math.min(1,excess/shrinkable);
    left -= (left-leftMinimum)*ratio;
    right -= (right-rightMinimum)*ratio;
  }
  const sizes = {left:Math.round(left),right:Math.round(right)};
  const mobile = available <= 780;
  function limit(side:Side) {
    return Math.max(minimum[side],Math.min(maximum[side],room-sizes[side==='left'?'right':'left']));
  }
  function resize(side:Side,width:number) {
    const next = Math.max(minimum[side],Math.min(limit(side),width));
    setPreferred(current=>({...current,[side]:next}));
  }
  function start(side:Side,event:PointerEvent<HTMLDivElement>) {
    if (mobile || folded[side] || event.button!==0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current={side,x:event.clientX,width:sizes[side]};setDragging(side);
  }
  function move(event:PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const {side,x,width}=drag.current;
    resize(side,width+(event.clientX-x)*(side==='left'?1:-1));
  }
  function stop() {drag.current=null;setDragging(null);}
  function toggle(side:Side) {stop();setFolded(current=>({...current,[side]:!current[side]}));}
  function keyboard(side:Side,event:KeyboardEvent<HTMLDivElement>) {
    if (event.key==='Enter') {event.preventDefault();toggle(side);return;}
    if (mobile || folded[side]) return;
    let width=sizes[side];
    if(event.key==='ArrowLeft'||event.key==='ArrowRight') width+=(event.key==='ArrowRight'?1:-1)*(side==='left'?1:-1)*(event.shiftKey?40:10);
    else if(event.key==='Home') width=minimum[side];
    else if(event.key==='End') width=limit(side);
    else return;
    event.preventDefault();resize(side,width);
  }
  function divider(side:Side) {
    const name=side==='left'?'故事索引':'章节详情';
    const action=folded[side]?'展开':'折叠';
    return <div className={`panel-divider ${side} ${folded[side]?'is-folded':''}`}>
      <div className="resize-track" role="separator" tabIndex={mobile?-1:0} aria-label={`调整${name}宽度`}
        aria-orientation="vertical" aria-controls={`pane-${side}`} aria-valuemin={folded[side]?0:minimum[side]}
        aria-valuemax={limit(side)} aria-valuenow={sizes[side]} aria-disabled={folded[side]||mobile}
        title="拖动调整宽度；方向键微调；Enter 折叠或展开" onPointerDown={event=>start(side,event)}
        onPointerMove={move} onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={stop}
        onKeyDown={event=>keyboard(side,event)}><span className="resize-grip"/></div>
      <button className="pane-toggle" aria-label={`${action}${name}`} aria-expanded={!folded[side]}
        aria-controls={`pane-${side}`} title={`${action}${name}`} onClick={()=>toggle(side)}>
        <span aria-hidden="true">{(side==='left')!==folded[side]?'‹':'›'}</span><span className="mobile-toggle-label">{action}{name}</span>
      </button>
    </div>;
  }
  return <main ref={workspace} className={`workspace split-workspace ${dragging?'is-resizing':''}`}
    style={{'--left-width':`${sizes.left}px`,'--right-width':`${sizes.right}px`} as CSSProperties}>
    <div id="pane-left" className="side-pane left-pane" hidden={folded.left}>{slots[0]}</div>
    {divider('left')}
    {slots[1]}
    {divider('right')}
    <div id="pane-right" className="side-pane right-pane" hidden={folded.right}>{slots[2]}</div>
  </main>;
}
