import type { Caption } from '@remotion/captions';
import { staticFile } from 'remotion';

const isUrl = (s: string) => /^(https?:|blob:|data:)/.test(s);
export const resolveSrc = (s: string) => (isUrl(s) ? s : staticFile(s.replace(/^\/?public\//, '')));

/** Load Caption[] from a public/ JSON file (or pass-through inline captions). */
export const loadCaptions = async (t: string | Caption[]): Promise<Caption[]> => {
  if (Array.isArray(t)) return t;
  if (!t) return [];
  const res = await fetch(resolveSrc(t));
  if (!res.ok) throw new Error(`Could not load transcript ${t}: ${res.status}`);
  const data = await res.json();
  const caps: Caption[] = Array.isArray(data) ? data : data.captions;
  if (!Array.isArray(caps)) throw new Error('Transcript must be Caption[] or {captions: Caption[]} (run npm run transcribe)');
  return caps;
};
