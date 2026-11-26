import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
export const WHISPER_DIR = path.join(ROOT, 'whisper.cpp');
export const WHISPER_VERSION = '1.5.5'; // prebuilt Windows binary; built from source on mac/linux
export const WHISPER_MODEL = process.env.WHISPER_MODEL || 'medium.en';

export const ffmpegBin = () => {
  if (process.env.FFMPEG_BIN) return process.env.FFMPEG_BIN;
  const r = spawnSync('ffmpeg', ['-version']);
  if (r.status === 0) return 'ffmpeg';
  // Remotion ships an ffmpeg with its compositor: `npx remotion ffmpeg`
  return null;
};

export const runFfmpeg = (args) => {
  const bin = ffmpegBin();
  if (bin) return execFileSync(bin, args, { stdio: 'inherit' });
  return execFileSync(process.platform === 'win32' ? 'npx.cmd' : 'npx', ['remotion', 'ffmpeg', ...args], { stdio: 'inherit', cwd: ROOT, shell: process.platform === 'win32' });
};

export const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : def;
};

export const writeJson = (p, obj) => {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj, null, 1));
};
