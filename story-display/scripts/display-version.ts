import { createHash } from 'node:crypto';
import { writeFile, rename } from 'node:fs/promises';
import { join } from 'node:path';
import type { StoryBundle } from '../src/model/types.ts';

/** Generation/sync clocks do not change the reading content. Code/CSS changes do. */
export function displayRevision(bundle: StoryBundle, js: string, css: string): string {
  const stories = bundle.stories.map(({syncedAt: _clock, ...story}) => story);
  return createHash('sha256').update(JSON.stringify({ stories, js, css})).digest('hex');
}

export function storyRevisions(bundle: StoryBundle): Record<string,string> {
  return Object.fromEntries(bundle.stories.map(({syncedAt: _clock,...story}) =>
    [story.slug,createHash('sha256').update(JSON.stringify({story})).digest('hex')]));
}

export function versionScript(revision: string, revisions: Record<string,string> = {}): string {
  if (!/^[a-f0-9]{64}$/.test(revision)) throw new Error('展示版本必须是 SHA-256');
  if (Object.values(revisions).some(value=> !/^[a-f0-9]{64}$/.test(value))) throw new Error('故事版本必须是 SHA-256');
  return `window.storyDisplayVersionReceived?.(${JSON.stringify({contentRevision:revision,storyRevisions:revisions}).replace(/</g,'\\u003c')});\n`;
}

/** Publish the marker last: an observer must never reload an unfinished HTML. */
export async function publishDisplay(dist: string, html: string, revision: string, revisions: Record<string,string> = {}): Promise<void> {
  const marker = versionScript(revision,revisions);
  await writeFile(join(dist,'index.html.tmp'), html, 'utf8');
  await rename(join(dist,'index.html.tmp'), join(dist,'index.html'));
  await writeFile(join(dist,'display-version.js.tmp'), marker, 'utf8');
  await rename(join(dist,'display-version.js.tmp'), join(dist,'display-version.js'));
}
