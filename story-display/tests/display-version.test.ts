import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { displayRevision, publishDisplay, versionScript } from '../scripts/display-version.ts';
import {fixtureStory} from './fixtures.ts';

test('identical display content ignores generation and synchronization clocks', async () => {
  const stories = [fixtureStory(),fixtureStory('other')];
  const bundle = {generatedAt:'old',stories};
  const revision = displayRevision(bundle,'js','css');
  assert.equal(displayRevision({...bundle,generatedAt:'new',stories:stories.map(story=>({...story,syncedAt:'new'}))},'js','css'),revision);
  const edited = structuredClone(bundle);
  edited.stories[0].chapters[0].narrative += '\n新的正文';
  assert.notEqual(displayRevision(edited,'js','css'),revision);
  assert.notEqual(displayRevision(bundle,'new-js','css'),revision);
  assert.notEqual(displayRevision(bundle,'js','new-css'),revision);
});

test('publisher replaces HTML before marker and preserves the marker if HTML publication fails', async () => {
  const dir = await mkdtemp(join(tmpdir(),'story-display-publish-'));
  const revision = 'a'.repeat(64);
  try {
    await publishDisplay(dir,'first',revision);
    assert.equal(await readFile(join(dir,'index.html'),'utf8'),'first');
    assert.equal(await readFile(join(dir,'display-version.js'),'utf8'),versionScript(revision));
    await mkdir(join(dir,'index.html.tmp'));
    await assert.rejects(publishDisplay(dir,'unfinished','b'.repeat(64)));
    assert.equal(await readFile(join(dir,'index.html'),'utf8'),'first');
    assert.equal(await readFile(join(dir,'display-version.js'),'utf8'),versionScript(revision));
  } finally { await rm(dir,{recursive:true,force:true}); }
});
