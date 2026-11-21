import { build } from 'esbuild';
import { mkdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadStories, projectRoot } from './data.ts';
import type { ReadingUpdateRepair, Story, StoryBundle } from '../src/model/types.ts';
import { displayRevision, publishDisplay, storyRevisions } from './display-version.ts';
import { loadPresentation } from './preview-store.ts';
import { withDisplayLock } from './display-lock.ts';

/** Repair metadata follows the same story/chapter scope as the emitted bundle. */
export function scopeReadingUpdateRepairs(repairs:ReadingUpdateRepair[],stories:Story[]):ReadingUpdateRepair[] {
  const visible=new Map(stories.map(story=>[story.id,new Set(story.chapters.map(chapter=>chapter.id))]));
  return repairs.flatMap(repair=> {
    const nodes=visible.get(repair.storyId);
    const chapters=repair.chapters.filter(chapter=>nodes?.has(chapter.nodeId));
    return chapters.length ? [{...repair,chapters}] : [];
  });
}

/** Reading-alert repairs belong to the local story library and are optional. */
export async function loadReadingUpdateRepairs(path=join(projectRoot,'conf/reading-update-repairs.json')):Promise<ReadingUpdateRepair[]> {
  try { return JSON.parse(await readFile(path,'utf8')); }
  catch(error) { if((error as NodeJS.ErrnoException).code==='ENOENT')return [];throw error; }
}

/** Caller owns the display lock when combining sync and publication. */
export async function generateDisplay(outputRoot=projectRoot) {
  await mkdir(join(outputRoot,'story'),{recursive:true});
  const stories = await loadStories(join(outputRoot,'story'),await loadPresentation(outputRoot),true);
  const readingUpdateRepairs=scopeReadingUpdateRepairs(await loadReadingUpdateRepairs(),stories);
  const bundle: StoryBundle = {generatedAt:new Date().toISOString(), stories, readingUpdateRepairs};
  const result = await build({
    entryPoints:[join(projectRoot,'src/main.tsx')], bundle:true, write:false,
    outdir:join(projectRoot,'dist'), format:'iife', platform:'browser', target:['es2022'],
    minify:true, define:{'process.env.NODE_ENV':'"production"'},
    supported:{'inline-script':false}, legalComments:'inline',
  });
  const js = result.outputFiles.find(f=>f.path.endsWith('.js'))!.text.replace(/<\/script/gi,'<\\/script');
  const css = result.outputFiles.find(f=>f.path.endsWith('.css'))!.text.replace(/<\/style/gi,'<\\/style');
  const data = JSON.stringify(bundle).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
  const revision = displayRevision(bundle,js,css);
  const revisions = storyRevisions(bundle);
  const versions = JSON.stringify(revisions).replace(/</g,'\\u003c');
  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' file:; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'">
<meta name="story-display-revision" content="${revision}">
<title>故事经纬 · Story Atlas</title><style>${css}</style></head><body><div id="root"></div>
<script type="application/json" id="story-data">${data}</script><script type="application/json" id="story-display-versions">${versions}</script><script>${js}</script></body></html>`;
  const dist = join(outputRoot,'dist');
  await mkdir(dist,{recursive:true});
  await publishDisplay(dist,html,revision,revisions);
  console.log(`已生成 ${join(dist,'index.html')}\n${stories.length} 个故事 · ${stories.reduce((n,s)=>n+s.chapters.length,0)} 章 · ${(Buffer.byteLength(html)/1024/1024).toFixed(2)} MiB\n无需服务进程；同目录 display-version.js 每 2.5 秒检测内容变化。`);
  for(const story of stories) for(const warning of story.warnings) console.warn(`[${story.slug}] ${warning}`);
  return {revision,storyRevisions:revisions,file:join(dist,'index.html')};
}
if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
try {
  const args=process.argv.slice(2);
  if(args.length>1 || (args.length===1 && args[0]!=='--open')) throw new Error('generate 只接受可选 --open');
  const result = await withDisplayLock(projectRoot,()=>generateDisplay());
  if (process.argv.includes('--open')) {
    const file = result.file;
    const command = process.platform === 'win32' ? 'explorer.exe' : process.platform === 'darwin' ? 'open' : 'xdg-open';
    const child = spawn(command,[file],{stdio:'ignore',detached:true});
    child.on('error', error => console.error(`自动打开失败，请手动打开 ${file}：${error.message}`));
    child.unref();
  }
} catch(error) {console.error(String(error));process.exitCode=1;}
}
