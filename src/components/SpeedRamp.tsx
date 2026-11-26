import React from 'react';
import { AbsoluteFill, OffthreadVideo, Sequence, useVideoConfig } from 'remotion';
import type { SpeedRampProps } from '../types';
import { resolveSrc } from '../transcript';

/**
 * Stop-and-go B-roll ramp: plays source footage [sourceStart, sourceEnd] inside this overlay's window,
 * easing 1x -> fast -> 1x in steps. Muted: the voice keeps running underneath (never ramp the talking track).
 */
export const SpeedRamp: React.FC<SpeedRampProps & { dur: number; defaultSrc: string }> = ({ sourceStart, sourceEnd, src, steps = 9, dur, defaultSrc }) => {
  const { fps } = useVideoConfig();
  const n = Math.max(3, steps);
  const segFrames = Array.from({ length: n }, (_, i) => Math.floor(((i + 1) * dur) / n) - Math.floor((i * dur) / n));
  const shape = Array.from({ length: n }, (_, i) => 0.35 + Math.sin((Math.PI * (i + 0.5)) / n) ** 2);
  const srcLen = Math.max(0.1, sourceEnd - sourceStart);
  const k = srcLen / shape.reduce((acc, b, i) => acc + (b * segFrames[i]) / fps, 0);
  let from = 0;
  let pos = sourceStart;
  const file = resolveSrc(src ?? defaultSrc);
  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      {segFrames.map((f, i) => {
        const rate = Math.max(0.25, shape[i] * k);
        const el = (
          <Sequence key={i} from={from} durationInFrames={f} layout="none">
            <AbsoluteFill>
              <OffthreadVideo src={file} trimBefore={Math.round(pos * fps)} playbackRate={rate} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </AbsoluteFill>
          </Sequence>
        );
        from += f;
        pos += (f / fps) * rate;
        return el;
      })}
    </AbsoluteFill>
  );
};
