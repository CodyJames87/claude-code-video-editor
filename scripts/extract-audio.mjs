// Usage: node scripts/extract-audio.mjs public/media/clip.mp4 [out.wav]
// 16 kHz mono WAV for whisper.cpp (and for ElevenLabs STT upload).
import path from 'node:path';
import { runFfmpeg } from './lib.mjs';

const input = process.argv[2];
if (!input) throw new Error('usage: node scripts/extract-audio.mjs <video> [out.wav]');
const out = process.argv[3] && !process.argv[3].startsWith('--') ? process.argv[3] : input.replace(/\.[^.]+$/, '.16k.wav');
runFfmpeg(['-y', '-v', 'error', '-i', input, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', out]);
console.log(`audio -> ${path.resolve(out)}`);
