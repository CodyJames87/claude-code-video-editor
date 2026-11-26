// QC: fail (exit 1) if any on-screen caption block would show more than one accent word.
// Usage: node helpers/check-highlights.mjs props/podcast-<slug>.json [--list]
import fs from 'node:fs';
import path from 'node:path';
import { buildTwoLinePages, makeIsMoney, highlightMap, cleanWord } from '../src/captionLayout.js';

const propsPath = process.argv[2];
if (!propsPath) { console.error('usage: node helpers/check-highlights.mjs props/<name>.json [--list]'); process.exit(2); }
const p = JSON.parse(fs.readFileSync(propsPath, 'utf8'));
const cap = p.captions || {};
// Karaoke Captions use the lowerThird layout + the same ONE-money-word pick (the lit active word is not an accent)
const layoutMode = cap.mode === 'karaoke' || cap.karaoke ? 'lowerThird' : cap.mode;
if (cap.enabled === false || (layoutMode && layoutMode !== 'lowerThird')) { console.log('HIGHLIGHTS: skipped (not lowerThird/karaoke captions)'); process.exit(0); }
const tj = p.transcriptJson;
const captions = JSON.parse(fs.readFileSync(path.join('public', tj), 'utf8'));
const trim = (p.trim && (p.trim.start ?? p.trim.startSec)) || 0;
const pages = buildTwoLinePages(captions, cap.maxWords ?? 4, cap.maxLineChars ?? 18, cap.skipWords ?? [], cap.oneLineRanges ?? [], trim);
const isMoney = makeIsMoney(cap.moneyWords ?? []);
let bad = 0;
for (const pg of pages) {
  // independent count: what the renderer will paint (highlightMap) AND a raw count of money words on screen
  let flags;
  try { flags = highlightMap(pg, isMoney); } catch (e) { bad++; console.log('FAIL', e.message); continue; }
  const accent = pg.lines.flatMap((l, li) => l.words.filter((_, wi) => flags[li][wi]).map((w) => cleanWord(w.text)));
  const raw = pg.lines.flatMap((l) => l.words.filter((w) => isMoney(w.text)).map((w) => cleanWord(w.text)));
  if (accent.length > 1) { bad++; console.log(`FAIL ${(pg.startMs / 1000 - trim).toFixed(2)}s accent=${accent.join(',')}`); }
  if (process.argv.includes('--list') || raw.length > 1)
    console.log(`${(pg.startMs / 1000 - trim).toFixed(2)}s | ${pg.lines.map((l) => l.words.map((w) => cleanWord(w.text)).join(' ')).join(' / ')} | accent: ${accent.join(',') || '-'}${raw.length > 1 ? `  (money matches ${raw.join(',')} -> one kept)` : ''}`);
}
// Talking-head motion layout guard: no PushIn/PunchIn over a Split/Takeover Frame, at most ONE Takeover Frame.
const nrm = (x) => x.toLowerCase().replace(/[^a-z0-9$%']/g, '');
const startOf = (o) => {
  if (typeof o.at === 'number') return o.at;
  const tgt = o.at.word.split(/\s+/).map(nrm).filter(Boolean);
  const ws = captions.map((c) => nrm(c.text));
  let seen = 0;
  for (let i = 0; i < ws.length; i++) if (tgt.every((t, k) => ws[i + k] === t) && ++seen === (o.at.occurrence ?? 1)) return captions[i].startMs / 1000 - trim + (o.at.offset ?? 0);
  console.log(`FAIL anchor not found: "${o.at.word}" (${o.type})`); bad++; return 0;
};
const ovs = (p.overlays ?? []).map((o) => ({ ...o, s: startOf(o) }));
const frames = ovs.filter((o) => o.type === 'SplitFrame' || o.type === 'TakeoverFrame');
for (const m of ovs.filter((o) => o.type === 'PushIn' || o.type === 'PunchIn'))
  for (const f of frames)
    if (m.s < f.s + f.duration && f.s < m.s + m.duration - 1e-3) { bad++; console.log(`FAIL ${m.type} @${m.s.toFixed(2)}s overlaps ${f.type} @${f.s.toFixed(2)}s (no camera moves on a split/takeover)`); }
if (ovs.filter((o) => o.type === 'TakeoverFrame').length > 1) { bad++; console.log('FAIL more than one TakeoverFrame (one per reel)'); }

console.log(bad ? `HIGHLIGHTS: FAIL (${bad} issue(s): caption blocks with >1 accent word, or layout conflicts)` : `HIGHLIGHTS: PASS (${pages.length} caption blocks, max 1 accent word each)`);
process.exit(bad ? 1 : 0);
