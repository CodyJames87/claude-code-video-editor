// Run a Python script with whichever Python is on this machine (python3, python, or the Windows "py" launcher).
// Usage: node scripts/py.mjs <script.py> [args...]
import { spawnSync } from 'node:child_process';

const cands = process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
const py = cands.find((c) => spawnSync(c, ['--version'], { stdio: 'ignore', shell: process.platform === 'win32' }).status === 0);
if (!py) {
  console.error('Python 3 not found. Install it from https://www.python.org/downloads (Windows: tick "Add to PATH").');
  process.exit(1);
}
const r = spawnSync(py, process.argv.slice(2), { stdio: 'inherit', shell: process.platform === 'win32' });
process.exit(r.status ?? 1);
