import type { CalculateMetadataFunction } from 'remotion';
import { getVideoMetadata } from '@remotion/media-utils';
import type { EditProps } from '../types';
import { loadCaptions, resolveSrc } from '../transcript';

export const FPS = 30;

/** Duration = trimmed video length (falls back to the transcript end). */
export const calcEditMetadata: CalculateMetadataFunction<EditProps> = async ({ props }) => {
  let seconds = 0;
  try {
    const meta = await getVideoMetadata(resolveSrc(props.videoSrc));
    seconds = meta.durationInSeconds;
  } catch {
    const caps = await loadCaptions(props.transcriptJson);
    seconds = caps.length ? caps[caps.length - 1].endMs / 1000 + 0.5 : 10;
  }
  const start = props.trim?.start ?? 0;
  const end = Math.min(props.trim?.end ?? seconds, seconds);
  const tail = Math.max(0, props.tailHoldSec ?? 0); // Takeover hold after the source ends
  return { durationInFrames: Math.max(1, Math.round((end - start + tail) * FPS)), fps: FPS };
};

export const defaultEditProps: EditProps = {
  videoSrc: 'media/sample.mp4',
  transcriptJson: 'media/sample.captions.json',
  trim: null,
  music: null, // creator adds a trending sound in the app
  captions: { enabled: true, mode: 'lowerThird', moneyWords: [] },
  hook: null,
  sfx: { enabled: true, whooshDb: -24, popDb: -26, maxWhooshes: 4, maxPops: 3, minGapSec: 8 },
  overlays: [],
};
