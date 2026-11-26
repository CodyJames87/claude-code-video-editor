import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { FullScreenListProps } from '../types';
import { enterExit } from './anim';
import { Highlighted } from './Highlighted';

/** Full-screen takeover list: title, then numbered items stagger in. */
export const FullScreenList: React.FC<FullScreenListProps & { dur: number }> = ({ title, items, theme = 'dark', highlight, dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = themeColors(theme);
  const fs = Math.round(Math.min(width, height * 0.75) * 0.066);
  const bgA = enterExit(frame, fps, dur, 0, 6);
  const stagger = Math.max(4, Math.min(12, Math.floor((dur * 0.5) / Math.max(1, items.length))));
  return (
    <AbsoluteFill style={{ background: t.bg, opacity: bgA, justifyContent: 'center', padding: '0 9%' }}>
      <div style={{ width: fs * 1.6, height: 10, borderRadius: 5, background: BRAND.accent, marginBottom: fs * 0.5 }} />
      <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 1.2, color: t.fg, letterSpacing: '-0.03em', lineHeight: 1.05, marginBottom: fs * 0.8 }}>
        <Highlighted text={title} highlight={highlight} />
      </div>
      {items.map((it, i) => {
        const a = enterExit(frame, fps, dur, 6 + i * stagger);
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: fs * 0.5, marginBottom: fs * 0.45, opacity: a, transform: `translateX(${(1 - a) * -40}px)` }}>
            <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 0.95, color: BRAND.accent, minWidth: fs * 1.1 }}>{String(i + 1).padStart(2, '0')}</div>
            <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 700, fontSize: fs * 0.95, color: t.fg, lineHeight: 1.15 }}>{it}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
