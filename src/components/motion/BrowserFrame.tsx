import React from 'react';
import { OffthreadVideo, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import { resolveSrc } from '../../transcript';

/**
 * Our own minimal browser chrome (no OS trademark, no company logo): three neutral window dots, an address pill,
 * a hairline, then the captured page clip (helpers/capture_browser_broll.mjs) top-aligned and muted.
 */
export const BrowserFrame: React.FC<{ src: string; url?: string; startFrom?: number; width: number; height: number; scale?: number }> = ({
  src,
  url,
  startFrom = 0,
  width,
  height,
  scale = 1,
}) => {
  const { fps } = useVideoConfig();
  const bar = 58 * scale;
  const dot = 14 * scale;
  const line = Math.max(1, 2 * scale);
  return (
    <div style={{ width, height, borderRadius: 22 * scale, overflow: 'hidden', background: BRAND.white, boxShadow: '0 18px 50px rgba(0,0,0,0.35)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: bar, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10 * scale, padding: `0 ${22 * scale}px`, background: BRAND.softTile, borderBottom: `${line}px solid ${BRAND.hairline}` }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ width: dot, height: dot, borderRadius: dot, background: BRAND.hairline }} />
        ))}
        <div
          style={{
            marginLeft: 16 * scale,
            flex: 1,
            height: bar * 0.6,
            borderRadius: bar,
            background: BRAND.white,
            border: `${line}px solid ${BRAND.hairline}`,
            display: 'flex',
            alignItems: 'center',
            padding: `0 ${18 * scale}px`,
            fontFamily: BRAND.bodyFont,
            fontWeight: 500,
            fontSize: 22 * scale,
            color: BRAND.neutral,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontStyle: 'normal',
          }}
        >
          {url ?? ''}
        </div>
      </div>
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: BRAND.white }}>
        <OffthreadVideo
          src={resolveSrc(src)}
          muted
          trimBefore={Math.round(startFrom * fps)}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 0%' }}
        />
      </div>
    </div>
  );
};
