import React, { useEffect, useMemo, useState } from 'react';
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, cancelRender, continueRender, delayRender, interpolate, useVideoConfig } from 'remotion';
import type { Caption } from '@remotion/captions';
import { BRAND } from '../brand';
import type { EditProps, Resolved } from '../types';
import { resolveOverlays } from '../types';
import { loadCaptions, resolveSrc } from '../transcript';
import { Camera, Captions, ComparisonCard, FullScreenList, HookText, PillList, ProcessFlow, SfxTrack, SpeedRamp, Spotlight, StatementCard, ZoomToDetail, planSfx } from '../components';
import { CalloutChip, CountUpCard, ProgressBar, SPLIT, SplitFrame, TakeoverFrame, TitleBanner } from '../components/motion';
import type { CameraMove } from '../components/Camera';
import type { SfxCue } from '../components/Sfx';

/** Shared edit: original video + camera moves + word-timed <Sequence> overlays + captions + hook + subtle SFX (+ optional ducked music). */
export const EditedVideo: React.FC<EditProps> = (props) => {
  const { videoSrc, transcriptJson, overlays = [], music, trim, captions: capCfg = {}, focus, fit = 'cover', videoVolume = 1, hook, sfx, layout, progressBar, tailHoldSec = 0 } = props;
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const [caps, setCaps] = useState<Caption[] | null>(Array.isArray(transcriptJson) ? transcriptJson : null);
  const [handle] = useState(() => (Array.isArray(transcriptJson) ? null : delayRender('Loading transcript')));

  useEffect(() => {
    if (Array.isArray(transcriptJson)) return;
    loadCaptions(transcriptJson)
      .then((c) => {
        setCaps(c);
        if (handle !== null) continueRender(handle);
      })
      .catch((e) => cancelRender(e));
  }, [transcriptJson, handle]);

  const trimStart = trim?.start ?? 0;
  const resolved: Resolved[] = useMemo(() => resolveOverlays(overlays, caps ?? [], trimStart), [overlays, caps, trimStart]);
  const manualSfx: SfxCue[] = useMemo(
    () =>
      resolveOverlays(
        (sfx?.events ?? []).map((e) => ({ type: 'PillList', at: e.at, duration: 0, props: { items: [e.kind] } })),
        caps ?? [],
        trimStart,
      ).map((r) => ({ sec: r.startSec, kind: (r.props as any).items[0] })),
    [sfx, caps, trimStart],
  );
  if (!caps) return null;

  const src = resolveSrc(videoSrc);
  const fx = (o: Resolved) => ({ from: Math.round(o.startSec * fps), durationInFrames: Math.max(1, Math.round(o.duration * fps)) });
  const zooms = resolved
    .filter((o) => o.type === 'ZoomToDetail')
    .map((o) => ({ startSec: o.startSec, duration: o.duration, ...(o.props as any) }));
  const moves: CameraMove[] = resolved
    .filter((o) => o.type === 'PushIn' || o.type === 'PunchIn')
    .map((o) => ({ kind: o.type === 'PushIn' ? 'push' : 'punch', startSec: o.startSec, duration: o.duration, ...(o.props as any) }));
  const hookDur = hook?.text ? hook.duration ?? 2.0 : 0;
  const cues = sfx && sfx.enabled !== false ? planSfx(resolved, hook, sfx, manualSfx) : [];
  const hidden = resolved
    .filter((o) => o.hideCaptions ?? ['FullScreenList', 'ComparisonCard', 'ProcessFlow', 'TakeoverFrame'].includes(o.type))
    .map((o) => [o.startSec, o.startSec + o.duration] as [number, number]);
  if (hookDur) hidden.push([0, hookDur]); // the hook text owns the first ~2 s

  // speech mask for music ducking (timeline seconds)
  const speech = caps.map((c) => [c.startMs / 1000 - trimStart, c.endMs / 1000 - trimStart] as [number, number]);
  const speaking = (t: number) => speech.some(([a, b]) => t >= a - 0.15 && t <= b + 0.25);
  const objectPosition = `${(focus?.x ?? 0.5) * 100}% ${(focus?.y ?? 0.4) * 100}%`;

  // Solo Frame headroom band (design px on 1080x1920, scaled): the video panel starts below it; camera moves stay inside.
  const bandPx = Math.max(0, Math.round((layout?.topBand ?? 0) * (height / 1920)));
  const bandColor = layout?.bandColor ?? BRAND.ink;
  const cropPx = Math.max(0, Math.round((layout?.cropTop ?? 0) * (height / 1920)));
  // Split Frame: captions move into the gap between the bands exactly at the layout cuts (byFrame), ahead of user ranges
  const splitRanges = resolved
    .filter((o) => o.type === 'SplitFrame')
    .map((o) => ({ from: o.startSec, to: o.startSec + o.duration, bottom: (o.props as any).captionBottom ?? SPLIT.captionBottom, byFrame: true }));
  const bottomRanges = [...splitRanges, ...(capCfg.bottomRanges ?? [])];
  // bottomRanges only apply on 9:16 (Captions.tsx); on 4:5 / 16:9 the split's caption gap can't be honoured, so captions
  // hide during a split there instead of landing on the face band
  if (height <= width * 1.5) splitRanges.forEach((r) => hidden.push([r.from, r.to]));
  const captionMode = capCfg.mode === 'karaoke' || capCfg.karaoke ? 'karaoke' : capCfg.mode;
  // Tail hold: the source stops, overlays (e.g. a Takeover Frame) keep going
  const videoFrames = Math.max(1, durationInFrames - Math.round(Math.max(0, tailHoldSec) * fps));
  // Takeover reveal "spoken": time (s into the overlay) at which each headline word is said
  const takeoverTimes = (o: Resolved) => {
    const words = String((o.props as any).text ?? '').split(/\s+/).filter(Boolean);
    const nrm = (x: string) => x.toLowerCase().replace(/[^a-z0-9$%']/g, '');
    let ci = caps.findIndex((c) => c.startMs / 1000 - trimStart >= o.startSec - 0.05);
    return words.map((w) => {
      if (ci < 0) return null;
      for (let j = ci; j < Math.min(caps.length, ci + 6); j++) {
        if (nrm(caps[j].text) === nrm(w)) {
          ci = j + 1;
          return Math.max(0, caps[j].startMs / 1000 - trimStart - o.startSec);
        }
      }
      return null;
    });
  };

  const base = (
    <OffthreadVideo
      src={src}
      trimBefore={Math.round(trimStart * fps)}
      trimAfter={trim?.end ? Math.round(trim.end * fps) : undefined}
      volume={videoVolume}
      style={{ width: '100%', height: '100%', objectFit: fit === 'cover' ? 'cover' : 'contain', objectPosition }}
    />
  );

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      {fit === 'contain-blur' ? (
        <AbsoluteFill style={{ filter: 'blur(40px) brightness(0.55)', transform: 'scale(1.15)' }}>
          <OffthreadVideo src={src} trimBefore={Math.round(trimStart * fps)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </AbsoluteFill>
      ) : null}
      <Sequence from={0} durationInFrames={videoFrames} name="Source video" layout="none">
        {bandPx ? (
          <AbsoluteFill style={{ backgroundColor: bandColor }}>
            <div style={{ position: 'absolute', left: 0, right: 0, top: bandPx, bottom: 0, overflow: 'hidden' }}>
              {/* cropTop: hide a light/dirty top edge baked into some webcam sources under the band edge */}
              <div style={{ position: 'absolute', left: 0, right: 0, top: -cropPx, bottom: 0 }}>
                <Camera moves={moves}>
                  <ZoomToDetail zooms={zooms}>{base}</ZoomToDetail>
                </Camera>
              </div>
            </div>
          </AbsoluteFill>
        ) : (
          <Camera moves={moves}>
            <ZoomToDetail zooms={zooms}>{base}</ZoomToDetail>
          </Camera>
        )}
      </Sequence>

      {resolved.map((o, i) => {
        const { from, durationInFrames: dur } = fx(o);
        const seq = (child: React.ReactNode) => (
          <Sequence key={i} from={from} durationInFrames={dur} name={`${o.type} @${o.startSec.toFixed(2)}s`}>
            {child}
          </Sequence>
        );
        switch (o.type) {
          case 'Spotlight':
            return seq(<Spotlight {...o.props} dur={dur} />);
          case 'SpeedRamp':
            return seq(<SpeedRamp {...o.props} dur={dur} defaultSrc={videoSrc} />);
          case 'StatementCard':
            return seq(<StatementCard {...o.props} dur={dur} />);
          case 'ProcessFlow':
            return seq(<ProcessFlow {...o.props} dur={dur} />);
          case 'ComparisonCard':
            return seq(<ComparisonCard {...o.props} dur={dur} />);
          case 'FullScreenList':
            return seq(<FullScreenList {...o.props} dur={dur} />);
          case 'PillList':
            return seq(<PillList {...o.props} dur={dur} />);
          case 'TitleBanner':
            return seq(<TitleBanner {...o.props} dur={dur} />);
          case 'CountUpCard':
            return seq(<CountUpCard {...o.props} dur={dur} />);
          case 'CalloutChip':
            return seq(<CalloutChip {...o.props} dur={dur} />);
          case 'SplitFrame':
            return seq(<SplitFrame {...o.props} dur={dur} videoSrc={videoSrc} sourceStartSec={trimStart + o.startSec} />);
          case 'TakeoverFrame':
            return seq(<TakeoverFrame {...o.props} dur={dur} wordTimes={takeoverTimes(o)} />);
          default:
            return null;
        }
      })}

      {capCfg.enabled === false ? null : (
        <Captions
          captions={caps}
          trimStartSec={trimStart}
          mode={captionMode}
          keywords={capCfg.keywords}
          moneyWords={capCfg.moneyWords}
          maxWords={capCfg.maxWords}
          maxLineChars={capCfg.maxLineChars}
          skipWords={capCfg.skipWords}
          hidden={hidden}
          bottomRanges={bottomRanges}
          oneLineRanges={capCfg.oneLineRanges}
        />
      )}

      {hookDur ? (
        <Sequence from={0} durationInFrames={Math.round(hookDur * fps)} name="Hook">
          <HookText {...hook!} dur={Math.round(hookDur * fps)} />
        </Sequence>
      ) : null}

      {progressBar && progressBar.enabled !== false ? <ProgressBar {...progressBar} /> : null}

      {cues.length ? <SfxTrack cues={cues} sfx={sfx!} /> : null}

      {/* Music is OFF by default: the creator usually adds a trending sound in the app. Only set `music` if asked. */}
      {music?.src ? (
        <Audio
          src={resolveSrc(music.src)}
          loop
          volume={(f) => {
            const t = f / fps;
            const v = music.volume ?? 0.18;
            const duck = speaking(t) ? music.duckTo ?? 0.35 : 1;
            const fadeIn = interpolate(t, [0, 0.5], [0, 1], { extrapolateRight: 'clamp' });
            return v * duck * fadeIn;
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
