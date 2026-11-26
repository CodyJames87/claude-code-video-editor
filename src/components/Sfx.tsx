import React from 'react';
import { Audio, Sequence, staticFile, useVideoConfig } from 'remotion';
import type { HookProps, Resolved, SfxProps } from '../types';

export type SfxCue = { sec: number; kind: 'whoosh' | 'pop' };

const CARDS = ['StatementCard', 'ProcessFlow', 'ComparisonCard', 'FullScreenList', 'PillList', 'TakeoverFrame'];

/**
 * Plan subtle SFX: a whoosh just before each PunchIn (peaks on the punch), a pop on the hook and on each card.
 * Capped (default 4 whooshes / 3 pops per reel) and whooshes spaced >= 8 s so it never gets busy.
 */
export const planSfx = (resolved: Resolved[], hook: HookProps | null | undefined, sfx: SfxProps, manual: SfxCue[] = []): SfxCue[] => {
  const cues: SfxCue[] = [...manual];
  if (sfx.auto !== false) {
    if (hook?.text && hook.sfx !== false) cues.push({ sec: 0.03, kind: 'pop' });
    for (const o of resolved) {
      if (o.type === 'PunchIn' && (o.props as any).sfx !== false) cues.push({ sec: Math.max(0, o.startSec - 0.12), kind: 'whoosh' });
      if (CARDS.includes(o.type)) cues.push({ sec: o.startSec, kind: 'pop' });
      // Count-Up Card: one pop when the number lands (not on entry)
      if (o.type === 'CountUpCard') cues.push({ sec: o.startSec + ((o.props as any).landSec ?? 0.4), kind: 'pop' });
    }
  }
  cues.sort((a, b) => a.sec - b.sec);
  const gap = sfx.minGapSec ?? 8;
  const out: SfxCue[] = [];
  let lastWhoosh = -Infinity;
  let w = 0;
  let p = 0;
  for (const c of cues) {
    if (c.kind === 'whoosh') {
      if (w >= (sfx.maxWhooshes ?? 4) || c.sec - lastWhoosh < gap) continue;
      lastWhoosh = c.sec;
      w++;
    } else {
      if (p >= (sfx.maxPops ?? 3)) continue;
      p++;
    }
    out.push(c);
  }
  return out;
};

const db = (v: number) => Math.pow(10, v / 20);

export const SfxTrack: React.FC<{ cues: SfxCue[]; sfx: SfxProps }> = ({ cues, sfx }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {cues.map((c, i) => (
        <Sequence key={i} from={Math.round(c.sec * fps)} durationInFrames={Math.round(0.6 * fps)} name={`sfx ${c.kind} @${c.sec.toFixed(2)}s`} layout="none">
          <Audio src={staticFile(`sfx/${c.kind}.wav`)} volume={db(c.kind === 'whoosh' ? sfx.whooshDb ?? -24 : sfx.popDb ?? -26)} />
        </Sequence>
      ))}
    </>
  );
};
