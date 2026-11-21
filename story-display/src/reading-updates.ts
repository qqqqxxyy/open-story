import type { Chapter, StoryBundle } from './model/types.ts';

export interface ReadingUpdates {
  known:Record<string,string>; unread:Record<string,string>;
  appliedRepairs?:Record<string,true>;
}
export const readingKey=(chapter:Chapter)=>`${chapter.storyId}/${chapter.display?.key ?? 'node:'+chapter.id}`;
export function reconcileUpdates(bundle:StoryBundle,previous:ReadingUpdates|null):ReadingUpdates {
  const known={...previous?.known}, unread={...previous?.unread};
  const appliedRepairs={...previous?.appliedRepairs};
  for(const repair of bundle.readingUpdateRepairs??[]) {
    if(appliedRepairs[repair.id])continue;
    const story=bundle.stories.find(item=>item.id===repair.storyId);
    if(!story)continue;
    const chapters=new Map(story.chapters.map(chapter=>[chapter.id,chapter]));
    const hadBaseline=story.chapters.some(chapter=>Object.hasOwn(known,readingKey(chapter)));
    for(const item of repair.chapters) {
      const chapter=chapters.get(item.nodeId);
      // A later real prose edit remains an update, even on the repair's first load.
      if(!chapter || chapter.display?.pending || chapter.display?.revision!==item.revision ||
          readingKey(chapter)!==item.key)continue;
      if((hadBaseline && !Object.hasOwn(known,item.key)) || known[item.key]===item.legacyRevision)known[item.key]=item.revision;
      if(unread[item.key]===item.revision || unread[item.key]===item.legacyRevision)delete unread[item.key];
    }
    appliedRepairs[repair.id]=true;
  }
  const state:ReadingUpdates={known:{},unread:{}};
  if(Object.keys(appliedRepairs).length)state.appliedRepairs=appliedRepairs;
  for(const story of bundle.stories) {
    // An empty state (or a state belonging only to other stories) is not a baseline.
    const hasBaseline=story.chapters.some(chapter=>Object.hasOwn(known,readingKey(chapter)));
    for(const chapter of story.chapters) {
      const key=readingKey(chapter), revision=chapter.display?.revision ?? chapter.narrative;
      state.known[key]=revision;
      const changed=hasBaseline && known[key]!==revision;
      if(changed || unread[key]===revision || (!hasBaseline && chapter.display?.pending))state.unread[key]=revision;
    }
  }
  return state;
}
export function acknowledgeUpdate(state:ReadingUpdates,chapter:Chapter):ReadingUpdates {
  const key=readingKey(chapter);
  if(!Object.hasOwn(state.unread,key))return state;
  const unread={...state.unread};delete unread[key];return {...state,unread};
}
const storageKey=()=>`story-display:updates:${location.pathname}`;
export function readUpdates():ReadingUpdates|null {
  for(const storage of [()=>localStorage,()=>sessionStorage]) {
    try {const value=storage().getItem(storageKey());if(value){const data=JSON.parse(value);if(data && typeof data.known==='object' && typeof data.unread==='object')return data;}} catch { /* local files may restrict storage */ }
  }
  return history.state?.storyDisplayUpdates??null;
}
export function saveUpdates(state:ReadingUpdates) {
  for(const storage of [()=>localStorage,()=>sessionStorage]) try {storage().setItem(storageKey(),JSON.stringify(state));} catch { /* use history below */ }
  try {history.replaceState({...history.state,storyDisplayUpdates:state},'');} catch { /* reading still works */ }
}
