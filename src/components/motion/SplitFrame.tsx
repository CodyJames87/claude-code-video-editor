import React from 'react';
import { AbsoluteFill, OffthreadVideo, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../../brand';
import type { SplitFrameProps } from '../../types';
import { resolveSrc } from '../../transcript';
import { Highlighted } from '../Highlighted';
import { BrowserFrame } from './BrowserFrame';
import { useDesign } from './design';

/** Design-frame geometry of the split (1080x1920). Captions sit in the gap between the bands (bottom 1110 by default). */
export const SPLIT = { graphicTop: 258, graphicH: 600, videoTopWhenBottom: 1150, videoTopWhenTop: 258, videoH: 608, captionBottom: 1068 };

/**
 * Split Frame: hard layout cut to an ink canvas with a graphic band (browser B-roll or a short text card) and you in a
 * full-width 16:9 video band (whole head, chin never cropped). The band plays the SAME source in sync, muted (the base
 * track keeps the audio). No camera moves while a split is on.
 */
export const SplitFrame: React.FC<SplitFrameProps & { dur: number; videoSrc: string; sourceStartSec: number }> = ({
  graphic,
  videoBand = 'bottom',
  background,
  videoZoom = 1,
  videoFocus,
  videoSrc,
  sourceStartSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { kx, ky, width } = useDesign();
  const ease = 1 - Math.pow(1 - Math.min(1, frame / 8), 3);
  const vTop = (videoBand === 'bottom' ? SPLIT.videoTopWhenBottom : SPLIT.videoTopWhenTop) * ky;
  const gTop = (videoBand === 'bottom' ? SPLIT.graphicTop : SPLIT.videoTopWhenTop + SPLIT.videoH + 250) * ky;
  const gW = 1000 * kx;
  const gH = SPLIT.graphicH * ky;
  return (
    <AbsoluteFill style={{ background: background ?? BRAND.ink }}>
      <div style={{ position: 'absolute', left: 0, top: vTop, width, height: SPLIT.videoH * ky, overflow: 'hidden' }}>
        <OffthreadVideo
          src={resolveSrc(videoSrc)}
          muted
          trimBefore={Math.round(sourceStartSec * fps)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: '50% 40%',
            // static band crop (e.g. to keep a mic maker's logo at the frame edge out of the band); never animated
            transform: `scale(${Math.max(1, videoZoom)})`,
            transformOrigin: `${(videoFocus?.x ?? 0.5) * 100}% ${(videoFocus?.y ?? 0.35) * 100}%`,
          }}
        />
      </div>
      <div style={{ position: 'absolute', left: (width - gW) / 2, top: gTop, opacity: ease, transform: `translateY(${(1 - ease) * 30 * ky}px)` }}>
        {graphic.type === 'browser' ? (
          <BrowserFrame src={graphic.src} url={graphic.url} startFrom={graphic.startFrom} width={gW} height={gH} scale={kx} />
        ) : (
          <div
            style={{
              width: gW,
              height: gH,
              borderRadius: 22 * ky,
              background: BRAND.white,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              padding: `0 ${70 * kx}px`,
              boxSizing: 'border-box',
            }}
          >
            <div style={{ width: 120 * kx, height: 8 * ky, borderRadius: 4, background: BRAND.accent, marginBottom: 26 * ky }} />
            {graphic.kicker ? (
              <div style={{ fontFamily: BRAND.bodyFont, fontWeight: 600, fontSize: 36 * ky, color: BRAND.neutral, marginBottom: 14 * ky }}>{graphic.kicker}</div>
            ) : null}
            <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: 84 * ky, lineHeight: 1.06, letterSpacing: '-0.025em', color: BRAND.ink }}>
              <Highlighted text={graphic.text} highlight={graphic.highlight} />
            </div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
