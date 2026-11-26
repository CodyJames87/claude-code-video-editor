import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { HookProps } from '../types';
import { Highlighted } from './Highlighted';

/**
 * Big text hook, visible on frame 0 (no fade-in from black, so the first frame already reads).
 * 'top': upper safe area (top edge ~y 300 on 1080x1920, below the IG header). 'lower': bottom edge at y 1150 (caption zone,
 * captions are hidden during the hook) for wide/podcast shots where the face sits high. One accent word.
 */
export const HookText: React.FC<HookProps & { dur: number }> = ({ text, highlight, theme = 'light', position = 'top', dur, bottom, fontSize, maxWidth }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const c = themeColors(theme);
  const settle = spring({ frame, fps, config: { damping: 16, stiffness: 220, mass: 0.6 } });
  const scale = 0.96 + 0.04 * settle; // starts at 96 %, so frame 0 is already fully readable
  const exit = interpolate(frame, [dur - 6, dur], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const tall = height > width * 1.5;
  const lower = position === 'lower';
  const fs = fontSize ?? (tall ? (lower ? 96 : 88) : Math.round(Math.min(width, height) * 0.075));
  return (
    <AbsoluteFill
      style={{
        alignItems: 'center',
        justifyContent: lower ? 'flex-end' : 'flex-start',
        paddingTop: lower ? 0 : tall ? 300 : height * 0.08,
        paddingBottom: lower ? (tall ? height - (bottom ?? 1150) : height * 0.16) : 0,
      }}
    >
      <div
        style={{
          background: c.card,
          color: c.fg,
          border: `2px solid ${c.border}`,
          borderRadius: 28,
          padding: `${fs * 0.45}px ${fs * 0.6}px`,
          maxWidth: maxWidth ?? (tall ? 900 : '86%'),
          boxShadow: '0 18px 50px rgba(17,20,24,0.28)',
          transform: `scale(${scale})`,
          opacity: exit,
          textAlign: 'center',
        }}
      >
        <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs, lineHeight: 1.06, letterSpacing: '-0.025em' }}>
          <Highlighted text={text} highlight={highlight} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
