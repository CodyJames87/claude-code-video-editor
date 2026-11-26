// Pure caption layout + highlight logic (plain ESM JS so Remotion AND node QC scripts share it).
// Rule: an on-screen caption (the 1-2 line block) shows AT MOST ONE accent word (brand.config.json accent).
// The money word is picked per occurrence: each line's candidate is its FIRST money word, and the
// LAST line with a candidate wins the block
// (e.g. "WE STARTED WITH / ONLY 3 CLIENTS" -> 3, "THIS GROWS / REALLY FAST" -> FAST, "FEAR NEVER GOES / AWAY." -> FEAR).

export const normWord = (s) => s.toLowerCase().replace(/[^a-z0-9$%']/g, '');
export const cleanWord = (s) => s.trim().replace(/^["'“”]+|["“”]+$/g, '');

/** Two-line pages: each line <= maxWords and <= maxLineChars; a page ends on . ! ? or a gap > 600 ms.
 *  oneLineRanges (timeline seconds, [from, to)): a page whose FIRST word starts inside a range holds ONE line only
 *  (decided by the page start, like bottomRanges without byFrame). Empty/absent = the original two-line behaviour. */
export const buildTwoLinePages = (captions, maxWords = 4, maxLineChars = 18, skip = [], oneLineRanges = [], trimStartSec = 0) => {
  const maxLinesAt = (startMs) => {
    const s = startMs / 1000 - trimStartSec;
    return oneLineRanges.some((r) => s >= r.from && s < r.to) ? 1 : 2;
  };
  const sk = new Set(skip.map(normWord));
  const words = captions.filter((c) => c.text.trim() && !sk.has(normWord(c.text)));
  const pages = [];
  let lines = [];
  let cur = [];
  const flushLine = () => {
    if (cur.length) lines.push({ words: cur });
    cur = [];
  };
  const flushPage = () => {
    flushLine();
    if (lines.length) {
      const all = lines.flatMap((l) => l.words);
      pages.push({ startMs: all[0].startMs, endMs: all[all.length - 1].endMs, lines });
    }
    lines = [];
  };
  words.forEach((w, i) => {
    const prev = words[i - 1];
    if (prev && w.startMs - prev.endMs > 600) flushPage();
    const chars = cur.reduce((n, x) => n + cleanWord(x.text).length + 1, 0) + cleanWord(w.text).length;
    if (cur.length && (cur.length >= maxWords || chars > maxLineChars)) {
      flushLine();
      if (lines.length >= (oneLineRanges.length ? maxLinesAt(lines[0].words[0].startMs) : 2)) flushPage();
    }
    cur.push(w);
    if (/[.!?]["”]?$/.test(w.text.trim())) flushPage();
  });
  flushPage();
  // hold each page until the next starts (max +300 ms) so nothing flickers
  return pages.map((p, i) => ({ ...p, endMs: Math.min(p.endMs + 300, pages[i + 1]?.startMs ?? p.endMs + 300) }));
};

export const makeIsMoney = (moneyWords = []) => {
  // A money word starting with '=' matches that exact word only ("=edit" lights EDIT, not EDITING / EDITED).
  const mws = moneyWords.map((m) => ({ k: normWord(m), exact: String(m).trim().startsWith('=') })).filter((m) => m.k);
  return (s) => {
    const w = normWord(s);
    if (!w) return false;
    return mws.length ? mws.some(({ k, exact }) => w === k || (!exact && k.length >= 4 && w.startsWith(k))) : /\d|\$/.test(s);
  };
};

/** Per page: [lineIndex, wordIndex] of the ONE accent word, or null.
 *  Within a line the FIRST money word is the candidate (the original per-line behaviour, so blocks that
 *  already had one accent word are unchanged); across the block's lines the LAST line with a candidate wins. */
export const pickHighlight = (page, isMoney) => {
  let hit = null;
  page.lines.forEach((line, li) => {
    const wi = line.words.findIndex((w) => isMoney(w.text));
    if (wi >= 0) hit = [li, wi];
  });
  return hit;
};

/** Accent flags per page/line/word. Throws if a block would show more than one accent word. */
export const highlightMap = (page, isMoney) => {
  const hit = pickHighlight(page, isMoney);
  const flags = page.lines.map((line, li) => line.words.map((_, wi) => !!hit && hit[0] === li && hit[1] === wi));
  const n = flags.flat().filter(Boolean).length;
  if (n > 1) throw new Error(`caption block at ${page.startMs} ms has ${n} accent words (max 1)`);
  return flags;
};
