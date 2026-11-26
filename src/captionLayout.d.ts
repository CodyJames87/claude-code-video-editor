import type { Caption } from '@remotion/captions';
export type Line = { words: Caption[] };
export type Page = { startMs: number; endMs: number; lines: Line[] };
export declare const normWord: (s: string) => string;
export declare const cleanWord: (s: string) => string;
export declare const buildTwoLinePages: (captions: Caption[], maxWords?: number, maxLineChars?: number, skip?: string[], oneLineRanges?: Array<{ from: number; to: number }>, trimStartSec?: number) => Page[];
export declare const makeIsMoney: (moneyWords?: string[]) => (s: string) => boolean;
export declare const pickHighlight: (page: Page, isMoney: (s: string) => boolean) => [number, number] | null;
export declare const highlightMap: (page: Page, isMoney: (s: string) => boolean) => boolean[][];
