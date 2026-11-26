import React from 'react';
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import type { CalloutChipProps } from '../../types';
import { enterExit } from '../anim';
import { Highlighted } from '../Highlighted';
import { useDesign } from './design';
import { resolveSrc } from '../../transcript';

/**
 * Callout Chip: a small white chip with a short VERBATIM phrase (one accent word max) and a thin sky-blue edge
 * (supporting use only). `box` = [x, y, w, h] on the 1080x1920 design frame and MUST pass `helpers/face_safe.py check`
 * for the whole window; the chip never grows past its box.
 * Optional `logoSrc` (e.g. an official logo PNG/SVG under public/): drawn at its intrinsic aspect ratio (height-driven,
 * never recolored or stretched), logo-only by default or followed by `text` when `logoOnly: false`. Without logoSrc the
 * chip is unchanged (text-only).
 */
export const CalloutChip: React.FC<CalloutChipProps & { dur: number }> = ({ text, highlight, box, align = 'left', logoSrc, logoOnly = true, logoScale = 0.46, dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { kx, ky } = useDesign();
  const a = enterExit(frame, fps, dur, 0, 6);
  const [x, y, w, h] = box;
  const fs = h * 0.48 * ky;
  const origin = align === 'right' ? '100% 50%' : align === 'center' ? '50% 50%' : '0% 50%';
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: x * kx,
          top: y * ky,
          width: w * kx,
          height: h * ky,
          display: 'flex',
          alignItems: 'center',
          justifyContent: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start',
        }}
      >
        <div
          style={{
            height: '100%',
            maxWidth: '100%',
            boxSizing: 'border-box',
            display: 'flex',
            alignItems: 'center',
            background: BRAND.white,
            borderRadius: 16 * ky,
            borderLeft: `${Math.max(4, 7 * kx)}px solid ${BRAND.support}`,
            padding: `0 ${fs * 0.7}px`,
            boxShadow: '0 10px 28px rgba(0,0,0,0.28)',
            fontFamily: BRAND.headlineFont,
            fontWeight: 800,
            fontSize: fs,
            color: BRAND.ink,
            whiteSpace: 'nowrap',
            textTransform: 'uppercase',
            letterSpacing: '0.01em',
            fontStyle: 'normal',
            opacity: a,
            transform: `scale(${0.9 + 0.1 * a})`,
            transformOrigin: origin,
          }}
        >
          {logoSrc ? (
            <Img
              src={resolveSrc(logoSrc)}
              style={{ height: h * ky * logoScale, width: 'auto', maxWidth: '100%', objectFit: 'contain', display: 'block', flexShrink: 1, minWidth: 0 }}
            />
          ) : null}
          {logoSrc && logoOnly ? null : (
            /* one inline span so the flex container keeps the spaces between words */
            <span style={logoSrc ? { marginLeft: fs * 0.45 } : undefined}>
              <Highlighted text={text} highlight={highlight} />
            </span>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
