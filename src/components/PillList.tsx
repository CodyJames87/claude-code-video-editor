import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { PillListProps } from '../types';
import { enterExit } from './anim';

/** Short tags that pop in one by one; the newest pill is filled with the accent (accent). */
export const PillList: React.FC<PillListProps & { dur: number }> = ({ items, position = 'top', theme = 'light', dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = themeColors(theme);
  const fs = Math.round(width * (height > width ? 0.045 : 0.024));
  const stagger = Math.max(4, Math.min(14, Math.floor((dur * 0.6) / Math.max(1, items.length))));
  const newest = Math.min(items.length - 1, Math.floor(Math.max(0, frame) / stagger));
  return (
    <AbsoluteFill
      style={{
        alignItems: 'center',
        justifyContent: position === 'top' ? 'flex-start' : position === 'bottom' ? 'flex-end' : 'center',
        padding: position === 'top' ? `${height * 0.13}px 6% 0` : position === 'bottom' ? `0 6% ${height * 0.36}px` : '0 6%',
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: fs * 0.4 }}>
        {items.map((it, i) => {
          const a = enterExit(frame, fps, dur, i * stagger);
          const on = i === newest;
          return (
            <div key={i} style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs, color: on ? BRAND.white : t.fg, background: on ? BRAND.accent : t.card, border: `3px solid ${on ? BRAND.accent : t.border}`, borderRadius: 999, padding: `${fs * 0.28}px ${fs * 0.7}px`, opacity: a, transform: `scale(${0.6 + 0.4 * a})`, boxShadow: '0 10px 30px rgba(17,20,24,0.25)', letterSpacing: '-0.01em' }}>
              {it}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
