// Word-level transcript -> Caption[] JSON for Remotion (@remotion/captions format).
//
//   node scripts/transcribe.mjs public/media/clip.mp4                 # local whisper.cpp (default)
//   node scripts/transcribe.mjs public/media/clip.mp4 --from stt.json # convert an ElevenLabs STT (MCP) /
//                                                                     # faster-whisper / Descript word JSON
// Writes public/media/clip.captions.json  (override with --out)
import fs from 'node:fs';
import path from 'node:path';
import { elevenLabsTranscriptToCaptions } from '@remotion/elevenlabs';
import { WHISPER_DIR, WHISPER_MODEL, WHISPER_VERSION, arg, runFfmpeg, writeJson } from './lib.mjs';

const input = process.argv[2];
if (!input) throw new Error('usage: node scripts/transcribe.mjs <video> [--from transcript.json] [--out x.captions.json]');
const out = arg('out', input.replace(/\.[^.]+$/, '.captions.json'));
const from = arg('from');

/** Generic word list (faster-whisper / Descript / normalized) -> Caption[] */
const wordsToCaptions = (data) => {
  let words = Array.isArray(data) ? data : data.words ?? (data.segments ?? []).flatMap((s) => s.words ?? []);
  words = words.filter((w) => !w.type || w.type === 'word');
  const ms = words.length && Math.max(...words.map((w) => Number(w.end ?? w.end_time ?? 0))) > 20000;
  return words
    .map((w, i) => {
      const s = Number(w.start ?? w.start_time ?? w.startTime);
      const e = Number(w.end ?? w.end_time ?? w.endTime);
      const text = String(w.text ?? w.word ?? '').trim();
      const k = ms ? 1 : 1000;
      return { text: (i ? ' ' : '') + text, startMs: Math.round(s * k), endMs: Math.round(e * k), timestampMs: Math.round(((s + e) / 2) * k), confidence: w.prob ?? w.probability ?? w.confidence ?? null };
    })
    .filter((c) => c.text.trim());
};

let captions;
if (from) {
  const data = JSON.parse(fs.readFileSync(from, 'utf8'));
  const looksEleven = Array.isArray(data?.words) && data.words.some((w) => w.type === 'word' || w.type === 'spacing') && ('language_code' in data || 'text' in data);
  if (looksEleven) {
    try {
      captions = elevenLabsTranscriptToCaptions({ transcript: data }).captions;
    } catch (e) {
      console.warn('ElevenLabs converter failed, using generic word converter:', e.message);
    }
  }
  captions ??= wordsToCaptions(data);
  console.log(`converted ${from} (${looksEleven ? 'ElevenLabs' : 'generic words'})`);
} else {
  const { transcribe, toCaptions } = await import('@remotion/install-whisper-cpp');
  if (!fs.existsSync(WHISPER_DIR)) throw new Error('whisper.cpp not installed: run `npm run setup:whisper` (or use --from with an ElevenLabs STT JSON)');
  const wav = path.join(path.dirname(out), path.basename(input).replace(/\.[^.]+$/, '.16k.wav'));
  runFfmpeg(['-y', '-v', 'error', '-i', input, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav]);
  const res = await transcribe({ inputPath: path.resolve(wav), whisperPath: WHISPER_DIR, whisperCppVersion: WHISPER_VERSION, model: arg('model', WHISPER_MODEL), tokenLevelTimestamps: true, printOutput: false });
  captions = toCaptions({ whisperCppOutput: res }).captions;
}
writeJson(out, captions);
console.log(`${captions.length} words -> ${path.resolve(out)}`);
console.log(captions.slice(0, 40).map((c) => c.text).join(''));
