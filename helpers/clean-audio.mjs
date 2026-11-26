#!/usr/bin/env node
// Audio cleanup, step 1 of every edit (FFmpeg only: no API key, works offline).
// Chain: highpass 80 Hz -> gentle FFT denoise (or arnndn if models/*.rnnn exists) -> light 2:1 compression
//        -> static gain + peak limiter (-2.5 dBFS) -> linear two-pass loudnorm to -14 LUFS integrated, -1.5 dBTP target (<= -1 after AAC), LRA 11.
// Usage:
//   node helpers/clean-audio.mjs public/media/<name>.mp4            cleans IN PLACE (video stream copied untouched);
//                                                                   original kept as public/media/orig/<name>.mp4
//   node helpers/clean-audio.mjs <in> -o <out.mp4|.m4a|.wav>         write elsewhere (audio-only if .m4a/.wav)
//   --loudnorm-only   skip highpass/denoise/compression (fallback if the cleanup makes the voice sound worse)
//   --force           clean again even if the file is already tagged as cleaned
// Prints before/after integrated loudness + true peak as JSON. Exits 3 if the result is off target.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const args = process.argv.slice(2);
const oi = args.indexOf('-o');
const inp = args.find((a, i) => !a.startsWith('-') && (oi < 0 || i !== oi + 1));
if (!inp || !fs.existsSync(inp)) { console.error('usage: node helpers/clean-audio.mjs <in.mp4> [-o out] [--loudnorm-only] [--force]'); process.exit(1); }
const lnOnly = args.includes('--loudnorm-only');
const force = args.includes('--force');
const ff = (a) => { const r = spawnSync('ffmpeg', a, { encoding: 'utf8', maxBuffer: 1 << 26 }); if (r.status !== 0) { console.error(r.stderr); process.exit(r.status || 1); } return r.stderr; };
const tag = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format_tags=comment', '-of', 'default=nw=1:nk=1', inp], { encoding: 'utf8' }).stdout.trim();
if (oi < 0 && /cve-clean-audio/.test(tag) && !force) { console.log(JSON.stringify({ skipped: 'already cleaned', file: inp, tag })); process.exit(0); }
const meter = (f) => {
  const e = ff(['-hide_banner', '-nostats', '-i', f, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-']);
  const s = e.slice(e.lastIndexOf('Summary:'));
  const g = (re) => { const m = s.match(re); return m ? +m[1] : null; };
  return { lufs: g(/I:\s+(-?[\d.]+) LUFS/), lra: g(/LRA:\s+(-?[\d.]+) LU/), true_peak: g(/Peak:\s+(-?[\d.]+) dBFS/) };
};
const before = meter(inp);
const model = fs.existsSync('models') ? fs.readdirSync('models').find((f) => f.endsWith('.rnnn')) : null;
const denoise = model ? `arnndn=m=models/${model}:mix=0.7` : 'afftdn=nr=10:nf=-50:tn=1';
const pre = lnOnly ? [] : ['highpass=f=80', denoise, 'acompressor=threshold=-20dB:ratio=2:attack=20:release=250:knee=4:makeup=1'];
const TARGET = 'I=-14:TP=-1.5:LRA=11';
const lnJson = (chain) => { const s = ff(['-hide_banner', '-nostats', '-i', inp, '-vn', '-af', [...chain, `loudnorm=${TARGET}:print_format=json`].join(','), '-f', 'null', '-']); return JSON.parse(s.slice(s.lastIndexOf('{'), s.lastIndexOf('}') + 1)); };
// pass 1: loudness after the pre-chain -> static gain to -14, then a transparent peak limiter (-2.5 dBFS) so the
// final loudnorm can stay LINEAR (dynamic loudnorm can pump). pass 2: measure. pass 3: linear loudnorm.
const gain = (-14 - +lnJson(pre).input_i).toFixed(2);
const chain = [...pre, `volume=${gain}dB`, 'alimiter=limit=0.75:attack=5:release=60:level=false:latency=1'];
const m = lnJson(chain);
const ln = `loudnorm=${TARGET}:measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true`;
const af = [...chain, ln, 'aresample=48000'].join(',');
const inPlace = oi < 0;
const out = inPlace ? inp.replace(/\.(\w+)$/, '.cleaning.$1') : args[oi + 1];
const ext = path.extname(out).toLowerCase();
const audioOnly = ext === '.wav' || ext === '.m4a';
const codec = ext === '.wav' ? ['-c:a', 'pcm_s16le'] : ['-c:a', 'aac', '-b:a', '192k'];
const note = `cve-clean-audio ${lnOnly ? 'loudnorm-only' : 'full'} ${new Date().toISOString()}`;
ff(['-y', '-v', 'error', '-i', inp, ...(audioOnly ? ['-vn'] : ['-map', '0:v:0?', '-map', '0:a:0', '-c:v', 'copy']),
  '-af', af, ...codec, '-ar', '48000', '-metadata', `comment=${note}`, ...(ext === '.mp4' ? ['-movflags', '+faststart'] : []), out]);
if (inPlace) {
  const dir = path.join(path.dirname(inp), 'orig'); fs.mkdirSync(dir, { recursive: true });
  const bak = path.join(dir, path.basename(inp)); if (!fs.existsSync(bak)) fs.copyFileSync(inp, bak);
  fs.renameSync(out, inp);
}
const after = meter(inPlace ? inp : out);
const ok = after.lufs >= -15 && after.lufs <= -13 && after.true_peak <= -1;
console.log(JSON.stringify({ file: inPlace ? inp : out, mode: lnOnly ? 'loudnorm-only' : 'full', gain_db: +gain, denoise: lnOnly ? null : denoise, before, after, pass: ok }, null, 2));
if (!ok) { console.error('FAIL: cleaned audio is not -14 +/-1 LUFS with true peak <= -1 dBTP'); process.exit(3); }
