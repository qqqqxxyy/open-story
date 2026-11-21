import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadPresentation, savePreview, bodyRevision, type Preview } from '../scripts/preview-store.ts';
import { validateStorySnapshot } from '../scripts/data.ts';
import { validatePreview } from '../scripts/preview.ts';
import { acknowledgeUpdate, reconcileUpdates, readingKey } from '../src/reading-updates.ts';
import type { Story, StoryBundle } from '../src/model/types.ts';

const preview:Preview={action:'publish',story_id:'example',branch_id:'main',turn_id:'turn-one',expected_head:'node-root',narrative:'一声铃响。\n',input:'继续'};
const base=()=>({source_kind: 'file_story',id:'example',slug:'example',title:'测试',syncedAt:'2026-10-02',chapters:[],graph:{storyId:'example',entryNodeIds:[],edges:[]},branches:[{id:'main',name:'main',headNodeId:'node-root',status:'open',nodeIds:[]}],defaultBranchId:'main',warnings:[]});
const bundle=(story:Story):StoryBundle=>({generatedAt:'test',stories:[story]});

test('first-scene preview is valid; promotion retains identity and acknowledgements',async()=>{
  const root=await mkdtemp(join(tmpdir(),'display-preview-'));
  try {
    await savePreview(root,preview);
    const projected=(await loadPresentation(root))(base());
    validateStorySnapshot(projected,'example');
    const chapter=projected.chapters[0];
    let state=reconcileUpdates(bundle(projected),null);
    assert.equal(state.unread[readingKey(chapter)],bodyRevision(preview.narrative));
    state=acknowledgeUpdate(state,chapter);
    assert.deepEqual(state.unread,{});
    const canonical:Story={...projected,chapters:[{...chapter,id:'node-one',raw:{input:{turn_id:'turn-one'}},display:undefined}],
      graph:{storyId:'example',entryNodeIds:['node-one'],edges:[]},branches:[{...projected.branches[0],headNodeId:'node-one',nodeIds:['node-one']}]};
    await savePreview(root,{...preview,action:'finish',node_id:'node-one'});
    const promoted=(await loadPresentation(root))(canonical);
    assert.equal(promoted.chapters.length,1);
    assert.equal(promoted.chapters[0].display?.previewId,chapter.id);
    assert.equal(promoted.chapters[0].display?.key,chapter.display?.key);
    assert.deepEqual(reconcileUpdates(bundle(promoted),state).unread,{});
    const unreadBefore=reconcileUpdates(bundle(projected),null);
    assert.equal(Object.keys(reconcileUpdates(bundle(promoted),unreadBefore).unread).length,1);
    const changed=structuredClone(promoted);changed.chapters[0].display!.revision=bodyRevision('别的正文');
    assert.equal(Object.keys(reconcileUpdates(bundle(changed),state).unread).length,1);
    assert.deepEqual(reconcileUpdates(bundle(promoted),null).unread,{});
  } finally {await rm(root,{recursive:true,force:true});}
});

test('preview rejects unknown fields and stale or mismatched canonical scope',async()=>{
  assert.throws(()=>validatePreview({...preview,secret:'must not export'}));
  assert.throws(()=>validatePreview({...preview,story_id:'../other'}));
  const root=await mkdtemp(join(tmpdir(),'display-preview-'));
  try {
    await savePreview(root,preview);
    const stale=base();stale.branches[0].headNodeId='node-else';
    const transform=await loadPresentation(root);
    assert.throws(()=>transform(stale),/锚点/);
    const canonical=transform(base());
    canonical.chapters[0].raw={input:{turn_id:'turn-one'}};
    canonical.chapters[0].narrative='与预览不一致';
    assert.throws(()=>transform(canonical),/不匹配/);
    await assert.rejects(savePreview(root,{...preview,narrative:'改变原始作者回复'}));
  } finally {await rm(root,{recursive:true,force:true});}
});
