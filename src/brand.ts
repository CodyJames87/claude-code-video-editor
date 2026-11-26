// Brand tokens. Colors come from brand.config.json at the repo root (edit that file, not this one).
// Rule of thumb: `accent` is the ONLY highlight (one word or idea, never the whole line). `support` is for
// small supporting touches only (thin edge, bullet, quiet label), never a second caption highlight.
import { loadFont } from '@remotion/fonts';
import { staticFile } from 'remotion';
import cfg from '../brand.config.json';

const ACCENT: string = cfg.accent ?? '#2F6FED';

export const BRAND = {
  accent: ACCENT,
  /** @deprecated old name; same as BRAND.accent. */
  emerald: ACCENT,
  support: (cfg.support ?? '#42A5F5') as string,
  ink: (cfg.ink ?? '#212121') as string,
  white: (cfg.white ?? '#FFFFFF') as string,
  slate: (cfg.neutral ?? '#595959') as string,
  neutral: (cfg.neutral ?? '#595959') as string,
  hairline: (cfg.hairline ?? '#E5E5E5') as string,
  paleFill: (cfg.paleFill ?? '#CAE6FC') as string,
  softTile: (cfg.softTile ?? '#F4F5F4') as string,
  captionFont: 'Anton',            // reel captions only, uppercase, upright
  headlineFont: 'Plus Jakarta Sans', // cards, lists, titles (ExtraBold 800)
  bodyFont: 'DM Sans',             // body copy on cards (talking-head motion effects)
};

export type Theme = 'dark' | 'light';

export const themeColors = (theme: Theme = 'light') =>
  theme === 'dark'
    ? { bg: BRAND.ink, fg: BRAND.white, sub: '#A7AEB6', card: '#1B1F24', border: '#2A3036' }
    : { bg: BRAND.white, fg: BRAND.ink, sub: BRAND.slate, card: BRAND.white, border: BRAND.hairline };

// Bundled OFL fonts (public/fonts). loadFont() holds the render until they are ready,
// so nothing ever falls back to a system italic face.
loadFont({ family: BRAND.captionFont, url: staticFile('fonts/Anton-Regular.ttf'), weight: '400', style: 'normal' });
loadFont({
  family: BRAND.headlineFont,
  url: staticFile('fonts/PlusJakartaSans-Variable.ttf'),
  weight: '200 800',
  style: 'normal',
});

loadFont({ family: BRAND.bodyFont, url: staticFile('fonts/DMSans-Variable.ttf'), weight: '100 1000', style: 'normal' });

/** Split text and wrap the words listed in `highlight` in the accent color. */
export const highlightWords = (text: string, highlight?: string | string[]) => {
  const hs = (Array.isArray(highlight) ? highlight : highlight ? [highlight] : []).map((h) => h.toLowerCase());
  if (!hs.length) return [{ text, hl: false }];
  const out: { text: string; hl: boolean }[] = [];
  let rest = text;
  while (rest.length) {
    let best = -1;
    let len = 0;
    const lower = rest.toLowerCase();
    const isWordChar = (c?: string) => !!c && /[a-z0-9']/i.test(c);
    for (const h of hs) {
      // whole words only: "now" must not light up inside "know"
      let i = lower.indexOf(h);
      while (i >= 0 && (isWordChar(lower[i - 1]) || isWordChar(lower[i + h.length]))) i = lower.indexOf(h, i + 1);
      if (i >= 0 && (best < 0 || i < best)) {
        best = i;
        len = h.length;
      }
    }
    if (best < 0) {
      out.push({ text: rest, hl: false });
      break;
    }
    if (best > 0) out.push({ text: rest.slice(0, best), hl: false });
    out.push({ text: rest.slice(best, best + len), hl: true });
    rest = rest.slice(best + len);
  }
  return out;
};
