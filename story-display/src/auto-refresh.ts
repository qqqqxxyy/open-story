import { shouldRefreshStory } from './refresh-policy.ts';
import type { VersionMessage } from './refresh-policy.ts';
interface ReadingPosition {
  hash: string; savedAt: number; windowX: number; windowY: number;
  readingKey?:string;
  detailTab?: 'text' | 'info';
  scrolls: {selector:string;top:number;left:number}[];
}
declare global {
  interface Window { storyDisplayVersionReceived?: (value: VersionMessage) => void }
}
const storageKey = `story-display:reload:${location.pathname}`;
const scrollSelectors = ['.detail-scroll','.chapter-list','.warnings'];

function readPosition(): ReadingPosition | null {
  try {
    const value = sessionStorage.getItem(storageKey);
    return value ? JSON.parse(value) : history.state?.storyDisplayReadingPosition ?? null;
  } catch { return history.state?.storyDisplayReadingPosition ?? null; }
}
// Read before React normalizes the URL. State is consumed only on this page load.
const pendingPosition = readPosition();
let positionConsumed = false;

export function restoredDetailTab(chapterId: string,readingKey?:string): 'text' | 'info' {
  const saved = pendingPosition;
  return saved && Date.now()-saved.savedAt <= 60_000 &&
    (new URLSearchParams(saved.hash.slice(1)).get('chapter') === chapterId || (readingKey && saved.readingKey===readingKey)) && saved.detailTab === 'info' ? 'info' : 'text';
}

export function restoreReadingPosition(hash: string,readingKey?:string): void {
  if (positionConsumed) return;
  positionConsumed = true;
  try { sessionStorage.removeItem(storageKey); } catch { /* file storage is browser-dependent */ }
  try {
    const {storyDisplayReadingPosition: _saved, ...state} = history.state ?? {};
    history.replaceState(state,'');
  } catch { /* ignore unavailable history storage */ }
  const saved = pendingPosition;
  const oldParams=new URLSearchParams(saved?.hash.slice(1)),newParams=new URLSearchParams(hash.slice(1));
  const sameScene=!!readingKey && saved?.readingKey===readingKey && oldParams.get('story')===newParams.get('story') && oldParams.get('branch')===newParams.get('branch');
  if (!saved || (saved.hash !== hash && !sameScene) || !Number.isFinite(saved.savedAt) || Date.now()-saved.savedAt > 60_000) return;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (location.hash !== hash) return;
    for (const position of saved.scrolls ?? []) {
      if (!scrollSelectors.includes(position.selector)) continue;
      const element = document.querySelector<HTMLElement>(position.selector);
      if (element && Number.isFinite(position.top) && Number.isFinite(position.left)) {
        element.scrollTo({top:position.top,left:position.left,behavior:'instant'});
      }
    }
    if (Number.isFinite(saved.windowX) && Number.isFinite(saved.windowY)) {
      window.scrollTo({left:saved.windowX,top:saved.windowY,behavior:'instant'});
    }
  }));
}

function saveReadingPosition(): void {
  const saved: ReadingPosition = {hash:location.hash,savedAt:Date.now(),windowX:window.scrollX,windowY:window.scrollY,
    readingKey:document.querySelector<HTMLElement>('.detail-panel')?.dataset.readingKey,
    detailTab: document.querySelector('.tabs button.active')?.textContent === '章节信息' ? 'info' : 'text',
    scrolls:scrollSelectors.flatMap(selector => {
      const element = document.querySelector<HTMLElement>(selector);
      return element ? [{selector,top:element.scrollTop,left:element.scrollLeft}] : [];
    })};
  try { sessionStorage.setItem(storageKey,JSON.stringify(saved)); } catch { /* keep history fallback */ }
  try { history.replaceState({...history.state,storyDisplayReadingPosition:saved},''); } catch { /* still readable */ }
}

/** Classic local scripts work without fetch/CORS or a service process. */
export function startAutoRefresh(revision: string, loadedStories: Record<string,string> = {}): () => void {
  if (!/^[a-f0-9]{64}$/.test(revision)) return () => {};
  let active: HTMLScriptElement | null = null;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let reloading = false;
  let serial = 0;
  const previous = window.storyDisplayVersionReceived;
  function cleanup() {
    if (timeout !== undefined) clearTimeout(timeout);
    timeout = undefined;
    active?.remove(); active = null;
  }
  window.storyDisplayVersionReceived = value => {
    // Ignore stale, unrelated or malformed script callbacks.
    if (!active || document.currentScript !== active || !value || 
        typeof value.contentRevision !== 'string' || !/^[a-f0-9]{64}$/.test(value.contentRevision)) return;
    const slug = new URLSearchParams(location.hash.slice(1)).get('story');
    if (!shouldRefreshStory(loadedStories,value,slug) || reloading) return;
    reloading = true; saveReadingPosition(); cleanup(); location.reload();
  };
  function check() {
    if (document.hidden || active || reloading) return;
    const script = document.createElement('script');
    script.src = new URL(`display-version.js?check=${Date.now()}-${++serial}`,location.href).href;
    script.async = true; active = script;
    script.onload = script.onerror = cleanup;
    timeout = setTimeout(cleanup,8_000);
    document.head.append(script);
  }
  const interval = setInterval(check,2_500);
  const onVisibility = () => { if (!document.hidden) check(); };
  document.addEventListener('visibilitychange',onVisibility);
  check();
  return () => {
    clearInterval(interval); cleanup();
    document.removeEventListener('visibilitychange',onVisibility);
    window.storyDisplayVersionReceived = previous;
  };
}
