import React, { useMemo } from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { createTikTokStyleCaptions, type Caption, type TikTokToken } from '@remotion/captions';
import { BRAND } from '../brand';
import { buildTwoLinePages, cleanWord, makeIsMoney, highlightMap } from '../captionLayout';

type Chunk = { startMs: number; endMs: number; tokens: TikTokToken[] };

/** Build 2-4 word lines from @remotion/captions pages. */
export const buildChunks = (captions: Caption[], maxWords = 4): Chunk[] => {
  const { pages } = createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: 1400 });
  const chunks: Chunk[] = [];
  for (const p of pages) {
    const toks = p.tokens.filter((t) => t.text.trim());
    let cur: TikTokToken[] = [];
    const flush = () => {
      if (cur.length) chunks.push({ startMs: cur[0].fromMs, endMs: cur[cur.length - 1].toMs, tokens: cur });
      cur = [];
    };
    toks.forEach((t) => {
      const chars = cur.reduce((n, x) => n + x.text.trim().length + 1, 0) + t.text.trim().length;
      if (cur.length >= maxWords || (cur.length >= 2 && chars > 16)) flush();
      cur.push(t);
      if (/[.!?]$/.test(t.text.trim())) flush();
    });
    flush();
  }
  // hold each line until the next starts (max +350 ms) so nothing flickers
  return chunks.map((c, i) => ({ ...c, endMs: Math.min(c.endMs + 350, chunks[i + 1]?.startMs ?? c.endMs + 350) }));
};

export type CaptionsProps = {
  captions: Caption[];
  trimStartSec?: number;
  mode?: 'active' | 'keyword' | 'lowerThird' | 'karaoke';
  karaoke?: boolean; // Karaoke Captions: lowerThird layout + the active spoken word lit (white + small scale pop)
  keywords?: string[];
  moneyWords?: string[];
  maxWords?: number;
  maxLineChars?: number;
  skipWords?: string[];
  hidden?: Array<[number, number]>; // timeline seconds where captions hide
  bottomRanges?: Array<{ from: number; to: number; bottom: number; byFrame?: boolean }>; // lowerThird 9:16: block bottom y per timeline range
  oneLineRanges?: Array<{ from: number; to: number }>; // lowerThird: pages starting in these timeline ranges show ONE line
};

const NO_RANGES: Array<{ from: number; to: number }> = [];

// Layout + highlight logic lives in ../captionLayout.js (shared with helpers/check-highlights.mjs).
export { buildTwoLinePages };

/** the default: two short Anton lines in the lower third (inside the IG Reels safe zone), ONE money word per caption block in the accent color. */
const LowerThirdCaptions: React.FC<CaptionsProps> = ({ captions, trimStartSec = 0, moneyWords = [], maxWords = 4, maxLineChars = 18, skipWords = [], hidden = [], bottomRanges = [], oneLineRanges = NO_RANGES, karaoke = false }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const pages = useMemo(
    () => buildTwoLinePages(captions, maxWords, maxLineChars, skipWords, oneLineRanges, trimStartSec),
    [captions, maxWords, maxLineChars, skipWords, oneLineRanges, trimStartSec],
  );
  const tSec = frame / fps;
  if (hidden.some(([a, b]) => tSec >= a && tSec < b)) return null;
  const t = (tSec + trimStartSec) * 1000;
  const page = pages.find((p) => t >= p.startMs && t < p.endMs);
  if (!page) return null;
  const tall = height > width * 1.5;
  const vertical = height > width;
  // 9:16: block bottom at y=1150 (above the IG like/comment rail that starts ~1150 px down, and above the bottom 35%).
  const fs = tall ? 84 : vertical ? 76 : 64;
  // optional override: the page's start time picks the range, so a page never jumps mid-display
  const pageSec = page.startMs / 1000 - trimStartSec;
  // byFrame: the current time decides instead, so a page straddling a hard layout cut moves exactly at the cut
  const ovr = tall ? bottomRanges.find((r) => { const s = r.byFrame ? tSec : pageSec; return s >= r.from && s < r.to; }) : undefined;
  const bottom = tall ? height - (ovr?.bottom ?? 1150) : vertical ? Math.round(height * 0.16) : 80;
  const isMoney = makeIsMoney(moneyWords);
  // ONE accent word per on-screen caption block (last money word wins); throws -> render fails if ever >1
  const flags = highlightMap(page, isMoney);
  const pop = 1 + 0.04 * Math.max(0, 1 - (t - page.startMs) / 100); // <= 104 %, settles in ~3 frames
  // karaoke: the active word = the last word of this block that has started
  const activeWord = karaoke ? page.lines.flatMap((l) => l.words).reduce<Caption | null>((acc, w) => (t >= w.startMs ? w : acc), null) : null;
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottom, paddingLeft: 110, paddingRight: 110 }}>
      <div
        style={{
          fontFamily: BRAND.captionFont,
          fontSize: fs,
          lineHeight: 1.08,
          textTransform: 'uppercase',
          color: BRAND.white,
          WebkitTextStroke: `${Math.round(fs * 0.11)}px ${BRAND.ink}`,
          paintOrder: 'stroke fill',
          textShadow: `0 ${Math.round(fs * 0.04)}px ${Math.round(fs * 0.1)}px rgba(17,20,24,0.55)`,
          textAlign: 'center',
          transform: `scale(${pop})`,
          transformOrigin: '50% 100%',
          letterSpacing: '0.01em',
          fontStyle: 'normal',
        }}
      >
        {page.lines.map((line, li) => {
          if (!karaoke) {
            return (
              <div key={li}>
                {line.words.map((w, i) => (
                  <span key={i} style={{ color: flags[li][i] ? BRAND.accent : BRAND.white }}>
                    {(i ? ' ' : '') + cleanWord(w.text)}
                  </span>
                ))}
              </div>
            );
          }
          // Karaoke Captions: the word being spoken is "lit" (pure white, or the accent color if it IS the money word) with a short
          // scale pop (1.08 -> 1.05); the rest sit at hairline white #E5E5E5. The ONE money word stays in the accent at
          // rest for the whole block (same pick as lowerThird, so check-highlights.mjs still holds). Never a 2nd accent.
          return (
            <div key={li}>
              {line.words.map((w, i) => {
                const lit = w === activeWord;
                const money = flags[li][i];
                const s = lit ? 1.05 + 0.03 * Math.max(0, 1 - (t - w.startMs) / 120) : 1;
                return (
                  <React.Fragment key={i}>
                    {i ? ' ' : ''}
                    <span style={{ display: 'inline-block', color: money ? BRAND.accent : lit ? BRAND.white : BRAND.hairline, transform: `scale(${s})`, transformOrigin: '50% 75%' }}>
                      {cleanWord(w.text)}
                    </span>
                  </React.Fragment>
                );
              })}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Clean Line captions: Anton uppercase, white with ink outline, active (or key) word in the accent color. */
export const Captions: React.FC<CaptionsProps> = (props) => {
  if (props.mode === 'karaoke') return <LowerThirdCaptions {...props} karaoke />;
  if (props.mode === 'lowerThird') return <LowerThirdCaptions {...props} />;
  return <WordCaptions {...props} />;
};

const WordCaptions: React.FC<CaptionsProps> = ({ captions, trimStartSec = 0, mode = 'active', keywords = [], maxWords = 4, hidden = [] }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const chunks = useMemo(() => buildChunks(captions, maxWords), [captions, maxWords]);
  const tSec = frame / fps;
  if (hidden.some(([a, b]) => tSec >= a && tSec < b)) return null;
  const t = (tSec + trimStartSec) * 1000;
  const chunk = chunks.find((c) => t >= c.startMs && t < c.endMs);
  if (!chunk) return null;
  const vertical = height > width;
  const fs = vertical ? (height > width * 1.5 ? 132 : 112) : 92;
  const bottom = vertical ? (height > width * 1.5 ? 600 : 250) : 110;
  const kws = keywords.map((k) => k.toLowerCase());
  const isKey = (s: string) => {
    const w = s.toLowerCase().replace(/[^a-z0-9$%']/g, '');
    return kws.length ? kws.some((k) => w === k || w.startsWith(k)) : /\d|\$/.test(s);
  };
  // active word = the last token that has started
  const activeIdx = chunk.tokens.reduce((acc, tok, i) => (t >= tok.fromMs ? i : acc), 0);
  const sinceStart = t - chunk.startMs;
  const pop = 1 + 0.08 * Math.max(0, 1 - sinceStart / 90);
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottom, paddingLeft: 70, paddingRight: 70 }}>
      <div
        style={{
          fontFamily: BRAND.captionFont,
          fontSize: fs,
          lineHeight: 1.1,
          textTransform: 'uppercase',
          color: BRAND.white,
          WebkitTextStroke: `${Math.round(fs * 0.11)}px ${BRAND.ink}`,
          paintOrder: 'stroke fill',
          textShadow: `0 ${Math.round(fs * 0.04)}px ${Math.round(fs * 0.08)}px rgba(17,20,24,0.6)`,
          textAlign: 'center',
          transform: `scale(${pop})`,
          letterSpacing: '0.01em',
          fontStyle: 'normal',
        }}
      >
        {chunk.tokens.map((tok, i) => {
          const active = mode === 'active' ? i === activeIdx : isKey(tok.text);
          return (
            <span key={i} style={{ color: active ? BRAND.accent : BRAND.white }}>
              {(i ? ' ' : '') + tok.text.trim().replace(/^["'“”]+|["“”]+$/g, '')}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
