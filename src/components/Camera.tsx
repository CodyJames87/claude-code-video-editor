import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';

/** 'eased' = Eased Push (cubic ease-in-out, default). 'crawl' = Steady Crawl (linear, no easing). */
export type PushStyle = 'eased' | 'crawl';

/** Steady Crawl rate: scale units per second. */
export const CRAWL_RATE = 0.048;

export type CameraMove =
  | { kind: 'push'; startSec: number; duration: number; to?: number; x?: number; y?: number; outFrames?: number; style?: PushStyle; holdSec?: number }
  | { kind: 'punch'; startSec: number; duration: number; to?: number; x?: number; y?: number; inFrames?: number; outFrames?: number };

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeInOut = (k: number) => {
  const x = clamp01(k);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; // cubic in-out
};
const easeOut = (k: number) => 1 - Math.pow(1 - clamp01(k), 3);

/**
 * Scale of one move at time t (seconds), or 1 when it is not active.
 * push 'eased' (default): 1 -> to (default 1.08) with cubic ease-in-out across the window.
 * push 'crawl': 1 -> to LINEARLY (default to = 1 + 0.048 * duration). Both snap back out over outFrames (default 4).
 * push holdSec (optional, default 0): hold the peak after the window before the out-ease.
 */
export const moveScale = (m: CameraMove, t: number, fps: number) => {
  const end = m.startSec + m.duration;
  const out = Math.max(0, m.outFrames ?? 4) / fps;
  if (m.kind === 'push') {
    // holdSec (optional, default 0 = unchanged): stay at the peak scale this long after the window, then ease out
    const hold = Math.max(0, m.holdSec ?? 0);
    if (t < m.startSec || t > end + hold + out) return 1;
    const crawl = m.style === 'crawl';
    const to = m.to ?? (crawl ? 1 + CRAWL_RATE * m.duration : 1.08);
    const k = clamp01((t - m.startSec) / Math.max(0.01, m.duration));
    const peak = 1 + (to - 1) * (crawl ? k : easeInOut(k));
    if (t <= end + hold) return peak;
    return 1 + (to - 1) * (1 - easeOut((t - end - hold) / out)); // snap back out
  }
  if (t < m.startSec || t > end + out) return 1;
  const to = m.to ?? 1.16;
  const inS = (m.inFrames ?? 4) / fps;
  if (t <= end) return 1 + (to - 1) * easeOut((t - m.startSec) / inS); // fast punch in, then hold
  return 1 + (to - 1) * (1 - easeOut((t - end) / out)); // snap back out
};

/**
 * Camera: slow push-ins on story beats + fast punch-ins on punchlines, each snapping back out in ~4 frames.
 * Scales about the focus point (x,y 0-1, default the face at 0.5,0.35) so the face stays put and edges never show.
 */
export const Camera: React.FC<{ moves: CameraMove[]; children: React.ReactNode }> = ({ moves, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  let s = 1;
  let ox = 0.5;
  let oy = 0.35;
  for (const m of moves) {
    const v = moveScale(m, t, fps);
    if (v > s) {
      s = v;
      ox = m.x ?? 0.5;
      oy = m.y ?? 0.35;
    }
  }
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: `${ox * 100}% ${oy * 100}%` }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};
