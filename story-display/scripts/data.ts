import { readdir, readFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { BranchRecord, Chapter, EdgeRecord, GraphRecord, Story } from '../src/model/types.ts';

export const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
type JsonObject = Record<string, any>;

function object(value: unknown): value is JsonObject { return !!value && typeof value === 'object' && !Array.isArray(value); }
function string(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value) throw new Error(`story.json：${field} 必须是非空字符串`);
  return value;
}
function strings(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) throw new Error(`story.json：${field} 必须是字符串数组`);
  return [...value];
}
function parse(body: string, file: string): unknown {
  try { return JSON.parse(body.replace(/^\uFEFF/, '')); }
  catch (error) { throw new Error(`${file}：JSON 格式错误：${String(error)}`); }
}

export function validateStorySnapshot(value: unknown, directoryName: string): Story {
  if (!object(value) || !['file_story','open_story'].includes(value.source_kind)) throw new Error('展示数据结构不匹配，请从数据库或原始故事重新导出并生成页面');
  const id = string(value.id, 'id');
  if (id !== directoryName || value.slug !== id) throw new Error(`story.json：目录、id 与 slug 必须一致（${directoryName}）`);
  string(value.title, 'title'); string(value.syncedAt, 'syncedAt');
  if (!Array.isArray(value.chapters)) throw new Error('story.json：chapters 必须是数组');
  const chapterIds = new Set<string>(); const timelineOrders = new Set<number>();
  const chapters: Chapter[] = value.chapters.map((item: unknown, index: number) => {
    if (!object(item)) throw new Error(`story.json：chapters[${index}] 必须是对象`);
    const chapterId = string(item.id, `chapters[${index}].id`);
    if (item.storyId !== id) throw new Error(`story.json：节点 ${chapterId} 的 storyId 不匹配`);
    if (chapterIds.has(chapterId)) throw new Error(`story.json：重复节点 ID ${chapterId}`);
    if (!Number.isInteger(item.timelineOrder) || item.timelineOrder < 0 || timelineOrders.has(item.timelineOrder)) throw new Error(`story.json：节点 ${chapterId} 的 timelineOrder 无效或重复`);
    if (!Number.isInteger(item.creationIndex) || !Number.isInteger(item.turn)) throw new Error(`story.json：节点 ${chapterId} 缺少整数序号`);
    string(item.narrative, `节点 ${chapterId}.narrative`);
    strings(item.participants, `节点 ${chapterId}.participants`); strings(item.branchIds, `节点 ${chapterId}.branchIds`);
    chapterIds.add(chapterId); timelineOrders.add(item.timelineOrder);
    return item as Chapter;
  }).sort((a, b) => a.timelineOrder - b.timelineOrder || a.id.localeCompare(b.id));

  if (!object(value.graph) || value.graph.storyId !== id || !Array.isArray(value.graph.entryNodeIds) || !Array.isArray(value.graph.edges)) throw new Error('story.json：graph 必须是匹配故事的 v2 关系图');
  const entryNodeIds = strings(value.graph.entryNodeIds, 'graph.entryNodeIds');
  for (const nodeId of entryNodeIds) if (!chapterIds.has(nodeId)) throw new Error(`story.json：时间线入口不存在：${nodeId}`);
  const edgeIds = new Set<string>(); const pairs = new Set<string>();
  const edges: EdgeRecord[] = value.graph.edges.map((edge: unknown, index: number) => {
    if (!object(edge)) throw new Error(`story.json：graph.edges[${index}] 必须是对象`);
    const edgeId = string(edge.id, `graph.edges[${index}].id`); const from = string(edge.from, `边 ${edgeId}.from`); const to = string(edge.to, `边 ${edgeId}.to`);
    if (!chapterIds.has(from) || !chapterIds.has(to)) throw new Error(`story.json：边 ${edgeId} 的端点不存在：${from} → ${to}`);
    if (edgeIds.has(edgeId)) throw new Error(`story.json：重复边 ID ${edgeId}`);
    const pair = JSON.stringify([from, to]); if (pairs.has(pair)) throw new Error(`story.json：重复时间关系 ${from} → ${to}`);
    if (edge.kind !== 'timeline') throw new Error(`story.json：边 ${edgeId} 必须是 timeline 关系`);
    edgeIds.add(edgeId); pairs.add(pair); return edge as EdgeRecord;
  });
  const graph: GraphRecord = { storyId: id, entryNodeIds, edges };

  if (!Array.isArray(value.branches)) throw new Error('story.json：branches 必须是数组');
  const branchIds = new Set<string>();
  const branches: BranchRecord[] = value.branches.map((branch: unknown, index: number) => {
    if (!object(branch)) throw new Error(`story.json：branches[${index}] 必须是对象`);
    const branchId = string(branch.id, `branches[${index}].id`); const headNodeId = string(branch.headNodeId, `分支 ${branchId}.headNodeId`);
    if (branchIds.has(branchId)) throw new Error(`story.json：重复分支 ID ${branchId}`);
    if (!chapterIds.has(headNodeId)) throw new Error(`story.json：分支 ${branchId} 的头节点不存在：${headNodeId}`);
    const nodeIds = strings(branch.nodeIds, `分支 ${branchId}.nodeIds`);
    for (const nodeId of nodeIds) if (!chapterIds.has(nodeId)) throw new Error(`story.json：分支 ${branchId} 引用了不存在的节点：${nodeId}`);
    branchIds.add(branchId); return { ...branch, nodeIds: [...nodeIds].sort((a, b) => chapters.find(c => c.id === a)!.timelineOrder - chapters.find(c => c.id === b)!.timelineOrder) } as BranchRecord;
  });
  string(value.defaultBranchId, 'defaultBranchId');
  if (branches.length && !branchIds.has(value.defaultBranchId)) throw new Error(`story.json：默认分支不存在：${value.defaultBranchId}`);
  if (!Array.isArray(value.warnings) || value.warnings.some((warning: unknown) => typeof warning !== 'string')) throw new Error('story.json：warnings 必须是字符串数组');
  return { ...value, chapters, graph, branches, warnings: [...value.warnings] } as Story;
}

export async function loadStory(dir: string, transform: (value:any)=>any = value=>value): Promise<Story> {
  const path = join(dir, 'story.json');
  return validateStorySnapshot(transform(parse(await readFile(path, 'utf8'), path)), basename(dir));
}

export async function loadStories(root = join(projectRoot, 'story'), transform: (value:any)=>any = value=>value, allowEmpty = false): Promise<Story[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const stories: Story[] = [];
  for (const entry of entries.filter(item => item.isDirectory() && !item.name.startsWith('.')).sort((a, b) => a.name.localeCompare(b.name))) {
    try { const story=await loadStory(join(root, entry.name),transform);if(story.chapters.length)stories.push(story); }
    catch (error: any) { if (error.code !== 'ENOENT') throw error; }
  }
  if (!stories.length && !allowEmpty) throw new Error('story 目录中未发现由 V4 同步生成的 story.json');
  return stories.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN') || a.id.localeCompare(b.id));
}
