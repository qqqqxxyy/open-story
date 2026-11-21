export interface VersionMessage {
  contentRevision: string;
  storyRevisions?: Record<string, string>;
}
const digest = /^[a-f0-9]{64}$/;

/** Compare against the data loaded with this HTML, never a later polling baseline. */
export function shouldRefreshStory(loaded: Record<string,string>, marker: VersionMessage, slug: string | null): boolean {
  if (!slug || !marker || !marker.storyRevisions ||
      typeof marker.storyRevisions !== 'object' || Array.isArray(marker.storyRevisions) ||
      !Object.hasOwn(loaded,slug) || !digest.test(loaded[slug])) return false;
  if (!Object.hasOwn(marker.storyRevisions,slug)) return true; // current story removed
  const latest = marker.storyRevisions[slug];
  return typeof latest === 'string' && digest.test(latest) && latest !== loaded[slug];
}
