import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import { BAR_Y, useDesign } from './design';

export type ProgressBarCfg = { enabled?: boolean; position?: 'topSafe' | 'bottom'; y?: number; height?: number; inset?: number; track?: 'hairline' | 'pale' };

/**
 * Progress Bar: a thin accent-color fill on a subtle hairline (#E5E5E5) or pale (#CAE6FC) track, elapsed / total.
 * topSafe = y 226 on 1080x1920: below the Reels top UI, inside the Solo Frame ink headroom band, above the cap.
 */
export const ProgressBar: React.FC<ProgressBarCfg> = ({ position = 'topSafe', y, height = 7, inset = 60, track = 'hairline' }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const { ky, kx, height: H } = useDesign();
  const p = Math.min(1, Math.max(0, (frame + 1) / durationInFrames));
  const top = position === 'bottom' ? H - (y ?? 120) * ky : (y ?? BAR_Y) * ky;
  const h = Math.max(4, Math.round(height * ky));
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{ position: 'absolute', left: inset * kx, right: inset * kx, top, height: h, borderRadius: h, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, background: track === 'pale' ? BRAND.paleFill : BRAND.hairline, opacity: 0.32 }} />
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${p * 100}%`, background: BRAND.accent, borderRadius: h }} />
      </div>
    </AbsoluteFill>
  );
};
