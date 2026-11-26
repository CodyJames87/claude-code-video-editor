import { interpolate, spring } from 'remotion';

/** 0->1 entrance spring and 1->0 exit over the last `outFrames`. */
export const enterExit = (frame: number, fps: number, dur: number, delay = 0, outFrames = 8) => {
  const enter = spring({ frame: frame - delay, fps, config: { damping: 14, stiffness: 160, mass: 0.7 } });
  const exit = interpolate(frame, [dur - outFrames, dur], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return Math.min(enter, exit);
};

export const smoothstep = (k: number) => {
  const x = Math.min(1, Math.max(0, k));
  return x * x * (3 - 2 * x);
};
