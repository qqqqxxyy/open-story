import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp,mkdir,writeFile,readFile,access,rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { eraseDisplayNodes } from '../scripts/erase-nodes.ts';
import { syncStory } from '../scripts/sync-story.ts';

const body=(v:unknown)=>JSON.stringify(v)+'\n';
async function json(path:string,v:unknown){await mkdir(join(path,'..'),{recursive:true});await writeFile(path,body(v));}
async function source(data:string,id:string,scene:boolean){
  const root=join(data,'stories',id);
  await json(join(root,'story.json'),{version:4,id,title:id,default_branch_id:'main'});
  for(const name of scene?['node-root','node-keep']:['node-root']){
    const dir=join(root,'nodes',name);
    const meta={version:4,story_id:id,node_id:name,kind:name==='node-root'?'root':'scene',creation_parent_id:name==='node-root'?null:'node-root',display_index:name==='node-root'?0:1,
      relation:'continuation',state_mode:'inherit',state_base:null,constraint_anchor_id:null,origin_branch_id:'main',canon_revision_id:'canon-v1',created_at:'2026-10-02T00:00:00Z',story_time:{label:'',before_node_ids:[],after_node_ids:[]}};
    const files={'meta.json':body(meta),'input.json':body({turn_id:'turn-'+name,raw_player_input:'继续'}),'delta.json':body({scene:{summary:'保留正文',participants:[]}}),'narrative.md':name==='node-root'?'\n':'保留正文。\n'};
    for(const [file,text] of Object.entries(files)){await mkdir(dir,{recursive:true});await writeFile(join(dir,file),text);}
    await json(join(dir,'manifest.json'),{files:Object.fromEntries(Object.entries(files).map(([file,text])=>[file,createHash('sha256').update(text).digest('hex')]))});
  }
  await json(join(root,'graph/branches/main.json'),{story_id:id,branch_id:'main',head_node_id:scene?'node-keep':'node-root',name:'主线',status:'open'});
  return root;
}

test('erasure removes owned active and archived previews, preserves other stories and supports empty story',async()=>{
  const root=await mkdtemp(join(tmpdir(),'display-erasure-')),data=join(root,'data'),display=join(root,'viewer');
  try{
    await source(data,'target',false);await source(data,'other',true);
    await syncStory({storyId:'other',dataRoot:data,displayRoot:join(display,'story')});
    const otherSnapshot=await readFile(join(display,'story/other/story.json'),'utf8');
    const erased={action:'finish',story_id:'target',branch_id:'main',turn_id:'turn-erased',node_id:'node-erased',expected_head:'node-root',narrative:'旧稿秘密',input:'继续'};
    await json(join(display,'.previews/old.json'),erased);
    await json(join(display,'.preview-quarantine/revision/old.json'),erased);
    const other={action:'publish',story_id:'other',branch_id:'main',turn_id:'turn-erased',expected_head:'node-keep',narrative:'其他故事预览',input:'继续'};
    await json(join(display,'.previews/other.json'),other);
    await eraseDisplayNodes({story_id:'target',erased_refs:['node-erased','turn-erased']},data,display);
    await assert.rejects(access(join(display,'.previews/old.json')));
    await assert.rejects(access(join(display,'.preview-quarantine/revision/old.json')));
    assert.equal(await readFile(join(display,'.previews/other.json'),'utf8'),body(other));
    assert.equal(await readFile(join(display,'story/other/story.json'),'utf8'),otherSnapshot);
    const html=await readFile(join(display,'dist/index.html'),'utf8');
    assert.ok(!html.includes('旧稿秘密'));assert.ok(!html.includes('node-erased'));assert.ok(html.includes('其他故事预览'));
    // After the sole remaining story is emptied, generation still succeeds.
    await source(data,'other',false);
    const nodeDir=join(data,'stories/other/nodes/node-keep');
    await rm(nodeDir,{recursive:true});
    await eraseDisplayNodes({story_id:'other',erased_refs:['node-keep','turn-erased']},data,display);
    const empty=await readFile(join(display,'dist/index.html'),'utf8');
    assert.ok(empty.includes('"stories":[]'));assert.ok(!empty.includes('node-keep'));
  }finally{await rm(root,{recursive:true,force:true});}
});
