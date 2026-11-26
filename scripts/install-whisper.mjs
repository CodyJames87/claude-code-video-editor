// One-time: installs whisper.cpp + a model into ./whisper.cpp (free, local, no API key).
// Usage: node scripts/install-whisper.mjs [--model medium.en]
import { downloadWhisperModel, installWhisperCpp } from '@remotion/install-whisper-cpp';
import { WHISPER_DIR, WHISPER_MODEL, WHISPER_VERSION, arg } from './lib.mjs';

const model = arg('model', WHISPER_MODEL);
await installWhisperCpp({ to: WHISPER_DIR, version: WHISPER_VERSION, printOutput: true });
await downloadWhisperModel({ folder: WHISPER_DIR, model, printOutput: true });
console.log(`whisper.cpp ${WHISPER_VERSION} + ${model} ready in ${WHISPER_DIR}`);
