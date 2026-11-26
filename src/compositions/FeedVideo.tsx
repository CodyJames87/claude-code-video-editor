import React from 'react';
import type { EditProps } from '../types';
import { EditedVideo } from './EditedVideo';

/** 1080x1350 (IG/FB feed 4:5). */
export const FeedVideo: React.FC<EditProps> = (p) => <EditedVideo fit="cover" {...p} />;
