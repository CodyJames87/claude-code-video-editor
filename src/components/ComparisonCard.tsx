import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { ComparisonCardProps, ComparisonSide } from '../types';
import { enterExit } from './anim';

/** Side-by-side (or stacked on vertical) comparison. Only the winner gets the accent color. */
export const ComparisonCard: React.FC<ComparisonCardProps & { dur: number }> = ({ title, left, right, winner = 'right', theme = 'light', dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = themeColors(theme);
  const vertical = height > width * 1.1;
  const fs = Math.round(width * (vertical ? 0.048 : 0.026));
  const side = (s: ComparisonSide, i: number, win: boolean) => {
    const a = enterExit(frame, fps, dur, i * 8);
    return (
      <div key={i} style={{ flex: 1, background: t.card, border: `3px solid ${win ? BRAND.accent : t.border}`, borderRadius: 26, padding: fs * 0.8, opacity: a, transform: `translateY(${(1 - a) * 30}px)`, boxShadow: '0 14px 40px rgba(17,20,24,0.25)', position: 'relative' }}>
        <div style={{ display: 'inline-block', fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 0.55, letterSpacing: '0.04em', textTransform: 'uppercase', color: win ? BRAND.white : t.sub, background: win ? BRAND.accent : 'transparent', border: win ? 'none' : `2px solid ${t.border}`, borderRadius: 999, padding: `${fs * 0.15}px ${fs * 0.45}px` }}>{s.label}</div>
        {s.value ? <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 1.7, color: win ? BRAND.accent : t.fg, marginTop: fs * 0.35, letterSpacing: '-0.03em' }}>{s.value}</div> : null}
        {(s.points ?? []).map((p, j) => (
          <div key={j} style={{ fontFamily: BRAND.headlineFont, fontWeight: 600, fontSize: fs * 0.72, color: t.fg, marginTop: fs * 0.3, lineHeight: 1.2 }}>• {p}</div>
        ))}
      </div>
    );
  };
  const a = enterExit(frame, fps, dur);
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: vertical ? '86%' : '82%' }}>
        {title ? <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 1.1, color: BRAND.white, textShadow: '0 4px 18px rgba(17,20,24,0.8)', marginBottom: fs * 0.6, opacity: a, textAlign: 'center', letterSpacing: '-0.02em' }}>{title}</div> : null}
        <div style={{ display: 'flex', flexDirection: vertical ? 'column' : 'row', gap: fs * 0.6 }}>
          {side(left, 0, winner === 'left')}
          {side(right, 1, winner === 'right')}
        </div>
      </div>
    </AbsoluteFill>
  );
};
