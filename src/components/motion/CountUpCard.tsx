import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import type { CountUpCardProps } from '../../types';
import { enterExit } from '../anim';
import { SLOT_Y, useDesign } from './design';

const easeOut = (k: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, k)), 3);

/**
 * Count-Up Card: a white card that counts up to a number the speaker SAYS and lands on it as he says it (`landSec` into the
 * overlay). The number is the one accent (Plus Jakarta ExtraBold); kicker in DM Sans neutral; unit in ink.
 * Sits in the top headroom band by default (face-safe by layout). Verbatim only: `to` must be spoken.
 */
export const CountUpCard: React.FC<CountUpCardProps & { dur: number }> = ({ to, from = 0, landSec = 0.4, numberSize = 96, kicker, unit, y = SLOT_Y, prefix = '', suffix = '', dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { ky } = useDesign();
  const t = frame / fps;
  const a = enterExit(frame, fps, dur, 0, 6);
  const k = landSec > 0 ? Math.min(1, t / landSec) : 1;
  const v = k >= 1 ? to : Math.floor(from + (to - from) * easeOut(k));
  const pop = t >= landSec ? 1 + 0.1 * Math.max(0, 1 - (t - landSec) / 0.18) : 1;
  const num = numberSize * ky;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: y * ky,
          transform: `translateY(-50%) scale(${0.94 + 0.06 * a})`,
          display: 'flex',
          justifyContent: 'center',
          opacity: a,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 22 * ky,
            background: BRAND.white,
            borderRadius: 24 * ky,
            padding: `${8 * ky}px ${34 * ky}px`,
            boxShadow: '0 12px 34px rgba(0,0,0,0.30)',
          }}
        >
          {kicker ? (
            <div style={{ fontFamily: BRAND.bodyFont, fontWeight: 600, fontSize: numberSize * 0.36 * ky, color: BRAND.neutral, textTransform: 'uppercase', letterSpacing: '0.06em', fontStyle: 'normal' }}>
              {kicker}
            </div>
          ) : null}
          <div
            style={{
              fontFamily: BRAND.headlineFont,
              fontWeight: 800,
              fontSize: num,
              lineHeight: 1.1,
              color: BRAND.accent,
              fontVariantNumeric: 'tabular-nums',
              letterSpacing: '-0.03em',
              transform: `scale(${pop})`,
              minWidth: num * 1.2,
              textAlign: 'center',
              fontStyle: 'normal',
            }}
          >
            {prefix}
            {v}
            {suffix}
          </div>
          {unit ? (
            <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: numberSize * 0.48 * ky, color: BRAND.ink, textTransform: 'uppercase', letterSpacing: '-0.01em', fontStyle: 'normal' }}>
              {unit}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
