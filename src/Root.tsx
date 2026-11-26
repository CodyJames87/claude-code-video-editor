import React from 'react';
import { Composition } from 'remotion';
import { ShortsVideo } from './compositions/ShortsVideo';
import { FeedVideo } from './compositions/FeedVideo';
import { LongForm } from './compositions/LongForm';
import { FPS, calcEditMetadata, defaultEditProps } from './compositions/presets';
import type { EditProps } from './types';
import { TextThread, THREAD_FPS, calcThreadMetadata, defaultThreadProps } from './textthread/TextThread';
import type { ThreadSpec } from './textthread/timeline';

// Props come from props/<name>.json via:  npx remotion render ShortsVideo out/x.mp4 --props=props/x.json
export const RemotionRoot: React.FC = () => (
  <>
    <Composition<any, EditProps> id="ShortsVideo" component={ShortsVideo} width={1080} height={1920} fps={FPS} durationInFrames={300} defaultProps={defaultEditProps} calculateMetadata={calcEditMetadata} />
    <Composition<any, EditProps> id="FeedVideo" component={FeedVideo} width={1080} height={1350} fps={FPS} durationInFrames={300} defaultProps={defaultEditProps} calculateMetadata={calcEditMetadata} />
    <Composition<any, EditProps> id="LongForm" component={LongForm} width={1920} height={1080} fps={FPS} durationInFrames={300} defaultProps={defaultEditProps} calculateMetadata={calcEditMetadata} />
    {/* Text Thread animated text post (iMessage-style), spec: threads/<name>.json. Not a footage edit. */}
    <Composition<any, ThreadSpec> id="TextThread" component={TextThread} width={1080} height={1920} fps={THREAD_FPS} durationInFrames={300} defaultProps={defaultThreadProps} calculateMetadata={calcThreadMetadata} />
  </>
);
