import type { Caption } from '@remotion/captions';
import type { Theme } from './brand';

/**
 * When an overlay starts. Either seconds on the video timeline, or anchored to a spoken word
 * (first occurrence by default) so graphics land exactly when the speaker says it.
 */
export type Anchor = number | { word: string; occurrence?: number; offset?: number };

type Base = {
  at: Anchor;             // start
  duration: number;       // seconds
  hideCaptions?: boolean; // hide burned captions while this overlay is up
};

export type StatementCardProps = { text: string; highlight?: string | string[]; theme?: Theme; position?: 'center' | 'top' | 'lower' | 'full'; kicker?: string };
export type ProcessFlowProps = { title?: string; steps: string[]; theme?: Theme };
export type ComparisonSide = { label: string; value?: string; points?: string[] };
export type ComparisonCardProps = { title?: string; left: ComparisonSide; right: ComparisonSide; winner?: 'left' | 'right'; theme?: Theme };
export type FullScreenListProps = { title: string; items: string[]; theme?: Theme; highlight?: string | string[] };
export type PillListProps = { items: string[]; position?: 'top' | 'center' | 'bottom'; theme?: Theme };
export type ZoomToDetailProps = { x: number; y: number; zoom?: number; ease?: number };       // x,y: 0-1 of the frame
export type SpotlightProps = { x: number; y: number; w?: number; h?: number; dim?: number; feather?: number }; // 0-1
export type SpeedRampProps = { sourceStart: number; sourceEnd: number; src?: string; steps?: number };    // B-roll seconds
/**
 * Slow zoom: scale 1 -> `to` across the whole window, then snap back to 1 in `outFrames` (default 4; 0 = instant).
 * `style` picks the named tool (see style/effects-library.md):
 *   "eased" = Eased Push (DEFAULT when omitted): cubic ease-in-out. Cinematic / emotional / B-roll. Default `to` 1.08.
 *   "crawl" = Steady Crawl: constant LINEAR zoom, no easing, ~+0.048 scale/s over 2-3 s. Talking-head / punchy speech.
 *             Default `to` when omitted = 1 + 0.048 * duration (2.5 s -> 1.12, 3.0 s -> 1.144).
 */
export type PushInProps = { to?: number; x?: number; y?: number; outFrames?: number; style?: 'eased' | 'crawl'; holdSec?: number }; // holdSec: optional peak hold after the window (default 0) // x 0.5, y 0.35, out 4f
/** Punchline punch: scale -> `to` in `inFrames`, hold for the window, snap back to 1 in `outFrames`. */
export type PunchInProps = { to?: number; x?: number; y?: number; inFrames?: number; outFrames?: number; sfx?: boolean }; // 1.16, 4f, 4f, whoosh on

// ---- Talking-head motion (style/effects-library.md "## Talking-head motion"). Coordinates are px on the 1080x1920
// design frame (scaled by height/1920 on other aspect ratios); place them with helpers/face_safe.py, then LOOK at QC frames.
/** Title Banner: short verbatim headline in the top headroom band (Plus Jakarta ExtraBold, one accent word). */
export type TitleBannerProps = { text: string; highlight?: string; y?: number; fontSize?: number; instantIn?: boolean; theme?: 'onInk' | 'card' };
/** Count-Up Card: counts from `from` to `to` (a number he SAYS), landing `landSec` into the overlay. */
export type CountUpCardProps = { to: number; from?: number; landSec?: number; numberSize?: number; kicker?: string; unit?: string; y?: number; prefix?: string; suffix?: string };
/** Callout Chip: small verbatim phrase in a box checked by helpers/face_safe.py. box = [x, y, w, h] on 1080x1920. */
export type CalloutChipProps = {
  text: string; highlight?: string; box: [number, number, number, number]; align?: 'left' | 'center' | 'right';
  /** Optional image (path under public/, e.g. an official logo) shown in the chip at its intrinsic aspect ratio. Default: text-only. */
  logoSrc?: string;
  /** With logoSrc: true = logo only (default); false = logo + `text` label. */
  logoOnly?: boolean;
  /** Logo height as a fraction of the chip height (default 0.46). */
  logoScale?: number;
};
/** Browser-Frame B-Roll clip (captured by helpers/capture_browser_broll.mjs) inside our own browser chrome. */
export type BrowserGraphic = { type: 'browser'; src: string; url?: string; startFrom?: number };
export type TextGraphic = { type: 'text'; text: string; highlight?: string; kicker?: string };
/** Split Frame: the speaker in a video band, a graphic in the other band. No camera moves while it is on. */
export type SplitFrameProps = {
  graphic: BrowserGraphic | TextGraphic;
  videoBand?: 'bottom' | 'top';   // default bottom
  videoZoom?: number;              // static crop of the video band about videoFocus (default 1 = whole 16:9); NOT a camera move
  videoFocus?: { x: number; y: number }; // 0-1 of the band (default 0.5, 0.35)
  captionBottom?: number;          // caption block bottom y while split (default 1068); injected as a byFrame bottomRange
  background?: string;             // layout canvas, default BRAND.ink
};
/** Takeover Frame: full-screen graphic, video hidden (ONE per reel). reveal "spoken" = words appear as he says them. */
export type TakeoverFrameProps = {
  text?: string; highlight?: string; kicker?: string; theme?: 'light' | 'dark'; reveal?: 'spoken' | 'all';
  graphic?: BrowserGraphic;        // full-frame browser B-roll instead of text
};

export type Overlay =
  | (Base & { type: 'StatementCard'; props: StatementCardProps })
  | (Base & { type: 'ProcessFlow'; props: ProcessFlowProps })
  | (Base & { type: 'ComparisonCard'; props: ComparisonCardProps })
  | (Base & { type: 'FullScreenList'; props: FullScreenListProps })
  | (Base & { type: 'PillList'; props: PillListProps })
  | (Base & { type: 'ZoomToDetail'; props: ZoomToDetailProps })
  | (Base & { type: 'Spotlight'; props: SpotlightProps })
  | (Base & { type: 'SpeedRamp'; props: SpeedRampProps })
  | (Base & { type: 'PushIn'; props: PushInProps })
  | (Base & { type: 'PunchIn'; props: PunchInProps })
  | (Base & { type: 'TitleBanner'; props: TitleBannerProps })
  | (Base & { type: 'CountUpCard'; props: CountUpCardProps })
  | (Base & { type: 'CalloutChip'; props: CalloutChipProps })
  | (Base & { type: 'SplitFrame'; props: SplitFrameProps })
  | (Base & { type: 'TakeoverFrame'; props: TakeoverFrameProps });

/** Big text hook on screen from frame 0 (Plus Jakarta Sans ExtraBold on a white Clean Line card). */
export type HookProps = {
  text: string;
  highlight?: string | string[];
  duration?: number;              // default 2.0 s
  position?: 'top' | 'lower';     // top = y ~300 (default); lower = in the caption zone (bottom at y 1150) when the face sits high
  theme?: 'light' | 'dark';
  sfx?: boolean;
  bottom?: number;                // 'lower' only: bottom edge y on 9:16 (default 1150). Raise for full-frame face cams so the hook sits on the chest
  fontSize?: number;              // optional override (default 96 lower / 88 top on 9:16)
  maxWidth?: number;              // optional override in px (default 900 on 9:16)
};

export type SfxEvent = { at: Anchor; kind: 'whoosh' | 'pop' };
/** Subtle SFX. Auto: whoosh on each PunchIn, pop on the hook and on cards. Capped and spaced so it never gets busy. */
export type SfxProps = {
  enabled?: boolean;        // default true when the prop exists
  auto?: boolean;           // default true
  whooshDb?: number;        // default -24 (relative to the full-scale SFX file)
  popDb?: number;           // default -26
  maxWhooshes?: number;     // default 4 per reel
  maxPops?: number;         // default 3 per reel
  minGapSec?: number;       // default 8 s between whooshes
  events?: SfxEvent[];      // manual extras (still capped)
};

export type MusicProps = {
  src: string;          // file in public/ (e.g. "music/bed.mp3") or URL
  volume?: number;      // 0-1 bed level when nobody is talking (default 0.18)
  duckTo?: number;      // multiplier while speech is active (default 0.35)
};

export type EditProps = {
  videoSrc: string;                    // file in public/ (e.g. "media/clip.mp4") or http(s) URL
  transcriptJson: string | Caption[];  // file in public/ (e.g. "media/clip.captions.json") or inline captions
  overlays: Overlay[];
  music?: MusicProps | null;
  trim?: { start: number; end?: number } | null; // seconds of the source to use
  captions?: {
    enabled?: boolean;
    mode?: 'active' | 'keyword' | 'lowerThird' | 'karaoke'; // 'lowerThird' = the default; 'karaoke' = lowerThird layout + lit active word
    karaoke?: boolean;                          // same as mode 'karaoke' (Karaoke Captions on the lowerThird layout)
    keywords?: string[];                        // keyword mode
    moneyWords?: string[];                      // lowerThird: the ONE word per line that gets the accent color (numbers/$ if empty)
    maxWords?: number;                          // words per line (lowerThird default 4)
    maxLineChars?: number;                      // lowerThird default 18
    skipWords?: string[];                       // drop these tokens from captions (e.g. host "mm-hmm")
    // lowerThird, 9:16 only, default off: per time range (timeline s, page start decides) caption block bottom y,
    // e.g. [{ "from": 0, "to": 29.7, "bottom": 1520 }] so captions sit on the chest of a full-frame face cam
    // byFrame: true = current time decides (page moves exactly at a hard layout cut)
    bottomRanges?: Array<{ from: number; to: number; bottom: number; byFrame?: boolean }>;
    // lowerThird: pages whose first word starts in [from, to) (timeline s) show ONE line (same font/size/bottom),
    // e.g. [{ "from": 59, "to": 90 }] when the chin sits too low for two lines. Absent = two lines everywhere.
    oneLineRanges?: Array<{ from: number; to: number }>;
  };
  hook?: HookProps | null;
  sfx?: SfxProps | null;
  focus?: { x: number; y: number };    // crop focus for cover framing, 0-1 (default 0.5, 0.4)
  fit?: 'cover' | 'contain-blur';
  videoVolume?: number;                // original audio level (default 1)
  /** Solo Frame headroom: an ink band of `topBand` px (1080x1920 design units) above the video panel, so the progress bar,
   *  Title Banner, Count-Up and chips sit ABOVE the cap. Camera moves stay inside the panel. Absent/0 = full-bleed (old look). */
  layout?: { topBand?: number; bandColor?: string; cropTop?: number } | null; // cropTop: design px of the panel's top edge hidden under the band
  /** Progress Bar: thin accent fill on a subtle track, elapsed / total. */
  progressBar?: { enabled?: boolean; position?: 'topSafe' | 'bottom'; y?: number; height?: number; inset?: number; track?: 'hairline' | 'pale' } | null;
  /** Seconds to hold after the source ends (e.g. so a Takeover Frame can be read). Video stops, overlays keep going. */
  tailHoldSec?: number;
};

export type Resolved = Overlay & { startSec: number };

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9$%']/g, '');

/** Resolve word anchors against the transcript (times relative to the trimmed timeline). */
export const resolveOverlays = (overlays: Overlay[], captions: Caption[], trimStart = 0): Resolved[] =>
  overlays.map((o) => {
    if (typeof o.at === 'number') return { ...o, startSec: o.at };
    const target = o.at.word.split(/\s+/).map(norm).filter(Boolean);
    const words = captions.map((c) => norm(c.text));
    let seen = 0;
    for (let i = 0; i < words.length; i++) {
      if (target.every((t, k) => words[i + k] === t)) {
        seen++;
        if (seen === (o.at.occurrence ?? 1)) {
          return { ...o, startSec: captions[i].startMs / 1000 - trimStart + (o.at.offset ?? 0) };
        }
      }
    }
    console.warn(`Overlay anchor word not found: "${o.at.word}". Starting at 0.`);
    return { ...o, startSec: 0 };
  });
