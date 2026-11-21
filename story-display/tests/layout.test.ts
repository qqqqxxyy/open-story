import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { Story } from '../src/model/types.ts';
import { layoutStory } from '../src/graph/layout.ts';

function chapter(id: string, timelineOrder: number, creationIndex: number) {
  return { id, storyId: 'story-test', turn: timelineOrder + 1, file: '', title: id, narrative: id, summary: id,
    location: '', time: '', participants: [], input: '', intent: '', raw: {}, timelineOrder, creationIndex,
    creationParentId: null, relation: 'continuation', branchIds: ['main'] };
}

test('layout uses story chronology even when creation and array order disagree', () => {
  const story: Story = { source_kind: 'file_story', syncedAt: '2026-09-16T00:00:00Z', slug: 'story-test', id: 'story-test', title: '测试',
    chapters: [chapter('future', 1, 1), chapter('prequel', 0, 2)],
    graph: { storyId: 'story-test', entryNodeIds: ['prequel'], edges: [{ id: 'time', from: 'prequel', to: 'future', kind: 'timeline' }] },
    branches: [{ id: 'main', name: '主线', headNodeId: 'prequel', status: 'active', nodeIds: ['prequel', 'future'] }], defaultBranchId: 'main', warnings: [] };
  const { nodes, edges } = layoutStory(story); const positions = new Map(nodes.map(node => [node.id, node.position.x]));
  assert.ok(positions.get('prequel')! < positions.get('future')!); assert.equal(edges.length, 1);
  assert.equal(JSON.stringify(story.chapters.map(item => item.id)), JSON.stringify(['future', 'prequel']));
});
