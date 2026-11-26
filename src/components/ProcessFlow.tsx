import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, themeColors } from '../brand';
import type { ProcessFlowProps } from '../types';
import { enterExit } from './anim';

/** Steps reveal one after another; the newest step gets the accent color edge. */
export const ProcessFlow: React.FC<ProcessFlowProps & { dur: number }> = ({ title, steps, theme = 'light', dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = themeColors(theme);
  const vertical = height >= width;
  const per = Math.max(6, Math.floor((dur - 12) / Math.max(1, steps.length)));
  const active = Math.min(steps.length - 1, Math.floor(frame / per));
  const fs = Math.round(width * (vertical ? 0.05 : 0.026));
  const out = enterExit(frame, fps, dur, 0);
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: out }}>
      <div style={{ background: t.card, border: `2px solid ${t.border}`, borderRadius: 32, padding: fs * 0.9, width: vertical ? '84%' : '80%', boxShadow: '0 18px 50px rgba(17,20,24,0.28)' }}>
        {title ? (
          <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 1.15, color: t.fg, marginBottom: fs * 0.7, letterSpacing: '-0.02em' }}>{title}</div>
        ) : null}
        <div style={{ display: 'flex', flexDirection: vertical ? 'column' : 'row', gap: fs * 0.5, alignItems: 'stretch' }}>
          {steps.map((s, i) => {
            const a = enterExit(frame, fps, dur, i * per);
            const on = i === active;
            return (
              <React.Fragment key={i}>
                {i > 0 ? (
                  <div style={{ alignSelf: 'center', color: i <= active ? BRAND.accent : t.sub, fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 0.9, opacity: a, transform: vertical ? 'rotate(90deg)' : undefined }}>→</div>
                ) : null}
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: fs * 0.45,
                    padding: `${fs * 0.45}px ${fs * 0.6}px`,
                    borderRadius: 20,
                    background: theme === 'dark' ? '#15191D' : BRAND.softTile,
                    border: `4px solid ${on ? BRAND.accent : 'transparent'}`,
                    opacity: a,
                    transform: `translateY(${interpolate(a, [0, 1], [24, 0])}px)`,
                  }}
                >
                  <div style={{ minWidth: fs * 1.25, height: fs * 1.25, borderRadius: '50%', background: i <= active ? BRAND.accent : t.sub, color: BRAND.white, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: BRAND.headlineFont, fontWeight: 800, fontSize: fs * 0.6 }}>{i + 1}</div>
                  <div style={{ fontFamily: BRAND.headlineFont, fontWeight: 700, fontSize: fs * 0.8, color: t.fg, lineHeight: 1.12 }}>{s}</div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
