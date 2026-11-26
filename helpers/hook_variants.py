#!/usr/bin/env python3
"""Hook Variations: build standalone variants of ONE picture-locked body with different hook openings, without
retiming the body by hand.

Each variant = [hook range of the source] + [body range of the source], cut frame-exact with ffmpeg (re-encoded,
audio kept). For each variant the helper also writes:
  - a captions JSON: hook words shifted to 0, body words shifted to follow the hook (same Caption[] format), and
  - optionally (--props) a props JSON copied from a template: videoSrc/transcriptJson point at the variant, numeric
    `at` values inside the body are shifted by the new offset, word anchors (`{"word": ...}`) are left alone because
    they re-resolve on the new captions automatically (a warning is printed if a hook repeats a body anchor word,
    since `occurrence` would then shift).

Hooks must be things he ACTUALLY SAID (ranges of the same source or another real clip). Never invent a hook line.

Usage:
  python helpers/hook_variants.py --src public/media/<name>.mp4 --captions public/media/<name>.captions.json \
      --body 3.48 [--body-end 35.98] --hook natural=0:3.0 [--hook alt=6.14:7.33 ...] \
      [--props props/<name>.json] [--out-dir public/media/hookvars] [--dry-run]
Outputs: <out-dir>/<name>-hook-<label>.mp4 + .captions.json (+ props/<name>-hook-<label>.json with --props).
Then render each props file as usual (ShortsVideo -> finish.mjs -> QC -> deliver). Only deliver what was asked for.
"""
import argparse, copy, json, os, subprocess, sys


def load_caps(p):
    d = json.load(open(p, encoding='utf8'))
    return d if isinstance(d, list) else d['captions']


def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum() or ch in "$%'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--captions', required=True)
    ap.add_argument('--body', type=float, required=True, help='body start (s) in the source')
    ap.add_argument('--body-end', type=float, help='body end (s); default = end of the source')
    ap.add_argument('--hook', action='append', required=True, help='label=start:end (s) of a REAL spoken hook in the source')
    ap.add_argument('--props', help='props template to copy per variant')
    ap.add_argument('--out-dir', default='public/media/hookvars')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base = os.path.splitext(os.path.basename(a.src))[0]
    caps = load_caps(a.captions)
    if a.body_end is None:
        dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.src],
                             capture_output=True, text=True).stdout.strip()
        a.body_end = float(dur)
    body_caps = [c for c in caps if c['startMs'] >= a.body * 1000 - 1 and c['endMs'] <= a.body_end * 1000 + 50]
    tmpl = json.load(open(a.props, encoding='utf8')) if a.props else None
    os.makedirs(a.out_dir, exist_ok=True)
    plan = []
    for spec in a.hook:
        label, _, rng = spec.partition('=')
        h0, h1 = [float(v) for v in rng.split(':')]
        if not (h1 > h0):
            sys.exit(f'bad hook range {spec}')
        hook_caps = [c for c in caps if c['startMs'] >= h0 * 1000 - 1 and c['endMs'] <= h1 * 1000 + 50]
        if not hook_caps:
            sys.exit(f'hook "{label}" has no transcript words in {h0}-{h1}s: hooks must be real speech')
        hlen = h1 - h0
        shift = hlen - a.body  # body time t -> t + shift on the variant timeline
        new_caps = [dict(c, startMs=round(c['startMs'] - h0 * 1000), endMs=round(c['endMs'] - h0 * 1000)) for c in hook_caps]
        new_caps += [dict(c, startMs=round(c['startMs'] + shift * 1000), endMs=round(c['endMs'] + shift * 1000)) for c in body_caps]
        name = f'{base}-hook-{label}'
        mp4 = os.path.join(a.out_dir, name + '.mp4')
        capj = os.path.join(a.out_dir, name + '.captions.json')
        fc = (f'[0:v]trim=start={h0}:end={h1},setpts=PTS-STARTPTS[hv];[0:a]atrim=start={h0}:end={h1},asetpts=PTS-STARTPTS[ha];'
              f'[0:v]trim=start={a.body}:end={a.body_end},setpts=PTS-STARTPTS[bv];[0:a]atrim=start={a.body}:end={a.body_end},asetpts=PTS-STARTPTS[ba];'
              f'[hv][ha][bv][ba]concat=n=2:v=1:a=1[v][a]')
        cmd = ['ffmpeg', '-v', 'error', '-y', '-i', a.src, '-filter_complex', fc, '-map', '[v]', '-map', '[a]',
               '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
               '-ar', '48000', '-movflags', '+faststart', mp4]
        hook_text = ' '.join(c['text'].strip() for c in hook_caps)
        item = {'label': label, 'hook': [h0, h1], 'hook_text': hook_text, 'body': [a.body, a.body_end],
                'duration': round(hlen + a.body_end - a.body, 3), 'video': mp4, 'captions': capj}
        if tmpl is not None:
            p = copy.deepcopy(tmpl)
            rel = lambda x: os.path.relpath(x, 'public').replace('\\', '/')
            p['videoSrc'], p['transcriptJson'], p['trim'] = rel(mp4), rel(capj), None
            hw = [norm(c['text']) for c in hook_caps]
            for o in p.get('overlays', []):
                if isinstance(o.get('at'), (int, float)):
                    o['at'] = round(o['at'] + shift, 3) if o['at'] >= a.body else o['at']
                elif isinstance(o.get('at'), dict):
                    ph = [norm(w) for w in o['at']['word'].split() if norm(w)]
                    if any(hw[i:i + len(ph)] == ph for i in range(len(hw))):
                        print(f'WARN [{label}] anchor "{o["at"]["word"]}" also appears in the hook: check its occurrence', file=sys.stderr)
            pp = os.path.join(os.path.dirname(a.props), name + '.json')
            item['props'] = pp
            if not a.dry_run:
                json.dump(p, open(pp, 'w', encoding='utf8'), indent=2)
        item['ffmpeg'] = ' '.join(cmd)
        if not a.dry_run:
            subprocess.run(cmd, check=True)
            json.dump(new_caps, open(capj, 'w', encoding='utf8'), indent=1)
        plan.append(item)
    print(json.dumps({'dry_run': a.dry_run, 'variants': plan}, indent=2))


if __name__ == '__main__':
    main()
