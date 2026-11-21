import { readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { projectRoot } from './data.ts';
import { syncStory } from './sync-story.ts';
import { generateDisplay } from './generate.ts';
import { withDisplayLock } from './display-lock.ts';
import { savePreview, normalizedBody, type Preview } from './preview-store.ts';

const safe=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
export function validatePreview(value:any):Preview {
  const fields=['action','story_id','branch_id','turn_id','expected_head','narrative','input',...(value?.action==='finish'?['node_id']:[])];
  if(!value || Array.isArray(value) || typeof value!=='object' || Object.keys(value).some(k=>!fields.includes(k)) ||
      fields.some(k=>!(k in value)) || !['publish','finish'].includes(value.action)) throw new Error('无效的预览参数');
  for(const key of ['story_id','branch_id','turn_id','expected_head',...(value.action==='finish'?['node_id']:[])])
    if(typeof value[key]!=='string' || !safe.test(value[key])) throw new Error(`无效的 ${key}`);
  if(typeof value.narrative!=='string' || !value.narrative.trim() || typeof value.input!=='string') throw new Error('预览必须包含完整正文与原始输入');
  return value;
}
export async function publishPreview(value:Preview,dataRoot:string,outputRoot:string) {
  const preview=validatePreview(value);
  return withDisplayLock(outputRoot,async()=>{
    const source=join(dataRoot,'stories',preview.story_id);
    const branch=JSON.parse(await readFile(join(source,'graph/branches',`${preview.branch_id}.json`),'utf8'));
    if(branch.story_id!==preview.story_id || branch.branch_id!==preview.branch_id) throw new Error('分支作用域不匹配');
    if(preview.action==='publish' && branch.head_node_id!==preview.expected_head) throw new Error('STALE_HEAD');
    const snapshot=await syncStory({storyId:preview.story_id,dataRoot,displayRoot:join(outputRoot,'story'),allowEmpty:true});
    if(preview.action==='finish') {
      const node=snapshot.chapters.find(c=>c.id===preview.node_id);
      if(!node || !node.branchIds.includes(preview.branch_id) || node.creationParentId!==preview.expected_head ||
          (node.raw.input as any)?.turn_id!==preview.turn_id || normalizedBody(node.narrative)!==normalizedBody(preview.narrative) ||
          node.input!==preview.input) throw new Error('归档正文或作用域与预览不匹配');
    }
    await savePreview(outputRoot,preview);
    return generateDisplay(outputRoot);
  });
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    const args=process.argv.slice(2), values:Record<string,string>={};
    for(let i=0;i<args.length;i+=2) {
      if(!['--payload','--data-root','--display-root'].includes(args[i]) || !args[i+1] || args[i+1].startsWith('--') || values[args[i]]) throw new Error(`未知、重复或缺少值的参数：${args[i]}`);
      values[args[i]]=args[i+1];
    }
    if(!values['--payload'] || !values['--data-root']) throw new Error('需要 --payload 和 --data-root');
    const payload=JSON.parse((await readFile(values['--payload'],'utf8')).replace(/^\uFEFF/,''));
    await publishPreview(payload,resolve(values['--data-root']),resolve(values['--display-root']??projectRoot));
  } catch(error) {console.error(String(error));process.exitCode=1;}
}
