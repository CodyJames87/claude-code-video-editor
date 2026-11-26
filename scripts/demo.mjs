// End-to-end smoke test: make the sample clip, render it with every motion effect, finish it, run the QA gate.
// Usage: npm run demo        Output: out/sample-shorts_final.mp4 + out/qa_sample-shorts_final/ (report + contact sheet)
import { spawnSync } from 'node:child_process';

const win = process.platform === 'win32';
const run = (cmd, args) => {
  console.log(`\n> ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { stdio: 'inherit', shell: win });
  if (r.status !== 0) {
    console.error(`\nDEMO FAILED at: ${cmd} ${args.join(' ')}`);
    process.exit(r.status || 1);
  }
};
run('node', ['scripts/py.mjs', 'examples/make_sample.py']);
run('node', ['helpers/check-highlights.mjs', 'examples/sample.props.json']);
run(win ? 'npx.cmd' : 'npx', ['remotion', 'render', 'ShortsVideo', 'out/sample-shorts.mp4', '--props=examples/sample.props.json', '--log=error']);
run('node', ['helpers/finish.mjs', 'out/sample-shorts.mp4']);
run('node', ['scripts/py.mjs', 'helpers/qa_gate.py', 'out/sample-shorts_final.mp4', '--props', 'examples/sample.props.json',
  '--accept-unsure', win ? '"demo sample: synthetic clip with no real face"' : 'demo sample: synthetic clip with no real face']);
console.log('\nDEMO OK: open out/sample-shorts_final.mp4 and out/qa_sample-shorts_final/frames/contact_sheet.jpg');
