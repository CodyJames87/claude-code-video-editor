// Browser-Frame B-Roll capture: record a clean, slow scroll of a REAL public web page with LOCAL Chrome
// (puppeteer-core + the Chrome already installed on this PC; no cloud browser, no browser download).
// Frame-by-frame screenshots (deterministic, no dropped frames) -> ffmpeg -> silent H.264 MP4 + a JSON sidecar.
//
// Usage:
//   node helpers/capture_browser_broll.mjs <url> -o public/media/broll/<name>.mp4
//        [--width 1080] [--height 620] [--seconds 5] [--fps 30] [--scroll 900] [--start 0] [--zoom 1.0]
//        [--hide "<css selector>,..."] [--chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"]
//
//   --scroll   px to scroll over the clip (eased in-out). 0 = no scroll (use --zoom for a slow push instead).
//   --zoom     end scale of a slow centred zoom (1.0 = none, 1.06 = gentle push).
//   --start    initial scroll offset (px) so the clip opens on the interesting part.
// Output: <out>.mp4 (yuv420p, 30 fps, no audio) + <out>.json { url, capturedAt, width, height, seconds, title }.
// Popups: cookie banners, donation banners, chat widgets and other fixed overlays are hidden before capture.
// Use only logo-safe public pages (no company sites, no customer names). Cache the result; renders never hit the network.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);
const url = args.find((a) => /^https?:\/\//.test(a));
const opt = (k, d) => {
  const i = args.findIndex((a) => a === `--${k}` || (k.length === 1 && a === `-${k}`));
  return i >= 0 ? args[i + 1] : d;
};
const out = opt('o', null) || opt('out', null);
if (!url || !out) {
  console.error('usage: node helpers/capture_browser_broll.mjs <url> -o public/media/broll/<name>.mp4 [--seconds 5] [--scroll 900]');
  process.exit(2);
}
const W = +opt('width', 1080);
const H = +opt('height', 620);
const SECS = +opt('seconds', 5);
const FPS = +opt('fps', 30);
const SCROLL = +opt('scroll', 900);
const START = +opt('start', 0);
const ZOOM = +opt('zoom', 1.0);
const extraHide = opt('hide', '');

const chromeCandidates = [
  opt('chrome', ''),
  process.env.CHROME_PATH || '',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const executablePath = chromeCandidates.find((p) => fs.existsSync(p));
if (!executablePath) {
  console.error('No local Chrome/Edge found. Pass --chrome <path>.');
  process.exit(3);
}

// generic popup / widget hiding (our own list, applied as CSS before the capture)
const HIDE = [
  '#siteNotice', '#centralNotice', '.cn-fundraising', '.frb', '.wmde-banner', '.mw-dismissable-notice',
  '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]', '[class*="consent" i]',
  '[id*="intercom" i]', '[class*="intercom" i]', '[id*="drift" i]', '[id*="hubspot" i]', '[class*="chat-widget" i]',
  'iframe[title*="chat" i]', '#vector-toc-pinned-container .vector-pinnable-header',
  ...extraHide.split(',').map((s) => s.trim()).filter(Boolean),
];

const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'broll-'));
const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ['--hide-scrollbars', '--mute-audio', '--disable-notifications', `--window-size=${W},${H}`],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
});
let title = '';
try {
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
  title = await page.title();
  await page.addStyleTag({ content: `${HIDE.join(',')}{display:none !important;visibility:hidden !important}\nhtml{scroll-behavior:auto !important}` });
  // hide any remaining fixed/sticky overlay that covers the bottom/right corner (chat bubbles, "back to top", promos)
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (cs.position !== 'fixed') continue;
      const r = el.getBoundingClientRect();
      const small = r.width < window.innerWidth * 0.6 && r.height < window.innerHeight * 0.6;
      const lowCorner = r.top > window.innerHeight * 0.4;
      if (small && lowCorner) el.style.setProperty('display', 'none', 'important');
    }
  });
  await new Promise((r) => setTimeout(r, 800));
  const n = Math.round(SECS * FPS);
  for (let i = 0; i < n; i++) {
    const k = n > 1 ? i / (n - 1) : 0;
    const y = START + SCROLL * ease(k);
    const z = 1 + (ZOOM - 1) * ease(k);
    await page.evaluate((yy, zz) => {
      window.scrollTo(0, yy);
      document.documentElement.style.transformOrigin = '50% ' + (yy + window.innerHeight / 2) + 'px';
      document.documentElement.style.transform = zz !== 1 ? `scale(${zz})` : '';
    }, y, z);
    await page.screenshot({ path: path.join(tmp, `f${String(i).padStart(4, '0')}.png`), type: 'png' });
  }
} finally {
  await browser.close();
}

fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
const ff = spawnSync('ffmpeg', ['-v', 'error', '-y', '-framerate', String(FPS), '-i', path.join(tmp, 'f%04d.png'),
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-color_range', 'tv',
  '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', '-an', out], { stdio: 'inherit' });
fs.rmSync(tmp, { recursive: true, force: true });
if (ff.status !== 0) process.exit(ff.status ?? 1);
const meta = { url, title, capturedAt: new Date().toISOString(), width: W, height: H, seconds: SECS, fps: FPS, scroll: SCROLL, start: START, zoom: ZOOM, browser: path.basename(executablePath) };
fs.writeFileSync(out.replace(/\.mp4$/i, '.json'), JSON.stringify(meta, null, 2));
console.log(JSON.stringify({ ok: true, out, ...meta }));
