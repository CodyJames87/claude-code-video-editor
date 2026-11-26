import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { StatementCardProps } from '../types';
import { enterExit } from './anim';
import { Highlighted } from './Highlighted';

/** One bold statement on a Clean Line card. `full` = full-screen takeover. */
export const StatementCard: React.FC<StatementCardProps & { dur: number }> = ({ text, highlight, theme = 'light', position = 'top', kicker, dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = themeColors(theme);
  const a = enterExit(frame, fps, dur);
  const full = position === 'full';
  const fs = Math.round(Math.min(width, height) * (full ? 0.085 : 0.074));
  const card = (
    <div
      style={{
        background: t.card,
        color: t.fg,
        border: `2px solid ${t.border}`,
        borderRadius: full ? 0 : 28,
        padding: full ? '0 9%' : `${fs * 0.55}px ${fs * 0.7}px`,
        boxShadow: full ? 'none' : '0 18px 50px rgba(17,20,24,0.28)',
        maxWidth: full ? '100%' : '86%',
        width: full ? '100%' : undefined,
        height: full ? '100%' : undefined,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        transform: `translateY(${(1 - a) * 40}px) scale(${0.94 + 0.06 * a})`,
        opacity: a,
      }}
    >
      <div style={{ width: fs * 1.4, height: 8, borderRadius: 4, background: BRAND.accent, marginBottom: fs * 0.35 }} />
      {kicker ? (
        <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 600, fontSize: fs * 0.42, color: t.sub, marginBottom: fs * 0.2, letterSpacing: '0.02em', textTransform: 'uppercase' }}>
          {kicker}
        </div>
      ) : null}
      <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs, lineHeight: 1.08, letterSpacing: '-0.025em' }}>
        <Highlighted text={text} highlight={highlight} />
      </div>
    </div>
  );
  return (
    <AbsoluteFill
      style={{
        alignItems: 'center',
        justifyContent: position === 'center' || full ? 'center' : position === 'lower' ? 'flex-end' : 'flex-start',
        paddingTop: position === 'top' ? height * 0.12 : 0,
        // lower: card bottom at 70% of the height (inside the IG safe zone), clear of a face that sits high
        paddingBottom: position === 'lower' ? height * 0.3 : 0,
      }}
    >
      {card}
    </AbsoluteFill>
  );
};
