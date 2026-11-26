import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import type { TitleBannerProps } from '../../types';
import { enterExit } from '../anim';
import { Highlighted } from '../Highlighted';
import { SLOT_Y, useDesign } from './design';

/** Title Banner: one short verbatim line in the top headroom band, Plus Jakarta Sans ExtraBold, ONE accent word. */
export const TitleBanner: React.FC<TitleBannerProps & { dur: number }> = ({ text, highlight, y = SLOT_Y, fontSize = 60, instantIn, theme = 'onInk', dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { ky, kx } = useDesign();
  // instantIn: fully on at frame 0 (the hook frame must be readable), still exits softly
  const a = instantIn
    ? interpolate(frame, [dur - 8, dur], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
    : enterExit(frame, fps, dur);
  const fs = fontSize * ky;
  const card = theme === 'card';
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: 50 * kx,
          right: 50 * kx,
          top: y * ky,
          transform: `translateY(-50%) translateY(${(1 - a) * -12 * ky}px)`,
          display: 'flex',
          justifyContent: 'center',
          opacity: a,
        }}
      >
        <div
          style={{
            fontFamily: BRAND.headlineFont,
            fontWeight: 800,
            fontSize: fs,
            lineHeight: 1.08,
            letterSpacing: '-0.02em',
            textAlign: 'center',
            fontStyle: 'normal',
            color: card ? BRAND.ink : BRAND.white,
            background: card ? BRAND.white : 'transparent',
            borderRadius: card ? 18 * ky : 0,
            padding: card ? `${fs * 0.22}px ${fs * 0.45}px` : 0,
          }}
        >
          <Highlighted text={text} highlight={highlight} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
