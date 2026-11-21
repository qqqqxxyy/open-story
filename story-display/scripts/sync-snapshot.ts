/** Import a public v6 presentation snapshot; never query the creative database. */
import {readFile, mkdir, writeFile, rename} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import type {Story} from '../src/model/types.ts';
import {generateDisplay} from './generate.ts';
import {withDisplayLock} from './display-lock.ts';

export async function syncSnapshot(snapshotPath:string, outputRoot:string) {
  const story = JSON.parse(await readFile(snapshotPath,'utf8')) as Story;
  if(story.source_kind!=='open_story' || !story.id || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(story.id)) throw new Error('需要合法的 v6 展示快照');
  return withDisplayLock(outputRoot,async()=> {
    const dir=join(outputRoot,'story',story.id); await mkdir(dir,{recursive:true});
    const temporary=join(dir,`story-${randomUUID()}.tmp`);
    await writeFile(temporary,JSON.stringify(story,null,2)+'\n','utf8');
    await rename(temporary,join(dir,'story.json'));
    return generateDisplay(outputRoot);
  });
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2);
  if(args.length!==4 || args[0]!=='--snapshot' || args[2]!=='--output-root') throw new Error('用法：sync-snapshot.ts --snapshot <派生JSON> --output-root <展示目录>');
  syncSnapshot(resolve(args[1]),resolve(args[3])).catch(error=>{console.error(String(error));process.exitCode=1;});
}
