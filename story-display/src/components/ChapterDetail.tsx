import { useEffect, useRef, useState } from 'react';
import type { Chapter, Story } from '../model/types.ts';
import { restoredDetailTab } from '../auto-refresh.ts';
import { readingKey } from '../reading-updates.ts';

export function ChapterDetail({story, chapter, onSelect}: {story: Story; chapter: Chapter; onSelect: (id:string)=>void}) {
  const [tab,setTab] = useState<'text'|'info'>(() => restoredDetailTab(chapter.id,readingKey(chapter)));
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { body.current?.scrollTo(0,0); },[chapter.id,tab]);
  const before = story.graph.edges.filter(e => e.to === chapter.id);
  const after = story.graph.edges.filter(e => e.from === chapter.id);
  function links(edges: typeof after, incoming = false) { return edges.map(e => {
    const target = story.chapters.find(c => c.id === (incoming ? e.from : e.to))!;
    return <button className="chapter-link" key={e.id} onClick={() => onSelect(target.id)}><span>{incoming?'←':'→'} {String(target.turn).padStart(2,'0')}</span><span>{e.label || target.title}</span></button>;
  }); }
  return <aside className="detail-panel" aria-label="章节详情" data-reading-key={readingKey(chapter)}>
    <div className="detail-heading"><div className="detail-index"><span className="eyebrow">TIMELINE {String(chapter.turn).padStart(2,'0')}</span><span className="small-tag">{chapter.narrative.length.toLocaleString()} 字符</span></div>
      <h2>{chapter.location || `第 ${chapter.turn} 章`}</h2><p>{story.source_kind==='file_story' && chapter.display?.pending?'正文已就绪 · 正在归档':chapter.time || '时间未标注'}</p>
      <div className="tabs"><button className={tab==='text'?'active':''} onClick={()=>setTab('text')}>阅读正文</button><button className={tab==='info'?'active':''} onClick={()=>setTab('info')}>章节信息</button></div>
    </div>
    <div className="detail-scroll" ref={body}>
      {tab === 'text' ? <><div className="scene-summary"><span className="eyebrow">这一章</span><p>{chapter.summary || '暂无摘要'}</p></div><article className="narrative">{chapter.narrative}</article><div className="end-mark">◇</div></>
      : <div className="info-content"><section><h3>你的输入</h3><p className="input-text">{chapter.input || '未记录'}</p></section><section><h3>理解的意图</h3><p>{chapter.intent || '未记录'}</p></section><section><h3>在场人物 ID</h3><div className="participant-list">{chapter.participants.map(p=><span key={p}>{p}</span>)}</div></section>
        <section><h3>源文件</h3><code>{chapter.file}</code><h3>节点 ID</h3><code>{chapter.id}</code></section>
        <section><h3>创作关系</h3><p>创作序号 {chapter.creationIndex} · 父节点 {chapter.creationParentId || '无'} · {chapter.relation || '未标注'}</p></section>
        {story.source_kind==='file_story' && <details><summary>V4 节点原始记录</summary><pre>{JSON.stringify(chapter.raw,null,2)}</pre></details>}
        <p className="muted">本页是只读展示快照；创作内容由 OpenStory 保存与维护。</p></div>}
      <div className="reading-navigation"><h3>接下来，故事走向哪里？</h3>{after.length ? links(after) : <p className="muted">这一页暂时写到这里。下一段故事，等你继续。</p>}
        {before.length > 0 && <><h4>此前的剧情</h4>{links(before,true)}</>}</div>
    </div>
    <div className="detail-footer"><span>{before.length} 个前驱 · {after.length} 个后继</span><span>本地阅读</span></div>
  </aside>;
}
