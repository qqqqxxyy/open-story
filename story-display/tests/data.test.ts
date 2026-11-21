import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadStory, validateStorySnapshot } from '../scripts/data.ts';

function chapter(id: string, timelineOrder: number) {
  return { id, storyId: 'story-test', turn: timelineOrder + 1, file: `nodes/${id}/narrative.md`, title: id,
    narrative: `正文 ${id}`, summary: id, location: '', time: '', participants: [], input: '', intent: '', raw: {},
    timelineOrder, creationIndex: timelineOrder + 1, creationParentId: null, relation: 'continuation', branchIds: ['main'] };
}
function snapshot() {
  return { source_kind: 'file_story', syncedAt: '2026-09-16T00:00:00Z', slug: 'story-test', id: 'story-test', title: '测试故事',
    chapters: [chapter('later', 1), chapter('earlier', 0)],
    graph: { storyId: 'story-test', entryNodeIds: ['earlier'], edges: [{ id: 'time', from: 'earlier', to: 'later', kind: 'timeline' }] },
    branches: [{ id: 'main', name: '主线', headNodeId: 'later', status: 'active', nodeIds: ['later', 'earlier'] }],
    defaultBranchId: 'main', warnings: [] };
}

test('v4 display snapshot loads chapters and branch nodes in story-time order', async () => {
  const root = await mkdtemp(join(tmpdir(), 'story-display-')); const dir = join(root, 'story-test');
  try { await mkdir(dir); await writeFile(join(dir, 'story.json'), JSON.stringify(snapshot())); const story = await loadStory(dir);
    assert.deepEqual(story.chapters.map(item => item.id), ['earlier', 'later']);
    assert.deepEqual(story.branches[0].nodeIds, ['earlier', 'later']);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('snapshot validation rejects mismatched identity, duplicate chronology and missing endpoints', () => {
  assert.throws(() => validateStorySnapshot({ ...snapshot(), id: 'other' }, 'story-test'), /目录、id/);
  const duplicate = snapshot(); duplicate.chapters[1].timelineOrder = 1;
  assert.throws(() => validateStorySnapshot(duplicate, 'story-test'), /timelineOrder/);
  const missing = snapshot(); missing.graph.edges[0].to = 'missing';
  assert.throws(() => validateStorySnapshot(missing, 'story-test'), /端点不存在/);
});

test('snapshot validation rejects branches that reference absent nodes', () => {
  const value = snapshot(); value.branches[0].nodeIds.push('missing');
  assert.throws(() => validateStorySnapshot(value, 'story-test'), /分支 main.*不存在/);
});
