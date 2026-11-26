#!/usr/bin/env python3
"""Face-safe gate for graphics on a reframed (9:16 / 4:5) edit.

Detects the speaker's face in the SOURCE video (OpenCV Haar, frontal), extends it to the whole head (cap on top, chin/beard
below, a little each side), maps it through the edit's layout (a cover-fit video panel + an optional camera scale) onto
the output frame, and checks proposed overlay boxes against it with padding.

  python helpers/face_safe.py check public/media/<name>.mp4 --t0 6.0 --t1 7.4 \
      --panel 0,420,1080,1500 --focus 0.5,0.4 [--cam-scale 1.12 --cam-origin 0.5,0.37] \
      --box chip=60,440,960,90 [--box other=x,y,w,h ...] [--pad 40] [--step 0.2] [--json out.json]

  python helpers/face_safe.py scan public/media/<name>.mp4 --t0 0 --t1 36 --panel 0,420,1080,1500 --focus 0.5,0.4
      -> head box on the output frame per sample + the union (min top / max bottom): use it to plan bars, banners,
         chips, count-ups and split bands.

Layout args: --panel x,y,w,h = where the source video is drawn on the output frame (cover fit, CSS object-position =
--focus). --frame 1080x1920 (default). --cam-scale/--cam-origin = a PushIn/PunchIn peak scale about (ox,oy) 0-1 of the
panel (Camera.tsx semantics), so peaks can be checked too.
Verdict per box: SAFE (no sample hits the padded head), UNSAFE (any sample hits), UNSURE (face found in < 60 % of the
samples: the detector can't vouch for it -> do NOT place the graphic). Exit 0 = all SAFE, 1 = any UNSAFE, 2 = any UNSURE.
This is a GATE, not a substitute for QC: still look at the frames.
"""
import argparse, json, os, sys

try:
    import cv2
except ImportError:  # optional helper dependency
    print('face_safe.py needs OpenCV: pip install "opencv-python-headless<5"', file=sys.stderr)
    sys.exit(3)

CAP_UP = 0.60    # cap tip above the Haar box top (measured ~0.47 face-heights on a ball cap, + margin)
CHIN_DOWN = 0.32 # beard / chin below the Haar box bottom (measured ~0.24, + margin)
SIDE = 0.18      # ears / headphones each side
MAX_HOLD = 1.0   # s: a missed sample may borrow the nearest detection this close in time (flagged 'held')


def parse_box(s):
    name, _, rest = s.partition('=')
    x, y, w, h = [float(v) for v in rest.split(',')]
    return name, (x, y, w, h)


def _cascade(name):
    return cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, name))


def detect(path, t0, t1, step):
    """Per sample: the face box (source px) or None. Frontal (default + alt2) and both profiles; the candidate
    closest to the clip's median face is kept, outliers (hands, shirt logos, posters) are rejected, and a missed
    sample may hold the nearest detection within MAX_HOLD s (marked held=True)."""
    times = []
    t = t0
    while t <= t1 + 1e-6:
        times.append(t)
        t += step
    return detect_at(path, times)


def detect_at(path, times, min_face=0.12, max_hold=MAX_HOLD):
    """Same detector as detect(), at an explicit list of times (s). Used by qa_gate.py / crop_previews.py
    (punch peaks, card mids). min_face = smallest face as a fraction of the frame height."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f'cannot open {path}')
    sw, sh = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    front = [_cascade('haarcascade_frontalface_default.xml'), _cascade('haarcascade_frontalface_alt2.xml')]
    prof = _cascade('haarcascade_profileface.xml')
    raw = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        cands = []
        if ok:
            g = cv2.equalizeHist(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
            ms = (int(sh * min_face), int(sh * min_face))
            for c in front:
                cands += [list(map(float, f)) for f in c.detectMultiScale(g, scaleFactor=1.08, minNeighbors=6, minSize=ms)]
            cands += [list(map(float, f)) for f in prof.detectMultiScale(g, scaleFactor=1.08, minNeighbors=6, minSize=ms)]
            gf = cv2.flip(g, 1)
            for x, y, w, h in prof.detectMultiScale(gf, scaleFactor=1.08, minNeighbors=6, minSize=ms):
                cands.append([float(sw - x - w), float(y), float(w), float(h)])
        raw.append((round(t, 3), cands))
    cap.release()
    # median track from the largest candidate per sample, then keep the candidate nearest to it
    big = [max(c, key=lambda f: f[2] * f[3]) for _, c in raw if c]
    if not big:
        return [{'t': t, 'face': None, 'held': False} for t, _ in raw], (sw, sh)
    med = lambda v: sorted(v)[len(v) // 2]
    mx = med([f[0] + f[2] / 2 for f in big]); my = med([f[1] + f[3] / 2 for f in big]); mw = med([f[2] for f in big])
    out = []
    for t, c in raw:
        good = [f for f in c if abs(f[0] + f[2] / 2 - mx) < 0.9 * mw and abs(f[1] + f[3] / 2 - my) < 0.9 * mw and 0.6 * mw < f[2] < 1.6 * mw]
        face = min(good, key=lambda f: abs(f[0] + f[2] / 2 - mx) + abs(f[1] + f[3] / 2 - my)) if good else None
        out.append({'t': t, 'face': face, 'held': False})
    det = [s for s in out if s['face']]
    for s in out:
        if s['face'] is None and det:
            near = min(det, key=lambda d: abs(d['t'] - s['t']))
            if abs(near['t'] - s['t']) <= max_hold:
                s['face'], s['held'] = near['face'], True
    return out, (sw, sh)


def head_from_face(f):
    x, y, w, h = f
    return [x - SIDE * w, y - CAP_UP * h, w * (1 + 2 * SIDE), h * (1 + CAP_UP + CHIN_DOWN)]


def mapper(src_wh, panel, focus, cam_scale=1.0, cam_origin=(0.5, 0.35)):
    sw, sh = src_wh
    px, py, pw, ph = panel
    s = max(pw / sw, ph / sh)                      # cover
    ox = (pw - sw * s) * focus[0]                  # CSS object-position
    oy = (ph - sh * s) * focus[1]
    cx, cy = cam_origin[0] * pw, cam_origin[1] * ph

    def pt(x, y):
        X, Y = ox + x * s, oy + y * s              # panel coords at scale 1
        X, Y = cx + (X - cx) * cam_scale, cy + (Y - cy) * cam_scale
        return px + X, py + Y

    def box(b):
        x0, y0 = pt(b[0], b[1])
        x1, y1 = pt(b[0] + b[2], b[1] + b[3])
        # the panel clips the video: anything outside it is not visible (but a head cut off = a framing problem)
        return [x0, y0, x1 - x0, y1 - y0]
    return box


def hits(a, b, pad):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw + pad <= bx or bx + bw + pad <= ax or ay + ah + pad <= by or by + bh + pad <= ay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['check', 'scan'])
    ap.add_argument('video')
    ap.add_argument('--t0', type=float, default=0.0)
    ap.add_argument('--t1', type=float, default=None)
    ap.add_argument('--step', type=float, default=0.2)
    ap.add_argument('--frame', default='1080x1920')
    ap.add_argument('--panel', help='x,y,w,h of the video panel on the output frame (default: the whole frame)')
    ap.add_argument('--focus', default='0.5,0.4')
    ap.add_argument('--cam-scale', type=float, default=1.0)
    ap.add_argument('--cam-origin', default='0.5,0.35')
    ap.add_argument('--box', action='append', default=[], help='name=x,y,w,h on the output frame')
    ap.add_argument('--pad', type=float, default=40.0)
    ap.add_argument('--json')
    a = ap.parse_args()
    fw, fh = [int(v) for v in a.frame.lower().split('x')]
    panel = [float(v) for v in a.panel.split(',')] if a.panel else [0, 0, fw, fh]
    focus = [float(v) for v in a.focus.split(',')]
    origin = [float(v) for v in a.cam_origin.split(',')]
    t1 = a.t1 if a.t1 is not None else a.t0
    samples, src_wh = detect(a.video, a.t0, t1, a.step)
    m = mapper(src_wh, panel, focus, a.cam_scale, origin)
    heads = [m(head_from_face(s['face'])) if s['face'] else None for s in samples]
    found = [h for h in heads if h]
    rate = sum(1 for s in samples if s['face'] and not s['held']) / max(1, len(samples))
    cover = len(found) / max(1, len(heads))
    res = {'video': a.video, 't0': a.t0, 't1': t1, 'detect_rate': round(rate, 2), 'covered_rate': round(cover, 2), 'panel': panel, 'focus': focus,
           'cam_scale': a.cam_scale, 'samples': len(heads)}
    if found:
        u = [min(h[0] for h in found), min(h[1] for h in found), max(h[0] + h[2] for h in found), max(h[1] + h[3] for h in found)]
        res['head_union'] = {'left': round(u[0]), 'top': round(u[1]), 'right': round(u[2]), 'bottom': round(u[3])}
        res['head_in_panel'] = u[1] >= panel[1] and u[3] <= panel[1] + panel[3]
    if a.cmd == 'check':
        res['boxes'] = {}
        for spec in a.box:
            name, b = parse_box(spec)
            bad = [s['t'] for s, h in zip(samples, heads) if h and hits(b, h, a.pad)]
            if rate < 0.6 or cover < 0.9:
                verdict, code = 'UNSURE', 2
            elif bad:
                verdict, code = 'UNSAFE', 1
            else:
                verdict, code = 'SAFE', 0
            gap = None
            if found:
                # smallest vertical/horizontal clearance between the box and the head union
                gx = max(u[0] - (b[0] + b[2]), b[0] - u[2], 0)
                gy = max(u[1] - (b[1] + b[3]), b[1] - u[3], 0)
                gap = round(max(gx, gy))
            res['boxes'][name] = {'box': b, 'verdict': verdict, 'hit_times': bad[:12], 'clearance_px': gap}
        print(json.dumps(res, indent=2))
        code = 1 if any(v['verdict'] == 'UNSAFE' for v in res['boxes'].values()) else 2 if any(v['verdict'] == 'UNSURE' for v in res['boxes'].values()) else 0
    else:
        res['heads'] = [{'t': s['t'], 'held': s['held'], 'head': [round(v) for v in h] if h else None} for s, h in zip(samples, heads)]
        print(json.dumps({k: v for k, v in res.items() if k != 'heads'}, indent=2))
        code = 0 if rate >= 0.6 and cover >= 0.9 else 2
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(res, f, indent=2)
    sys.exit(code)


if __name__ == '__main__':
    main()
