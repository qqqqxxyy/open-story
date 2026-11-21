import type {Story} from '../src/model/types.ts';
import {bodyRevision} from '../scripts/preview-store.ts';
export function fixtureStory(id='fixture'):Story {
 const chapters=Array.from({length:3},(_,i)=>({id:`${id}-${i}`,storyId:id,turn:i+1,file:'',title:`幕${i}`,
 narrative:`正文${i}`,summary:'摘要',location:'地点',time:'时间',participants:[],input:'',intent:'',raw:{},timelineOrder:i,
 creationIndex:i+1,creationParentId:i?`${id}-${i-1}`:null,relation:'continuation',branchIds:['main'],
 display:{key:`node:${id}-${i}`,revision:bodyRevision(`正文${i}`),pending:false}}));
 return {source_kind:'open_story',id,slug:id,title:id,syncedAt:'now',chapters,
 graph:{storyId:id,entryNodeIds:[`${id}-0`],edges:chapters.slice(1).map((c,i)=>({id:`e${i}`,from:chapters[i].id,to:c.id,kind:'timeline'}))},
 branches:[{id:'main',name:'main',headNodeId:chapters[2].id,status:'active',nodeIds:chapters.map(c=>c.id)}],defaultBranchId:'main',warnings:[]};
}
