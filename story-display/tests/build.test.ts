import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {generateDisplay,scopeReadingUpdateRepairs,loadReadingUpdateRepairs} from '../scripts/generate.ts';
import {fixtureStory} from './fixtures.ts';
test('generation embeds isolated current snapshots without external assets or source changes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'openstory-build-'));
 try {
  const story=fixtureStory();const dir=join(root,'story',story.id);await mkdir(dir,{recursive:true});
  const source=JSON.stringify(story);await writeFile(join(dir,'story.json'),source);
  await generateDisplay(root);const html=await readFile(join(root,'dist/index.html'),'utf8');
  const embedded=html.match(/<script type="application\/json" id="story-data">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(embedded);const bundle=JSON.parse(embedded);assert.deepEqual(bundle.stories[0].chapters,story.chapters);
  assert.deepEqual(bundle.readingUpdateRepairs,[]);
  assert.doesNotMatch(html,/<script\b[^>]*\bsrc\s*=/i);assert.equal(await readFile(join(dir,'story.json'),'utf8'),source);
  assert.ok((await readFile(join(root,'dist/display-version.js'),'utf8')).includes('contentRevision'));
 }finally{await rm(root,{recursive:true,force:true});}
});
test('empty checkout generates a usable page without a preexisting story directory',async()=>{
 const root=await mkdtemp(join(tmpdir(),'openstory-empty-'));
 try{await generateDisplay(root);assert.ok((await readFile(join(root,'dist/index.html'),'utf8')).includes('"stories":[]'));}
 finally{await rm(root,{recursive:true,force:true});}
});

test('generation scopes repair metadata while preserving repairs for visible chapters',()=>{
 const story=fixtureStory();
 const repair={id:'visible-repair',storyId:story.id,chapters:story.chapters.map(chapter=>({
  nodeId:chapter.id,key:`${story.id}/${chapter.display!.key}`,revision:chapter.display!.revision,legacyRevision:'legacy'
 }))};
 const hidden={nodeId:'hidden-chapter',key:`${story.id}/node:hidden-chapter`,revision:'hidden',legacyRevision:'old'};
 const repairs=[{...repair,chapters:[...repair.chapters,hidden]},
  {id:'other-repair',storyId:'other-story',chapters:[hidden]}];
 assert.deepEqual(scopeReadingUpdateRepairs(repairs,[story]),[repair]);
 assert.deepEqual(scopeReadingUpdateRepairs(repairs,[]),[]);
 assert.equal(repairs[0].chapters.length,4);
});

test('a clean checkout needs no private reading-repair file and can read local overrides',async()=>{
 const root=await mkdtemp(join(tmpdir(),'openstory-local-repairs-'));
 try {
  const path=join(root,'reading-update-repairs.json');
  assert.deepEqual(await loadReadingUpdateRepairs(path),[]);
  const repairs=[{id:'example-repair',storyId:'example-story',chapters:[]}];
  await writeFile(path,JSON.stringify(repairs));
  assert.deepEqual(await loadReadingUpdateRepairs(path),repairs);
 }finally{await rm(root,{recursive:true,force:true});}
});
