import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {acknowledgeUpdate,readingKey,reconcileUpdates} from '../src/reading-updates.ts';
import {bodyRevision,loadPresentation} from '../scripts/preview-store.ts';
import type {Story,StoryBundle,ReadingUpdateRepair} from '../src/model/types.ts';

function story(id='example',count=3):Story {
  const chapters=Array.from({length:count},(_,i)=>({
    id:'node-'+i,storyId:id,turn:i+1,file:'',title:'幕',narrative:'正文'+i+'\r\n',
    summary:'摘要',location:'',time:'',participants:[],input:'',intent:'',raw:{},
    timelineOrder:i,creationIndex:i+1,creationParentId:i?'node-'+(i-1):null,
    relation:'continuation',branchIds:['main'],
    display:{key:'node:node-'+i,revision:bodyRevision('正文'+i+'\r\n'),pending:false}
  }));
  return {source_kind: 'open_story',id,slug:id,title:id,syncedAt:'now',chapters,
    graph:{storyId:id,entryNodeIds:['node-0'],edges:[]},
    branches:[{id:'main',name:'main',headNodeId:chapters.at(-1)!.id,status:'open',nodeIds:chapters.map(c=>c.id)}],
    defaultBranchId:'main',warnings:[]};
}
const bundle=(...stories:Story[]):StoryBundle=>({generatedAt:'now',stories});
const keys=(state:ReturnType<typeof reconcileUpdates>)=>Object.keys(state.unread);

test('missing and empty baselines silently accept published history independently per story',()=>{
  const current=bundle(story());
  assert.deepEqual(keys(reconcileUpdates(current,null)),[]);
  assert.deepEqual(keys(reconcileUpdates(current,{known:{},unread:{}})),[]);
  const other=story('other');
  const previous=reconcileUpdates(bundle(other),null);
  assert.deepEqual(keys(reconcileUpdates(bundle(other,story()),previous)),[]);
  current.stories[0].chapters[2].display!.pending=true;
  assert.deepEqual(keys(reconcileUpdates(current,{known:{},unread:{}})),[readingKey(current.stories[0].chapters[2])]);
});

test('valid baseline detects one new scene and one real edit, but not regeneration or publication',()=>{
  const old=story('example',2), previous=reconcileUpdates(bundle(old),null);
  const current=story();
  current.chapters[2].display!.pending=true;
  let state=reconcileUpdates(bundle(current),previous);
  assert.deepEqual(keys(state),[readingKey(current.chapters[2])]);
  state=acknowledgeUpdate(state,current.chapters[2]);
  current.chapters[2].display!.pending=false;
  state=reconcileUpdates(bundle(current),state);
  assert.deepEqual(keys(state),[]);
  const edited=structuredClone(current);
  edited.chapters[0].narrative='真实修改';
  edited.chapters[0].display!.revision=bodyRevision('真实修改');
  assert.deepEqual(keys(reconcileUpdates(bundle(edited),state)),[readingKey(edited.chapters[0])]);
  assert.deepEqual(keys(reconcileUpdates({...bundle(current),generatedAt:'later'},state)),[]);
});

test('a displayed chapter acknowledges once, including restoration and changed prose',()=>{
  const current=story(), chapter=current.chapters[2];
  chapter.display!.pending=true;
  const unread=reconcileUpdates(bundle(current),null);
  const read=acknowledgeUpdate(unread,chapter);
  assert.deepEqual(keys(read),[]);
  assert.strictEqual(acknowledgeUpdate(read,chapter),read);
  const updated={...chapter,display:{...chapter.display!,revision:bodyRevision('修改')}};
  const state={known:read.known,unread:{[readingKey(updated)]:updated.display.revision}};
  assert.deepEqual(keys(acknowledgeUpdate(state,updated)),[]);
});

test('v6 presentation preserves API display metadata and original prose',async()=>{
  const current=story(); const chapter=current.chapters[2];
  chapter.display={key:'node:stable-key',revision:bodyRevision(chapter.narrative),pending:true};
  const projected=(await loadPresentation(tmpdir()))(current);
  assert.deepEqual(projected.chapters[2].display,chapter.display);
  assert.equal(projected.chapters[2].narrative,chapter.narrative);
  const legacy=structuredClone(current);
  legacy.chapters[2].display!.revision=createHash('sha256').update(chapter.narrative).digest('hex');
  const upgraded=(await loadPresentation(tmpdir()))(legacy);
  assert.deepEqual(upgraded.chapters[2].display,chapter.display);
  assert.equal(upgraded.chapters[2].narrative,chapter.narrative);
  assert.equal(bodyRevision('正文\r\n\u00a0\ufeff'),bodyRevision('正文'));
  assert.notEqual(bodyRevision('正文\u0085'),bodyRevision('正文'));
});

test('scoped repair clears only known old false alerts once and preserves new scenes and other stories',()=>{
  const current=story(), other=story('other',1), old=current.chapters[0];
  const repair:ReadingUpdateRepair={id:'incident',storyId:current.id,chapters:[{
    nodeId:old.id,key:readingKey(old),revision:old.display!.revision,legacyRevision:'legacy'
  }]};
  const data={...bundle(current,other),readingUpdateRepairs:[repair]};
  const previous=reconcileUpdates(bundle(current,other),null);
  previous.known[readingKey(old)]='legacy';
  previous.unread={...previous.known};
  const state=reconcileUpdates(data,previous);
  assert.deepEqual(keys(state).sort(),[readingKey(current.chapters[1]),readingKey(current.chapters[2]),readingKey(other.chapters[0])].sort());
  assert.equal(state.known[readingKey(old)],old.display!.revision);
  const edited=structuredClone(data);
  edited.stories[0].chapters[0].display!.revision=bodyRevision('新修改');
  assert.ok(reconcileUpdates(edited,state).unread[readingKey(old)]);
  assert.ok(reconcileUpdates(edited,previous).unread[readingKey(old)]);
  assert.deepEqual(keys(reconcileUpdates(data,null)),[]);
  const alreadyApplied={...state,unread:{...state.unread,[readingKey(old)]:old.display!.revision}};
  assert.ok(reconcileUpdates(data,alreadyApplied).unread[readingKey(old)]);
});

test('repair is restricted to selected ancestors, retaining later chapters',()=>{
 const current=story('fixture',5), repaired=current.chapters.slice(0,3);
 const repairs:ReadingUpdateRepair[]=[{id:'fixture-repair',storyId:current.id,chapters:repaired.map(c=>({nodeId:c.id,key:readingKey(c),revision:c.display!.revision,legacyRevision:'legacy-'+c.id}))}];
 const previous=reconcileUpdates(bundle(current),null);previous.unread={...previous.known};
 for(const item of repairs[0].chapters){previous.known[item.key]=item.legacyRevision;previous.unread[item.key]=item.legacyRevision;}
 const result=reconcileUpdates({...bundle(current),readingUpdateRepairs:repairs},previous);
 for(const chapter of repaired)assert.ok(!result.unread[readingKey(chapter)]);
 assert.deepEqual(keys(result).sort(),current.chapters.slice(3).map(readingKey).sort());
});
