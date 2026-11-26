#!/usr/bin/env node
// Node finisher (no Python needed). Two-pass loudnorm to -14 LUFS / TP <= -1 dBTP and the iPhone-safe encode:
// libx264 High@4.1, yuv420p, TV (limited) range, BT.709 tags, CRF 21, maxrate 10M, AAC 160k 48 kHz, +faststart.
// Usage: node helpers/finish.mjs out/<name>-shorts.mp4 [-o out/<name>-shorts_final.mp4] [--no-loudnorm]
//   --no-loudnorm: re-encode only (use it to convert an already-finished final to the phone format).
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
const args = process.argv.slice(2);
const inp = args.find((a) => !a.startsWith('-') && args[args.indexOf(a) - 1] !== '-o');
if (!inp) { console.error('usage: node helpers/finish.mjs <in.mp4> [-o out.mp4] [--no-loudnorm]'); process.exit(1); }
const oi = args.indexOf('-o');
let out = oi >= 0 ? args[oi + 1] : inp.replace(/\.mp4$/i, '_final.mp4');
const noLn = args.includes('--no-loudnorm');
const run = (a) => { const r = spawnSync('ffmpeg', a, { encoding: 'utf8', maxBuffer: 1 << 26 }); if (r.status !== 0) { console.error(r.stderr); process.exit(r.status || 1); } return r.stderr; };
const TARGET = 'I=-14:TP=-1.5:LRA=11';
let af = [];
if (!noLn) {
  const s = run(['-hide_banner', '-nostats', '-i', inp, '-vn', '-af', `loudnorm=${TARGET}:print_format=json`, '-f', 'null', '-']);
  const m = JSON.parse(s.slice(s.lastIndexOf('{'), s.lastIndexOf('}') + 1));
  af = ['-af', `loudnorm=${TARGET}:measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true`];
}
const same = out === inp;
const tmp = same ? out.replace(/\.mp4$/i, '.tmp_phone.mp4') : out;
run(['-y', '-v', 'error', '-i', inp, ...af,
  '-vf', 'scale=out_range=tv:flags=lanczos,format=yuv420p',
  '-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.1', '-preset', 'medium', '-crf', '21', '-maxrate', '10M', '-bufsize', '20M',
  '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
  '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', tmp]);
if (same) fs.renameSync(tmp, out);
const e = run(['-hide_banner', '-nostats', '-i', out, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-']);
const I = (e.match(/I:\s+(-?[\d.]+) LUFS/g) || []).pop(); const TP = (e.match(/Peak:\s+(-?[\d.]+) dBFS/g) || []).pop();
const p = spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=pix_fmt,color_range,profile,level', '-of', 'compact=p=0:nk=0', out], { encoding: 'utf8' }).stdout.trim();
console.log(JSON.stringify({ output: out, size_mb: +(fs.statSync(out).size / 1e6).toFixed(2), loudness: I, true_peak: TP, video: p }, null, 2));
// LOUDNESS GATE (QC): the final must be -14 +/-1 LUFS integrated and true peak <= -1 dBTP, else exit 3 (QC FAIL).
const nI = I ? +I.match(/-?[\d.]+/)[0] : NaN; const nTP = TP ? +TP.match(/-?[\d.]+/)[0] : NaN;
// Sidecar for helpers/qa_gate.py (the QA gate consumes finish's own verdict instead of re-deciding it).
const loudOk = nI >= -15 && nI <= -13 && nTP <= -1; const fmtOk = /pix_fmt=yuv420p/.test(p) && /color_range=tv/.test(p);
const st = fs.statSync(out);
fs.writeFileSync(out.replace(/\.mp4$/i, '') + '.finish.json', JSON.stringify({ output: out, time: new Date().toISOString(), size: st.size, mtime_ms: Math.round(st.mtimeMs),
  loudnorm: !noLn, integrated_lufs: nI, true_peak_dbtp: nTP, loudness_pass: loudOk, format_pass: fmtOk, video: p,
  exit_code: !noLn && !loudOk ? 3 : !fmtOk ? 2 : 0 }, null, 2));
if (!noLn && !(nI >= -15 && nI <= -13 && nTP <= -1)) { console.error(`QC FAIL: loudness ${nI} LUFS / true peak ${nTP} dBTP (need -14 +/-1 LUFS, TP <= -1). Re-run finish; if it still fails, check helpers/clean-audio.mjs ran on the source.`); process.exit(3); }
console.log(`LOUDNESS: PASS (${nI} LUFS, TP ${nTP} dBTP)`);
if (!/pix_fmt=yuv420p/.test(p) || !/color_range=tv/.test(p)) { console.error('FAIL: final is not yuv420p / tv range'); process.exit(2); }
