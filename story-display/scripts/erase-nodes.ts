import { readdir,readFile,unlink,rmdir,lstat } from 'node:fs/promises';
import { resolve,relative,join,sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { syncStory } from './sync-story.ts';
import { generateDisplay } from './generate.ts';
import { withDisplayLock } from './display-lock.ts';

function has(value:unknown,refs:Set<string>):boolean {
  if(typeof value==='string'){
    const segments=value.replaceAll('\\','/').split('/');
    return refs.has(value)||[...refs].some(n=>n.startsWith('node-')&&value.includes(n))||segments.some((s,i)=>s==='nodes'&&refs.has(segments[i+1]));
  }
  if(Array.isArray(value))return value.some(v=>has(v,refs));
  if(value&&typeof value==='object')return Object.entries(value).some(([k,v])=>refs.has(k)||has(v,refs));
  return false;
}

export async function eraseDisplayNodes(payload:any,dataRoot:string,outputRoot:string) {
  if(typeof payload.story_id!=='string'||!Array.isArray(payload.erased_refs)||!payload.erased_refs.every((v:any)=>typeof v==='string'))throw new Error('Invalid erasure payload');
  const root=resolve(outputRoot),refs=new Set<string>(payload.erased_refs);
  const owned=(path:string)=>{const rel=relative(root,resolve(path));if(rel==='..'||rel.startsWith('..'+sep)||rel=== '')throw new Error('Erasure path outside display');return path;};
  const clean=async(dir:string)=>{
    const entries=await readdir(dir,{withFileTypes:true}).catch((e:any)=>{if(e.code==='ENOENT')return [];throw e;});
    for(const entry of entries){
      const path=owned(join(dir,entry.name));
      if((await lstat(path)).isSymbolicLink())throw new Error('Do not traverse display links during erasure');
      if(entry.isDirectory()){await clean(path);if(!(await readdir(path)).length)await rmdir(path);}
      else if(entry.name.endsWith('.json')){
        const value=JSON.parse(await readFile(path,'utf8'));
        if(value.story_id===payload.story_id&&has(value,refs))await unlink(path);
      }
    }
  };
  return withDisplayLock(root,async()=>{
    await clean(owned(join(root,'.previews')));
    await clean(owned(join(root,'.preview-quarantine')));
    await syncStory({storyId:payload.story_id,dataRoot,displayRoot:join(root,'story'),allowEmpty:true});
    return generateDisplay(root);
  });
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2),fields=new Map<string,string>();
  for(let i=0;i<args.length;i+=2){if(!['--payload','--data-root','--display-root'].includes(args[i])||!args[i+1]||args[i+1].startsWith('--')||fields.has(args[i]))throw new Error('Invalid erase-nodes arguments');fields.set(args[i],args[i+1]);}
  if(fields.size!==3)throw new Error('erase-nodes requires --payload --data-root --display-root');
  const payload=JSON.parse(await readFile(fields.get('--payload')!,'utf8'));
  eraseDisplayNodes(payload,fields.get('--data-root')!,fields.get('--display-root')!).then(()=>{console.log('Deleted scene references and refreshed this story.');}).catch(error=>{console.error(error.message);process.exitCode=1;});
}
