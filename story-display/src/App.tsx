import { useEffect, useMemo, useState } from 'react';
import { restoreReadingPosition } from './auto-refresh.ts';
import { acknowledgeUpdate, readingKey, readUpdates, reconcileUpdates, saveUpdates } from './reading-updates.ts';
import type { Story, StoryBundle } from './model/types.ts';
import { GraphView } from './components/GraphView.tsx';
import { ChapterDetail } from './components/ChapterDetail.tsx';
import { SplitWorkspace } from './components/SplitWorkspace.tsx';
import './branch.css';

function firstNode(story: Story, branchId: string) {
  const branch = story.branches.find(item => item.id === branchId);
  return branch?.nodeIds[0] || story.graph.entryNodeIds[0] || story.chapters[0].id;
}

export function App({bundle}: {bundle:StoryBundle}) {
  const hash = new URLSearchParams(location.hash.slice(1));
  const initialStory = bundle.stories.find(story => story.slug === hash.get('story')) || bundle.stories[0];
  const requestedBranch = hash.get('branch');
  const initialBranch = requestedBranch === 'all' || initialStory.branches.some(branch => branch.id === requestedBranch) ? requestedBranch! : initialStory.defaultBranchId;
  const [slug,setSlug] = useState(initialStory.slug);
  const [branchId,setBranchId] = useState(initialBranch);
  const initialChapter=initialStory.chapters.find(chapter=>chapter.id===hash.get('chapter') || chapter.display?.previewId===hash.get('chapter'));
  const [selectedId,setSelectedId] = useState(initialChapter?.id ?? firstNode(initialStory, initialBranch));
  const [updates,setUpdates]=useState(()=>reconcileUpdates(bundle,readUpdates()));
  useEffect(()=>saveUpdates(updates),[updates]);
  const [query,setQuery] = useState('');
  const [showWarnings,setShowWarnings] = useState(false);
  const story = bundle.stories.find(item => item.slug === slug)!;
  const activeBranchId = branchId === 'all' || story.branches.some(branch => branch.id === branchId) ? branchId : story.defaultBranchId;
  const visibleStory = useMemo(() => {
    const branch = story.branches.find(item => item.id === activeBranchId);
    if (!branch) return story;
    const ids = new Set(branch.nodeIds);
    return { ...story, chapters: story.chapters.filter(chapter => ids.has(chapter.id)),
      graph: { ...story.graph, entryNodeIds: story.graph.entryNodeIds.filter(id => ids.has(id)), edges: story.graph.edges.filter(edge => ids.has(edge.from) && ids.has(edge.to)) } };
  }, [story,activeBranchId]);
  const selected = visibleStory.chapters.find(chapter => chapter.id === selectedId) || visibleStory.chapters[0];
  // Direct chapter URLs and restored positions are reads too.
  useEffect(()=>setUpdates(current=>acknowledgeUpdate(current,selected)),
    [selected.storyId,selected.id,selected.display?.revision,selected.narrative]);
  const unread=useMemo(()=>new Set(visibleStory.chapters.filter(c=>updates.unread[readingKey(c)]).map(c=>c.id)),[visibleStory,updates]);
  useEffect(() => {
    const value = `#${new URLSearchParams({story:slug,branch:activeBranchId,chapter:selected.id})}`;
    if (location.hash !== value) {
      try { history.replaceState(history.state,'',value); } catch { location.hash = value; }
    }
    restoreReadingPosition(value,readingKey(selected));
  },[slug,activeBranchId,selected.id]);
  const results = useMemo(() => { const q=query.trim().toLocaleLowerCase(); return visibleStory.chapters.filter(chapter => !q || `${chapter.turn} ${chapter.title} ${chapter.narrative} ${chapter.location} ${chapter.input}`.toLocaleLowerCase().includes(q)); },[visibleStory,query]);
  const matches = useMemo(() => query.trim() ? new Set(results.map(chapter => chapter.id)) : null,[query,results]);
  function select(id:string, storySlug=slug, nextBranch=activeBranchId) {
    const chapter=bundle.stories.find(s=>s.slug===storySlug)?.chapters.find(c=>c.id===id);
    if(chapter)setUpdates(current=>acknowledgeUpdate(current,chapter));
    setSelectedId(id); const params = new URLSearchParams({story:storySlug,branch:nextBranch,chapter:id});
    try { history.replaceState(history.state,'',`#${params}`); } catch { location.hash = params.toString(); }
  }
  function switchStory(value:string) {
    const next=bundle.stories.find(item=>item.slug===value)!; const nextBranch=next.defaultBranchId;
    setSlug(value); setBranchId(nextBranch); setQuery(''); setShowWarnings(false); select(firstNode(next,nextBranch),value,nextBranch);
  }
  function switchBranch(value:string) { setBranchId(value); setQuery(''); select(firstNode(story,value),slug,value); }
  return <div className="app">
    <header className="app-header"><div className="brand"><span className="brand-symbol">⌘</span><div><strong>故事经纬</strong><span>STORY ATLAS</span></div></div>
      <div className="header-path">我的故事 <span>/</span> {story.title}</div>{unread.size>0 && <button className="update-notice" onClick={()=>select([...unread].at(-1)!)}>{unread.size} 幕更新 · 点击阅读</button>}<div className="local-status"><i/> 本地展示 <span>·</span> {new Date(story.syncedAt).toLocaleDateString('zh-CN')}</div></header>
    <SplitWorkspace>
      <aside className="sidebar"><div className="library-heading"><span className="eyebrow">YOUR LIBRARY</span><h1>故事集</h1><p>沿故事时间，阅读每一种可能。</p></div>
        <label className="story-selector">当前故事<select aria-label="选择故事" value={slug} onChange={event=>switchStory(event.target.value)}>{bundle.stories.map(item=><option key={item.slug} value={item.slug}>{item.title}</option>)}</select></label>
        <label className="story-selector branch-selector">展示分支<select aria-label="选择分支" value={activeBranchId} onChange={event=>switchBranch(event.target.value)}><option value="all">全部节点</option>{story.branches.map(branch=><option key={branch.id} value={branch.id}>{branch.name}{branch.id===story.defaultBranchId?'（默认）':''}</option>)}</select></label>
        <div className="story-stats"><div><strong>{visibleStory.chapters.length}</strong><span>时间切片</span></div><div><strong>{visibleStory.graph.edges.length}</strong><span>时序关系</span></div><div><strong>{story.branches.length}</strong><span>创作分支</span></div></div>
        <div className="search-box"><span>⌕</span><input aria-label="搜索章节" placeholder="搜索正文、摘要或地点…" value={query} onChange={event=>setQuery(event.target.value)}/>{query && <button aria-label="清空搜索" onClick={()=>setQuery('')}>×</button>}</div>
        <div className="list-heading"><span>{query?'搜索结果':'时间线索引'}</span><span>{results.length} 幕</span></div>
        <nav className="chapter-list" aria-label="时间线索引">{results.map(chapter=><button key={chapter.id} className={`chapter-item ${selected.id===chapter.id?'active':''} ${unread.has(chapter.id)?'is-unread':''}`} onClick={()=>select(chapter.id)}><span className="list-number">{String(chapter.turn).padStart(2,'0')}</span><span><strong>{chapter.location || `时间切片 ${chapter.turn}`}{unread.has(chapter.id)&&<span className="update-tag">新</span>}</strong><small>{chapter.summary || chapter.narrative}</small></span></button>)}{!results.length&&<p className="empty-state">没有找到这一段故事。<br/>换个词试试。</p>}</nav>
        {story.warnings.length>0 && <div className="warnings"><button onClick={()=>setShowWarnings(!showWarnings)}>ⓘ {story.warnings.length} 条同步提示 {showWarnings?'−':'+'}</button>{showWarnings&&<ul>{story.warnings.map(warning=><li key={warning}>{warning}</li>)}</ul>}</div>}
        <div className="sidebar-footer"><span>◇</span> 展示副本不参与创作</div>
      </aside>
      <GraphView key={`${story.slug}:${activeBranchId}`} story={visibleStory} selectedId={selected.id} onSelect={select} matches={matches} unread={unread}/>
      <ChapterDetail story={visibleStory} chapter={selected} onSelect={select}/>
    </SplitWorkspace>
  </div>;
}
