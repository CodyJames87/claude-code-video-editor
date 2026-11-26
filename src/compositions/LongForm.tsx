import React from 'react';
import type { EditProps } from '../types';
import { EditedVideo } from './EditedVideo';

/** 1920x1080 (YouTube / LinkedIn). Vertical sources get a blurred fill instead of a hard crop. */
export const LongForm: React.FC<EditProps> = (p) => <EditedVideo fit="contain-blur" {...p} />;
