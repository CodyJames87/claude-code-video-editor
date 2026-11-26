import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { smoothstep } from './anim';

export type ZoomWindow = { startSec: number; duration: number; x: number; y: number; zoom?: number; ease?: number };

/**
 * Wraps the base video. During each window it pushes in toward (x,y) (0-1 of the frame),
 * holds, then eases back out. Zoom 2-2.5 for a detail, 1.15-1.25 for an emphasis push on a face.
 */
export const ZoomToDetail: React.FC<{ zooms: ZoomWindow[]; children: React.ReactNode }> = ({ zooms, children }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  let s = 1;
  let tx = 0;
  let ty = 0;
  for (const z of zooms) {
    const e = Math.max(0.04, z.ease ?? 0.3);
    const k = Math.min((t - z.startSec) / e, (z.startSec + z.duration - t) / e);
    if (k <= 0) continue;
    const eased = smoothstep(k);
    const zs = 1 + ((z.zoom ?? 2) - 1) * eased;
    const px = (z.x - 0.5) * width;
    const py = (z.y - 0.5) * height;
    // move the detail toward the center while scaling about the center
    s = zs;
    tx = px * (1 - eased - zs);
    ty = py * (1 - eased - zs);
    const mx = ((zs - 1) * width) / 2;
    const my = ((zs - 1) * height) / 2;
    tx = Math.max(-mx, Math.min(mx, tx));
    ty = Math.max(-my, Math.min(my, ty));
  }
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${tx}px, ${ty}px) scale(${s})`, transformOrigin: '50% 50%' }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};
