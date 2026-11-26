import React from 'react';
import type { EditProps } from '../types';
import { EditedVideo } from './EditedVideo';

/** 1080x1920 (Reels / Shorts / TikTok). */
export const ShortsVideo: React.FC<EditProps> = (p) => <EditedVideo fit="cover" {...p} />;
