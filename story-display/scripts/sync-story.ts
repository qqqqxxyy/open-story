import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { withDisplayLock } from './display-lock.ts';
import type { BranchRecord, Chapter, EdgeRecord, GraphRecord, Story } from '../src/model/types.ts';

export const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;

type JsonObject = Record<string, any>;
export interface SyncOptions { storyId: string; dataRoot?: string; displayRoot?: string; allowEmpty?: boolean }

function object(value: unknown): value is JsonObject { return !!value && typeof value === 'object' && !Array.isArray(value); }
function json(value: unknown) { return JSON.stringify(value, null, 2) + '\n'; }
function text(value: unknown) { return typeof value === 'string' ? value : ''; }
function safeId(value: string, field = 'story ID') {
  if (!SAFE_ID.test(value)) throw new Error(`${field} 不合法：${value}`);
  return value;
}
function inside(root: string, path: string) {
  const rel = relative(resolve(root), resolve(path));
  if (rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))) return resolve(path);
  throw new Error(`路径超出允许目录：${path}`);
}
async function readJson(path: string): Promise<JsonObject> {
  let value: unknown;
  try { value = JSON.parse((await readFile(path, 'utf8')).replace(/^\uFEFF/, '')); }
  catch (error) { throw new Error(`${path}：JSON 读取失败：${String(error)}`); }
  if (!object(value)) throw new Error(`${path}：应为 JSON 对象`);
  return value;
}
async function readLines(path: string): Promise<JsonObject[]> {
  try {
    const body = await readFile(path, 'utf8');
    return body.split(/\r?\n/).filter(line => line.trim()).map((line, index) => {
      try { const value = JSON.parse(line); if (!object(value)) throw new Error('not object'); return value; }
      catch (error) { throw new Error(`${path}:${index + 1}：JSONL 格式错误：${String(error)}`); }
    });
  } catch (error: any) { if (error.code === 'ENOENT') return []; throw error; }
}
async function verifyNode(dir: string) {
  const manifest = await readJson(join(dir, 'manifest.json'));
  if (!object(manifest.files)) throw new Error(`${dir}：manifest files 缺失`);
  for (const [name, expected] of Object.entries(manifest.files)) {
    const path = inside(dir, join(dir, name));
    const actual = createHash('sha256').update(await readFile(path)).digest('hex');
    if (actual !== expected) throw new Error(`${basename(dir)}/${name} hash mismatch`);
  }
}
function compareMeta(a: JsonObject, b: JsonObject) {
  return Number(a.display_index ?? 0) - Number(b.display_index ?? 0)
    || text(a.created_at).localeCompare(text(b.created_at))
    || text(a.node_id).localeCompare(text(b.node_id));
}
function timelineOrder(metas: Map<string, JsonObject>, rawEdges: Array<[string, string]>) {
  const pairs = new Map<string, [string, string]>();
  for (const [from, to] of rawEdges) {
    if (from === to || !metas.has(from) || !metas.has(to)) continue;
    pairs.set(JSON.stringify([from, to]), [from, to]);
  }
  const outgoing = new Map([...metas.keys()].map(id => [id, [] as string[]]));
  const indegree = new Map([...metas.keys()].map(id => [id, 0]));
  for (const [from, to] of pairs.values()) {
    outgoing.get(from)!.push(to);
    indegree.set(to, indegree.get(to)! + 1);
  }
  const ready = [...metas.keys()].filter(id => indegree.get(id) === 0).sort((a, b) => compareMeta(metas.get(a)!, metas.get(b)!));
  const ordered: string[] = [];
  while (ready.length) {
    const id = ready.shift()!;
    ordered.push(id);
    for (const next of outgoing.get(id)!) {
      indegree.set(next, indegree.get(next)! - 1);
      if (indegree.get(next) === 0) {
        ready.push(next);
        ready.sort((a, b) => compareMeta(metas.get(a)!, metas.get(b)!));
      }
    }
  }
  if (ordered.length !== metas.size) throw new Error('timeline relations contain a cycle; refusing to invent a display order');
  return { ordered, pairs: [...pairs.values()] };
}
function branchPath(head: string, allMetas: Map<string, JsonObject>) {
  const path: string[] = []; const seen = new Set<string>(); let current: string | null = head;
  while (current && allMetas.has(current)) {
    if (seen.has(current)) throw new Error(`creation graph cycle at ${current}`);
    seen.add(current);
    const meta: JsonObject = allMetas.get(current)!;
    if (meta.kind !== 'root') path.push(current);
    current = typeof meta.creation_parent_id === 'string' ? meta.creation_parent_id : null;
  }
  return path.reverse();
}

export async function syncStory(options: SyncOptions): Promise<Story> {
  const storyId = safeId(options.storyId);
  if (!options.dataRoot) throw new Error('旧原始文件同步需要显式 --data-root');
  const dataRoot = resolve(options.dataRoot);
  const displayRoot = resolve(options.displayRoot ?? join(projectRoot, 'story'));
  const source = inside(join(dataRoot, 'stories'), join(dataRoot, 'stories', storyId));
  const sourceInfo = await stat(source).catch(() => null);
  if (!sourceInfo?.isDirectory()) throw new Error(`v4 故事不存在：${storyId}`);
  const storyMeta = await readJson(join(source, 'story.json'));
  if (storyMeta.version !== 4 || storyMeta.id !== storyId) throw new Error('story.json 与 v4 story ID 不匹配');

  const allMetas = new Map<string, JsonObject>();
  const nodeDirs = (await readdir(join(source, 'nodes'), { withFileTypes: true })).filter(entry => entry.isDirectory()).sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of nodeDirs) {
    const dir = join(source, 'nodes', entry.name);
    await verifyNode(dir);
    const meta = await readJson(join(dir, 'meta.json'));
    if (meta.story_id !== storyId || meta.node_id !== entry.name) throw new Error(`${entry.name}：节点作用域不匹配`);
    allMetas.set(entry.name, meta);
  }
  const metas = new Map([...allMetas].filter(([, meta]) => meta.kind !== 'root'));
  if (!metas.size && !options.allowEmpty) throw new Error('故事没有可展示场景节点');

  const timelineRows = await readLines(join(source, 'timeline', 'relations.jsonl'));
  const rawEdges: Array<[string, string]> = [];
  for (const row of timelineRows) if (row.type === 'before') rawEdges.push([text(row.from_node_id), text(row.to_node_id)]);
  for (const [nodeId, meta] of metas) {
    const storyTime = object(meta.story_time) ? meta.story_time : {};
    for (const before of Array.isArray(storyTime.before_node_ids) ? storyTime.before_node_ids : []) if (typeof before === 'string') rawEdges.push([nodeId, before]);
    for (const after of Array.isArray(storyTime.after_node_ids) ? storyTime.after_node_ids : []) if (typeof after === 'string') rawEdges.push([after, nodeId]);
  }
  const explicitPairs = new Set(rawEdges.map(pair => JSON.stringify(pair)));
  const warnings: string[] = [];
  for (const [nodeId, meta] of metas) {
    const parent = text(meta.creation_parent_id);
    const mentioned = rawEdges.some(([from, to]) => from === nodeId || to === nodeId);
    if (!mentioned && metas.has(parent) && meta.relation !== 'prequel') {
      rawEdges.push([parent, nodeId]);
      warnings.push(`${nodeId} 缺少显式 timeline 关系，展示层回退到创作父节点顺序。`);
    }
  }
  const timeline = timelineOrder(metas, rawEdges);
  const order = new Map(timeline.ordered.map((id, index) => [id, index]));

  const branchDir = join(source, 'graph', 'branches');
  const branches: BranchRecord[] = [];
  for (const file of (await readdir(branchDir)).filter(name => name.endsWith('.json')).sort()) {
    const branch = await readJson(join(branchDir, file));
    if (branch.story_id !== storyId) throw new Error(`${file}：branch story ID 不匹配`);
    const creationNodes = branchPath(text(branch.head_node_id), allMetas);
    branches.push({ id: text(branch.branch_id), name: text(branch.name) || text(branch.branch_id),
      headNodeId: text(branch.head_node_id), status: text(branch.status),
      nodeIds: creationNodes.sort((a, b) => order.get(a)! - order.get(b)!) });
  }
  const defaultBranchId = text(storyMeta.default_branch_id) || 'main';
  if (!branches.some(branch => branch.id === defaultBranchId)) {
    throw new Error(`${storyId}：默认分支不存在：${defaultBranchId}`);
  }
  const branchIdsByNode = new Map([...metas.keys()].map(id => [id, [] as string[]]));
  for (const branch of branches) for (const nodeId of branch.nodeIds) branchIdsByNode.get(nodeId)?.push(branch.id);

  const chapters: Chapter[] = [];
  for (const nodeId of timeline.ordered) {
    const dir = join(source, 'nodes', nodeId);
    const meta = metas.get(nodeId)!;
    const input = await readJson(join(dir, 'input.json'));
    const delta = await readJson(join(dir, 'delta.json'));
    const scene = object(delta.scene) ? delta.scene : {};
    const narrative = (await readFile(join(dir, 'narrative.md'), 'utf8')).replace(/\r\n/g, '\n').trimEnd();
    const summary = text(scene.summary);
    chapters.push({
      id: nodeId, storyId, turn: order.get(nodeId)! + 1, timelineOrder: order.get(nodeId)!,
      creationIndex: Number(meta.display_index ?? 0), creationParentId: typeof meta.creation_parent_id === 'string' ? meta.creation_parent_id : null,
      relation: text(meta.relation), branchIds: branchIdsByNode.get(nodeId) ?? [],
      file: `nodes/${nodeId}/narrative.md`, title: summary || `时序 ${order.get(nodeId)! + 1}`,
      narrative, summary, location: text(scene.location), time: text(scene.time),
      participants: Array.isArray(scene.participants) ? scene.participants.filter((value: unknown) => typeof value === 'string') : [],
      input: text(input.raw_player_input), intent: text(input.interpreted_intent), raw: { meta, input, delta },
    });
  }
  const edges: EdgeRecord[] = timeline.pairs.map(([from, to]) => ({
    id: `timeline-${createHash('sha256').update(`${from}\0${to}`).digest('hex').slice(0, 16)}`,
    from, to, kind: 'timeline',
    ...(!explicitPairs.has(JSON.stringify([from, to])) ? { label: '展示顺序回退' } : {}),
  }));
  const indegree = new Map([...metas.keys()].map(id => [id, 0]));
  for (const edge of edges) indegree.set(edge.to, indegree.get(edge.to)! + 1);
  const graph: GraphRecord = { storyId, entryNodeIds: timeline.ordered.filter(id => indegree.get(id) === 0), edges };
  const snapshot: Story = { source_kind: 'file_story', syncedAt: new Date().toISOString(),
    slug: storyId, title: text(storyMeta.title) || storyId, id: storyId,
    chapters, graph, branches, defaultBranchId, warnings };

  await mkdir(displayRoot, { recursive: true });
  const target = inside(displayRoot, join(displayRoot, storyId));
  const temporary = inside(displayRoot, join(displayRoot, `.sync-${storyId}-${randomUUID()}`));
  const previous = inside(displayRoot, join(displayRoot, `.previous-${storyId}-${randomUUID()}`));
  await mkdir(temporary);
  await writeFile(join(temporary, 'story.json'), json(snapshot), 'utf8');
  let movedPrevious = false;
  try {
    const targetInfo = await stat(target).catch(() => null);
    if (targetInfo) { await rename(target, previous); movedPrevious = true; }
    await rename(temporary, target);
    if (movedPrevious) await rm(previous, { recursive: true, force: true });
  } catch (error) {
    await rm(temporary, { recursive: true, force: true }).catch(() => {});
    if (movedPrevious && !(await stat(target).catch(() => null))) await rename(previous, target).catch(() => {});
    throw error;
  }
  return snapshot;
}

function parseArgs(argv: string[]) {
  const storyId = argv[0];
  if (!storyId) throw new Error('用法：node scripts/sync-story.ts <story-id> [--data-root <path>]');
  let dataRoot: string | undefined;
  for (let index = 1; index < argv.length; index += 1) {
    if (argv[index] === '--data-root' && argv[index + 1] && !dataRoot && !argv[index+1].startsWith('--')) { dataRoot = argv[++index]; continue; }
    throw new Error(`未知参数：${argv[index]}`);
  }
  return { storyId, dataRoot };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  withDisplayLock(projectRoot,()=>syncStory(parseArgs(process.argv.slice(2)))).then(story => {
    console.log(`已同步 ${story.title} (${story.id})：${story.chapters.length} 个节点，${story.branches.length} 条分支。`);
  }).catch(error => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; });
}
