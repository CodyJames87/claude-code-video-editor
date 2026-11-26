import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, highlightWords } from '../../brand';
import type { TakeoverFrameProps } from '../../types';
import { BrowserFrame } from './BrowserFrame';
import { useDesign } from './design';

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9$%']/g, '');

/**
 * Takeover Frame: ONE full-screen moment per reel, video hidden. Kicker (DM Sans, neutral) + headline (Plus Jakarta
 * ExtraBold, ONE accent word). reveal "spoken": each headline word appears when he says it (`wordTimes` = seconds into
 * the overlay, matched from the transcript by EditedVideo). Text verbatim only. `graphic` = full-frame browser B-roll.
 */
export const TakeoverFrame: React.FC<TakeoverFrameProps & { dur: number; wordTimes?: Array<number | null> }> = ({
  text = '',
  highlight,
  kicker,
  theme = 'light',
  reveal = 'spoken',
  graphic,
  wordTimes = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { kx, ky, width, height } = useDesign();
  const t = frame / fps;
  const dark = theme === 'dark';
  const fg = dark ? BRAND.white : BRAND.ink;
  if (graphic) {
    return (
      <AbsoluteFill style={{ background: BRAND.ink, alignItems: 'center', justifyContent: 'center' }}>
        <BrowserFrame src={graphic.src} url={graphic.url} startFrom={graphic.startFrom} width={1000 * kx} height={Math.min(height * 0.62, 1200 * ky)} scale={kx} />
      </AbsoluteFill>
    );
  }
  const hl = new Set(highlightWords(text, highlight).filter((p) => p.hl).map((p) => norm(p.text)));
  const words = text.split(/\s+/).filter(Boolean);
  const fs = Math.round(width * 0.112);
  return (
    <AbsoluteFill style={{ background: dark ? BRAND.ink : BRAND.white, justifyContent: 'center', padding: `0 ${84 * kx}px` }}>
      <div style={{ width: 120 * kx, height: 9 * ky, borderRadius: 5, background: BRAND.accent, marginBottom: 34 * ky }} />
      {kicker ? (
        <div style={{ fontFamily: BRAND.bodyFont, fontWeight: 600, fontSize: 52 * ky, color: dark ? BRAND.hairline : BRAND.neutral, marginBottom: 22 * ky, fontStyle: 'normal' }}>{kicker}</div>
      ) : null}
      <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs, lineHeight: 1.04, letterSpacing: '-0.03em', color: fg, fontStyle: 'normal' }}>
        {words.map((w, i) => {
          const at = reveal === 'spoken' ? wordTimes[i] ?? 0 : 0;
          const k = Math.min(1, Math.max(0, (t - at) / (3 / fps)));
          return (
            <React.Fragment key={i}>
              {i ? ' ' : ''}
              <span style={{ display: 'inline-block', opacity: k, transform: `translateY(${(1 - k) * 18 * ky}px)`, color: hl.has(norm(w)) ? BRAND.accent : fg }}>{w}</span>
            </React.Fragment>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
