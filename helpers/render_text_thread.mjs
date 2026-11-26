#!/usr/bin/env node
// Render a "Text Thread" animated text post (iMessage-style, 1080x1920) from threads/<name>.json.
// Usage: node helpers/render_text_thread.mjs threads/<name>.json [--no-finish]
// Outputs (spec.output.dir / spec.output.name, default out/<name>/<name>):
//   <stem>-shorts_silent.mp4  the Remotion picture (silent AAC track), refreshed on every render
//   <stem>-shorts.mp4         picture + text SFX mix (default "soft" synthesized tones on bubble lands and typing dots;
//                             no music; see helpers/text_thread_sfx_classic.py, mix in <dir>/sfx/)
//   <stem>-shorts_final.mp4   finish.mjs WITH loudnorm (-14 LUFS, TP <= -1 dBTP gate; iPhone-safe encode)
//   <stem>-cover.png (still at output.coverAt), <stem>.timeline.json (appear times + QC times).
// Opt out of SFX: spec "sfx": false or "none" -> silent AAC track, finish.mjs --no-loudnorm.
// "sfxPreset": "soft" (default) / "classic" = synthesized; "custom" = your own MP3s in assets/textthread/custom/.
// Text is rendered VERBATIM from the spec: never fix spelling or censor.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const specPath = args.find((a) => !a.startsWith('-'));
if (!specPath) { console.error('usage: node helpers/render_text_thread.mjs threads/<name>.json [--no-finish]'); process.exit(1); }
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

// --- validate ---
const errs = [];
if (!spec.name || !/^[a-z0-9-]+$/.test(spec.name)) errs.push('name must be kebab-case');
if (!spec.contact?.name) errs.push('contact.name missing');
if (!Array.isArray(spec.messages) || !spec.messages.length) errs.push('messages missing');
let prevAt = -1;
(spec.messages || []).forEach((m, i) => {
  if (m.from !== 'them' && m.from !== 'me') errs.push(`message ${i + 1}: from must be "them" or "me"`);
  if (typeof m.text !== 'string' || !m.text.trim()) errs.push(`message ${i + 1}: empty text`);
  if (m.highlight && !m.text.includes(m.highlight)) errs.push(`message ${i + 1}: highlight "${m.highlight}" not in text`);
  if (m.at !== undefined) { if (m.at <= prevAt) errs.push(`message ${i + 1}: "at" must increase`); prevAt = m.at; }
});
if (spec.messages.filter((m) => m.highlight).length > 1) errs.push('only ONE accent highlight per thread');
if (errs.length) { console.error('SPEC FAIL:\n  ' + errs.join('\n  ')); process.exit(4); }

// --- timeline (mirror of src/textthread/timeline.ts; QC times only, the render uses the TS version) ---
const FPS = 30;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
// Auto-timing read hold (only for messages WITHOUT "at"; explicit "at" + "duration" specs are unaffected).
// ~25 % more generous than the old clamp(0.5 + 0.045 * len, 0.9, 3.0) so threads are easier to read:
//   hold = clamp(0.62 + 0.056 * len, 1.1, 3.7)   (e.g. 20 chars 1.40 -> 1.74 s, 50 chars 2.75 -> 3.42 s). Same in timeline.ts.
const hold = (m) => m.hold ?? clamp(0.62 + 0.056 * m.text.length, 1.1, 3.7);
const typing = (m) => m.typing ?? (m.from === 'them' ? clamp(0.4 + 0.01 * m.text.length, 0.4, 0.7) : 0.3);
const pace = spec.pace ?? 1, sv = spec.startVisible ?? 0;
const fr = (s) => Math.round(s * pace * FPS);
let t = 0;
const rows = spec.messages.map((m, i) => {
  if (i < sv) { if (i === sv - 1) t = fr(hold(m)); return { i: i + 1, from: m.from, appear: 0, text: m.text }; }
  let appear;
  if (m.at !== undefined) { appear = Math.round(m.at * FPS); t = appear + fr(hold(m)); }
  else { t += fr(typing(m)); appear = t; t += fr(hold(m)); }
  return { i: i + 1, from: m.from, appear: +(appear / FPS).toFixed(2), text: m.text };
});
const lastF = Math.round(rows[rows.length - 1].appear * FPS);
const frames = spec.duration ? Math.round(spec.duration * FPS) : lastF + Math.round((spec.endHold ?? 4) * FPS);
const total = frames / FPS;
console.log(`TEXT THREAD ${spec.name}: ${spec.messages.length} messages, ${total.toFixed(2)} s, ${frames} frames`);
for (const r of rows) console.log(`  ${String(r.i).padStart(2)} ${r.from === 'me' ? 'BLUE' : 'GREY'} @${r.appear.toFixed(2)}s  ${JSON.stringify(r.text)}`);

const dir = spec.output?.dir ?? path.join('out', spec.name);
const stem = path.join(dir, spec.output?.name ?? spec.name);
fs.mkdirSync(dir, { recursive: true });
const qc = [0.2, ...rows.filter((r) => r.appear > 0).map((r) => +(r.appear + 0.4).toFixed(2)), +(total - 0.3).toFixed(2)];
const coverAt = spec.output?.coverAt ?? null;
fs.writeFileSync(`${stem}.timeline.json`, JSON.stringify({ duration: total, frames, messages: rows, cover_at: coverAt, qc_times: qc }, null, 2));
console.log(`timeline: ${stem}.timeline.json\nQC times: ${qc.join(',')}`);

const sh = (cmd, a) => { const r = spawnSync(cmd, a, { stdio: 'inherit', shell: true }); if (r.status !== 0) process.exit(r.status || 1); };
// --- render ---
sh('npx', ['remotion', 'render', 'TextThread', `${stem}-shorts.mp4`, `--props=${specPath}`, '--enforce-audio-track', '--log=error']);
if (coverAt !== null) sh('npx', ['remotion', 'still', 'TextThread', `${stem}-cover.png`, `--props=${specPath}`, `--frame=${Math.round(coverAt * FPS)}`, '--log=error']);
// Keep the untouched picture: the SFX mux always reads <stem>-shorts_silent.mp4, so refresh it from this render.
fs.copyFileSync(`${stem}-shorts.mp4`, `${stem}-shorts_silent.mp4`);
console.log(`silent picture: ${stem}-shorts_silent.mp4`);
if (args.includes('--no-finish')) process.exit(0);
const sfxOff = spec.sfx === false || spec.sfx === 'none';
if (sfxOff) {
  sh('node', ['helpers/finish.mjs', `${stem}-shorts.mp4`, '--no-loudnorm']);
  console.log('AUDIO: silent track ("sfx" off in the spec; loudness gate not applicable).');
} else {
  // Locked-tone mix (pre-leveled to ~-14 LUFS with a fast peak limiter so loudnorm stays LINEAR) muxed onto the silent picture.
  sh(process.platform === 'win32' ? 'python' : 'python3', ['helpers/text_thread_sfx_classic.py', specPath]);
  sh('node', ['helpers/finish.mjs', `${stem}-shorts.mp4`]);
  console.log('AUDIO: text SFX (soft synthesized tones unless sfxPreset says otherwise), no music; finish.mjs loudness gate applied.');
}
