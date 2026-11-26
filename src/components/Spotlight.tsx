import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SpotlightProps } from '../types';

/** Dims everything outside a soft ellipse (brand: 30-40%, never black, never tinted). */
export const Spotlight: React.FC<SpotlightProps & { dur: number }> = ({ x, y, w = 0.3, h = 0.2, dim = 0.38, feather = 0.35, dur }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const fade = Math.min(8, Math.floor(dur / 3));
  const a = interpolate(frame, [0, fade, dur - fade, dur], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const rx = (w * width) / 2;
  const ry = (h * height) / 2;
  const inner = 100 / (1 + feather);
  return (
    <AbsoluteFill
      style={{
        opacity: a,
        background: `radial-gradient(${rx * (1 + feather)}px ${ry * (1 + feather)}px at ${x * 100}% ${y * 100}%, rgba(0,0,0,0) ${inner}%, rgba(0,0,0,${dim}) 100%)`,
      }}
    />
  );
};
