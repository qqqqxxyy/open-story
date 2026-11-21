export interface EdgeRecord { id: string; from: string; to: string; label?: string; kind?: 'timeline' }
export interface GraphRecord { storyId: string; entryNodeIds: string[]; edges: EdgeRecord[] }
export interface Chapter {
  display?: {key:string; revision:string; pending:boolean; previewId?:string};
  id: string; storyId: string; turn: number; file: string; title: string;
  narrative: string; summary: string; location: string; time: string;
  participants: string[]; input: string; intent: string; raw: Record<string, unknown>;
  timelineOrder: number; creationIndex: number; creationParentId: string | null;
  relation: string; branchIds: string[];
}
export interface BranchRecord { id: string; name: string; headNodeId: string; status: string; nodeIds: string[] }
export interface Story {
  source_kind: 'file_story' | 'open_story'; syncedAt: string;
  slug: string; title: string; id: string; chapters: Chapter[];
  graph: GraphRecord; branches: BranchRecord[]; defaultBranchId: string; warnings: string[];
}
/** One-time viewer maintenance; never part of authoring data or creative APIs. */
export interface ReadingUpdateRepair {
  id:string; storyId:string;
  chapters:{nodeId:string; key:string; revision:string; legacyRevision:string}[];
}
export interface StoryBundle {
  generatedAt:string; stories:Story[]; readingUpdateRepairs?:ReadingUpdateRepair[];
}
