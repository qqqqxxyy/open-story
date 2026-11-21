import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readdir, readFile, rename, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { Chapter, Story } from '../src/model/types.ts';

export interface Preview {
  action:'publish'|'finish'; story_id:string; branch_id:string; turn_id:string;
  expected_head:string; narrative:string; input:string; node_id?:string;
}
export const normalizedBody = (body:string) => body.replace(/\r\n/g,'\n').trimEnd();
export const bodyRevision = (body:string) => createHash('sha256').update(normalizedBody(body)).digest('hex');
export const previewId = (turn:string) => `preview-${turn}`;

export async function savePreview(root:string, preview:Preview) {
  const dir = join(root,'.previews'); await mkdir(dir,{recursive:true});
  const target = join(dir,`${preview.turn_id}.json`);
  const old: Preview|null = await readFile(target,'utf8').then(JSON.parse).catch((e:any)=>{if(e.code==='ENOENT')return null;throw e;});
  if (old && (old.story_id!==preview.story_id || old.branch_id!==preview.branch_id ||
      old.expected_head!==preview.expected_head || old.narrative!==preview.narrative || old.input!==preview.input ||
      (old.node_id && old.node_id!==preview.node_id))) throw new Error('同一预览的身份或正文已改变');
  const temporary = `${target}.${randomUUID()}.tmp`;
  await writeFile(temporary,JSON.stringify(preview,null,2)+'\n','utf8'); await rename(temporary,target);
}

export async function loadPresentation(root:string) {
  const dir=join(root,'.previews');
  const names=await readdir(dir).catch((e:any)=>{if(e.code==='ENOENT')return [] as string[];throw e;});
  const previews:Preview[]=await Promise.all(names.filter(n=>n.endsWith('.json')).sort().map(async n=>JSON.parse(await readFile(join(dir,n),'utf8'))));
  return (raw:any):Story => {
    const story:Story=structuredClone(raw);
    for(const chapter of story.chapters) {
      const turn=(chapter.raw.input as any)?.turn_id;
      // v6 owns stable identity and pending state; legacy snapshots need a projection.
      // Rebuild legacy raw-text hashes too; current v6 API uses this identical rule.
      chapter.display=story.source_kind==='open_story' && chapter.display ?
        {...chapter.display,revision:bodyRevision(chapter.narrative)} :
        {key:typeof turn==='string'?`turn:${turn}`:`node:${chapter.id}`,revision:bodyRevision(chapter.narrative),pending:false};
    }
    for(const preview of previews.filter(p=>p.story_id===story.id)) {
      const canonical=story.chapters.find(c=>(c.raw.input as any)?.turn_id===preview.turn_id);
      if(canonical) {
        if(bodyRevision(canonical.narrative)!==bodyRevision(preview.narrative) || canonical.creationParentId!==preview.expected_head ||
            !canonical.branchIds.includes(preview.branch_id) || (preview.node_id && canonical.id!==preview.node_id)) throw new Error('预览与归档节点不匹配');
        canonical.display!.previewId=previewId(preview.turn_id); continue;
      }
      if(preview.action==='finish') throw new Error('归档节点尚未出现在展示快照');
      const branch=story.branches.find(b=>b.id===preview.branch_id);
      if(!branch || branch.headNodeId!==preview.expected_head) throw new Error('未归档预览的分支锚点已经改变');
      const id=previewId(preview.turn_id), index=Math.max(-1,...story.chapters.map(c=>c.timelineOrder))+1;
      const chapter:Chapter={id,storyId:story.id,turn:index+1,timelineOrder:index,creationIndex:index+1,
        creationParentId:preview.expected_head,relation:'continuation',branchIds:[preview.branch_id],file:'',
        title:`第 ${index+1} 幕`,narrative:normalizedBody(preview.narrative),summary:'',location:'',time:'',participants:[],
        input:preview.input,intent:'',raw:{},display:{key:`turn:${preview.turn_id}`,revision:bodyRevision(preview.narrative),pending:true,previewId:id}};
      story.chapters.push(chapter);branch.nodeIds.push(id);branch.headNodeId=id;
      if(story.chapters.some(c=>c.id===preview.expected_head)) story.graph.edges.push({id:`preview-edge-${preview.turn_id}`,from:preview.expected_head,to:id,kind:'timeline'});
      else story.graph.entryNodeIds.push(id);
    }
    // Empty branches may point to a hidden root before the first scene exists.
    story.branches=story.branches.filter(b=>b.nodeIds.length>0);
    if(!story.branches.some(b=>b.id===story.defaultBranchId) && story.branches.length) story.defaultBranchId=story.branches[0].id;
    return story;
  };
}
