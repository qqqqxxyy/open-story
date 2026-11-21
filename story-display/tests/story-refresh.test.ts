import {test} from 'node:test';
import assert from 'node:assert/strict';
import {storyRevisions,displayRevision} from '../scripts/display-version.ts';
import {shouldRefreshStory} from '../src/refresh-policy.ts';
import {fixtureStory} from './fixtures.ts';

test('only selected story changes trigger refresh, with fixed loaded baselines across story switches',async()=>{
  const stories = [fixtureStory(),fixtureStory('other')];
  assert.ok(stories.length>1);
  const bundle={generatedAt:'old',stories};
  const loaded=storyRevisions(bundle), selected=stories[0].slug, other=stories[1].slug;
  const edited=structuredClone(bundle);
  edited.stories[1].chapters[0].narrative+='other changed';
  const marker={contentRevision:displayRevision(edited,'new code','css'),storyRevisions:storyRevisions(edited)};
  assert.equal(shouldRefreshStory(loaded,marker,selected),false);
  assert.equal(shouldRefreshStory(loaded,marker,other),true);
  edited.stories[0].chapters[0].narrative+='selected changed';
  marker.storyRevisions=storyRevisions(edited);
  assert.equal(shouldRefreshStory(loaded,marker,selected),true);
  assert.deepEqual(storyRevisions({...bundle,generatedAt:'new',stories:stories.map(s=>({...s,syncedAt:'new'}))}),loaded);
  assert.equal(shouldRefreshStory(loaded,{...marker,storyRevisions:loaded},selected),false);
});

test('preview addition, promotion and removal are story changes; malformed callbacks are ignored',async()=>{
  const stories=[fixtureStory(),fixtureStory('other')];
  const bundle={generatedAt:'now',stories};
  const slug=stories[0].slug, loaded=storyRevisions(bundle);
  const edited=structuredClone(bundle);
  const chapter=structuredClone(edited.stories[0].chapters[0]);
  chapter.id='preview-example';chapter.display={key:'turn-example',revision:'a'.repeat(64),pending:true};
  edited.stories[0].chapters.push(chapter);
  const marker={contentRevision:'b'.repeat(64),storyRevisions:storyRevisions(edited)};
  assert.equal(shouldRefreshStory(loaded,marker,slug),true);
  const previewLoaded=marker.storyRevisions;
  chapter.display.pending=false;chapter.id='committed-example';
  assert.equal(shouldRefreshStory(previewLoaded,{...marker,storyRevisions:storyRevisions(edited)},slug),true);
  assert.equal(shouldRefreshStory(loaded,{...marker,storyRevisions:{}},slug),true);
  assert.equal(shouldRefreshStory(loaded,{...marker,storyRevisions:{[slug]:'bad'}},slug),false);
  assert.equal(shouldRefreshStory(loaded,{contentRevision:'c'.repeat(64)},slug),false);
  assert.equal(shouldRefreshStory(loaded,marker,null),false);
});
