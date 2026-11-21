import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import { syncStory } from '../scripts/sync-story.ts';

function stable(value: unknown) { return JSON.stringify(value, null, 2) + '\n'; }
async function writeJson(path: string, value: unknown) { await writeFile(path, stable(value), 'utf8'); }

async function writeNode(storyRoot: string, meta: Record<string, unknown>, narrative: string) {
  const dir = join(storyRoot, 'nodes', String(meta.node_id));
  await mkdir(dir, { recursive: true });
  const files: Record<string, string> = {
    'meta.json': stable(meta),
    'input.json': stable({ turn_id: `turn-${meta.node_id}`, raw_player_input: `input-${meta.node_id}`, interpreted_intent: '继续', proxy_actions: [] }),
    'narrative.md': narrative + '\n',
    'delta.json': stable({ scene: { time: String(meta.node_id), location: '测试地', summary: `${meta.node_id}摘要`, participants: [] } }),
  };
  for (const [name, value] of Object.entries(files)) await writeFile(join(dir, name), value, 'utf8');
  await writeJson(join(dir, 'manifest.json'), {
    version: 4,
    transaction_id: `transaction-${meta.node_id}`,
    has_snapshot: false,
    files: Object.fromEntries(Object.entries(files).map(([name, value]) => [name, createHash('sha256').update(value).digest('hex')])),
  });
}

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'story-display-v4-sync-'));
  const dataRoot = join(root, 'open-story-data');
  const displayRoot = join(root, 'display');
  const storyRoot = join(dataRoot, 'stories', 'story-test');
  await mkdir(join(storyRoot, 'graph', 'branches'), { recursive: true });
  await mkdir(join(storyRoot, 'timeline'), { recursive: true });
  await writeJson(join(storyRoot, 'story.json'), { version: 4, id: 'story-test', title: '测试故事', default_branch_id: 'main' });
  const base = { version: 4, story_id: 'story-test', kind: 'scene', state_base: null, constraint_anchor_id: null,
    origin_branch_id: 'main', canon_revision_id: 'canon-v1', created_at: '2026-01-01T00:00:00Z' };
  await writeNode(storyRoot, { ...base, node_id: 'future', creation_parent_id: 'node-root', relation: 'continuation',
    state_mode: 'inherit', display_index: 1, story_time: { label: '后来', before_node_ids: [], after_node_ids: ['node-root'] } }, '后来发生');
  await writeNode(storyRoot, { ...base, node_id: 'prequel', creation_parent_id: 'future', relation: 'prequel',
    state_mode: 'reset', state_base: { kind: 'canon-baseline', id: 'canon-v1-initial' }, constraint_anchor_id: 'future',
    origin_branch_id: 'prequel', display_index: 1, created_at: '2026-01-02T00:00:00Z',
    story_time: { label: '更早', before_node_ids: ['future'], after_node_ids: [] } }, '更早发生');
  await writeJson(join(storyRoot, 'graph', 'branches', 'main.json'), { version: 4, story_id: 'story-test', branch_id: 'main', name: '主线', head_node_id: 'future', forked_from_node_id: 'node-root', status: 'open' });
  await writeJson(join(storyRoot, 'graph', 'branches', 'prequel.json'), { version: 4, story_id: 'story-test', branch_id: 'prequel', name: '前传', head_node_id: 'prequel', forked_from_node_id: 'future', status: 'open' });
  await writeFile(join(storyRoot, 'timeline', 'relations.jsonl'), JSON.stringify({ story_id: 'story-test', from_node_id: 'prequel', to_node_id: 'future', type: 'before' }) + '\n');
  return { root, dataRoot, displayRoot, storyRoot };
}

async function hashes(root: string) {
  const result: Record<string, string> = {};
  async function walk(dir: string) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) await walk(path);
      else result[relative(root, path)] = createHash('sha256').update(await readFile(path)).digest('hex');
    }
  }
  await walk(root);
  return result;
}

test('sync is source-read-only and orders a prequel before its creation parent', async () => {
  const f = await fixture();
  try {
    const before = await hashes(f.dataRoot);
    const snapshot = await syncStory({ storyId: 'story-test', dataRoot: f.dataRoot, displayRoot: f.displayRoot });
    assert.deepEqual(await hashes(f.dataRoot), before);
    assert.deepEqual(snapshot.chapters.map(chapter => chapter.id), ['prequel', 'future']);
    assert.equal(snapshot.chapters[0].creationParentId, 'future');
    assert.deepEqual(snapshot.graph.edges.map(edge => [edge.from, edge.to]), [['prequel', 'future']]);
    assert.deepEqual(snapshot.branches.map(branch => branch.id), ['main', 'prequel']);
    const saved = JSON.parse(await readFile(join(f.displayRoot, 'story-test', 'story.json'), 'utf8'));
    assert.deepEqual(saved, snapshot);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test('corrupt source manifest leaves the previous display snapshot intact', async () => {
  const f = await fixture();
  try {
    await mkdir(join(f.displayRoot, 'story-test'), { recursive: true });
    await writeFile(join(f.displayRoot, 'story-test', 'story.json'), '{"previous":true}\n', 'utf8');
    await writeFile(join(f.storyRoot, 'nodes', 'future', 'narrative.md'), 'tampered\n', 'utf8');
    await assert.rejects(syncStory({ storyId: 'story-test', dataRoot: f.dataRoot, displayRoot: f.displayRoot }), /hash/i);
    assert.equal(await readFile(join(f.displayRoot, 'story-test', 'story.json'), 'utf8'), '{"previous":true}\n');
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test('missing source default branch fails during sync and identifies the story', async () => {
  const f = await fixture();
  try {
    await writeJson(join(f.storyRoot, 'story.json'), { version: 4, id: 'story-test', title: '测试故事', default_branch_id: 'missing' });
    await assert.rejects(
      syncStory({ storyId: 'story-test', dataRoot: f.dataRoot, displayRoot: f.displayRoot }),
      /story-test：默认分支不存在：missing/,
    );
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
