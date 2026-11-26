#!/usr/bin/env python3
"""Reference style breakdown: measure how a reel FILE is edited (camera moves, cuts, captions, faces, color, audio)
and write a style guide in this editor's effect vocabulary, with a CONFLICTS section against CLAUDE.md rules.

  python helpers/style_breakdown.py <reel.mp4> [--captions sidecar.captions.json] [--captions-offset S]
                                    [--out out/style-breakdown/<name>] [--name N]

Read-only on the input (never writes next to it). Never applies anything: no props, no src/, no renders.
Outputs (in --out): cuts.json, cuts.csv, contact_sheet.jpg, breakdown.json, style_guide.md.

How it works (all heuristics, all offline: OpenCV + numpy + PIL + ffmpeg):
- Every frame is read once (cv2), downscaled to ANALYSIS_W wide gray. Burned-in text is masked out, then ORB features +
  cv2.estimateAffinePartial2D(RANSAC) between frame n-1 and n give a per-frame scale ratio and an inlier count.
  A frame-difference spike with few inliers = hard cut; a scale jump = punch; scale ~1 with a widespread change = jump
  cut (a splice); a small, local change = an overlay/graphic pop (not a cut). The per-frame scale is integrated inside
  each shot to find slow zooms (linear = Steady Crawl, eased = Eased Push).
- Text regions: morphological contrast (bright fill touching dark outline / dark ink touching a light card),
  horizontal closing, text-shaped connected components. No OCR: words, case and paraphrase cannot be read.
- Faces: helpers/face_safe.py (Haar) on the final frames. Audio: ffmpeg ebur128 + silencedetect + a numpy STFT.
"""
import argparse, csv, json, math, os, re, subprocess, sys, time

import numpy as np

try:
    import cv2
except ImportError:
    print('style_breakdown.py needs OpenCV: pip install "opencv-python-headless<5"', file=sys.stderr)
    sys.exit(3)
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import face_safe  # noqa: E402  (CAP_UP, CHIN_DOWN, SIDE, detect_at, head_from_face)

# ---------------------------------------------------------------------------------------------- thresholds
ANALYSIS_W = 540           # px: motion / text analysis width (height keeps the aspect)
ORB_FEATURES = 1200
RANSAC_PX = 2.0            # reprojection threshold at ANALYSIS_W
MIN_INLIERS = 20           # fewer inliers between n-1 and n = the two frames are not the same shot
MIN_INLIER_RATIO = 0.30    # inliers / cross-checked matches
MAD_ABS_MIN = 5.0          # gray levels: smallest mean frame difference that can be an edit
MAD_K = 3.0                # x local median difference (+-MAD_WIN frames) = a candidate edit
MAD_WIN = 15
PUNCH_FAST = 0.012         # |log scale| per frame above this = a fast move (crawl is ~0.0016/frame)
PUNCH_MIN = 0.04           # total |ratio-1| of a fast run to count as a punch (>= 1.04 in, <= 0.96 out)
PUNCH_MIN_INSTANT = 0.03   # ...or >= 3 % when it happens within 1-3 frames (a punch on top of a crawl: 1.08 -> 1.12)
CUT_ECHO_FRAMES = 6        # events this soon after a hard / layout cut are the same cut (layout animations)
PUNCH_MAX_FRAMES = 15      # fast runs longer than this are reported as fast pushes, not punches
LAYOUT_LO, LAYOUT_HI = 0.75, 1.40  # per-frame scale outside this = a layout change (split / band), not a punch
JUMP_SCALE_TOL = 0.015     # |scale-1| <= this with a big change = jump cut candidate
JUMP_CELL_DIFF = 14.0      # gray levels: aligned residual per 8x8-grid cell that counts as "changed"
JUMP_MIN_AREA = 0.06       # share of grid cells changed for a jump cut; less = a local overlay / graphic pop
JUMP_FACE_AREA = 0.25      # ...and at least this share of the cells over the head must change (a splice moves the head;
                           #    a card fade or a hand gesture changes the frame away from the head = overlay/motion)
JUMP_ISOLATION = 2.3       # a splice is a one-frame spike: diff >= 2.3 x the median diff of the 3 frames each side
                           #    (a hand gesture keeps changing over several frames)
GRID = (12, 8)             # rows x cols of the residual grid
MERGE_FRAMES = 2           # candidate frames this close merge into one event
SLOW_RATE_MIN = 0.012      # scale/s: a slow zoom is at least this fast...
PUSH_MIN_SEC = 1.0         # ...for at least this long...
PUSH_MIN_GROWTH = 0.03     # ...and grows at least 3 %
SNAP_AFTER_PUSH_SEC = 1.5  # a push followed by a snap-out / punch within this = a rendered camera move
PUSH_MIN_R2 = 0.985        # a rendered zoom fits a ramp almost perfectly; a speaker leaning in/out is jittery (lower R^2)
EASED_MARGIN = 0.90        # eased wins only if its RMSE < 0.90 x the linear RMSE (and vice versa)
BAND_ROW_STD = 2.0         # a flat graphic band row (rendered solid color); shirts / walls are noisier
SAMPLE_SEC = 0.25          # captions / graphics sampling step
FACE_SEC = 0.5             # face sampling step
PAGE_IOU = 0.45            # caption text-mask IoU below this between samples = a page flip
TIGHT_FACE_FRAC = 0.20     # Haar face height / frame height at rest above this = an already-tight crop
SILENCE_DB, SILENCE_SEC = -35, 0.25
BED_LIKELY_DB = -42.0      # median level in speech pauses above this = a music bed is likely
BED_POSSIBLE_DB = -50.0
SFX_BAND = (3000, 12000)   # Hz: whoosh / pop energy band
SFX_DB = 9.0               # band peak this far over the local median, within SFX_WIN of an edit = an SFX hit
SFX_WIN = (-0.35, 0.20)
SFX_CTRL_PCT = 95          # ...and above this percentile of the score at random non-edit times
CONTACT_CELLS = 24
RULE_CAPS = {'whooshes': 4, 'pops': 3, 'whoosh_gap_s': 8.0, 'tight_punch_max': 1.12, 'standard_punch': 1.16,
             'stacked_max': 1.23, 'hero': 1.30}


# ---------------------------------------------------------------------------------------------- helpers
def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')


def probe(path):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate,nb_frames',
             '-show_entries', 'format=duration', '-of', 'json', path])
    d = json.loads(r.stdout or '{}')
    v = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not v:
        raise SystemExit(f'no video stream in {path}')
    num, den = (v.get('r_frame_rate') or '30/1').split('/')
    fps = float(num) / float(den or 1)
    return {'width': int(v['width']), 'height': int(v['height']), 'fps': round(fps, 3),
            'duration': float(d.get('format', {}).get('duration') or 0),
            'has_audio': any(s.get('codec_type') == 'audio' for s in d.get('streams', []))}


def color_name(bgr):
    b, g, r = [int(c) for c in bgr]
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]
    h, s, v = int(hsv[0]) * 2, hsv[1] / 255.0, hsv[2] / 255.0
    if v < 0.22:
        return 'black / ink'
    if s < 0.22:
        return 'white' if v > 0.82 else ('light gray' if v > 0.55 else 'gray')
    if s < 0.4 and v < 0.5:
        return 'dark gray'
    if h < 6 or h >= 340:          # rendered #FF5722 lands at ~8-14 deg: keep it orange
        name = 'red'
    elif h < 40:
        name = 'orange' if s > 0.55 else 'tan / skin'
    elif h < 68:
        name = 'yellow'
    elif h < 165:
        name = 'green'
    elif h < 200:
        name = 'cyan / teal'
    elif h < 260:
        name = 'blue'
    elif h < 300:
        name = 'purple'
    else:
        name = 'pink / magenta'
    if v < 0.45 and name not in ('tan / skin',):
        name = 'dark ' + name
    return name


def hexcol(bgr):
    b, g, r = [int(c) for c in bgr]
    return f'#{r:02X}{g:02X}{b:02X}'


def kmeans_colors(pix, k):
    pix = np.float32(pix.reshape(-1, 3))
    if len(pix) < k * 4:
        return []
    k = min(k, len(pix))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0)
    _, lab, cen = cv2.kmeans(pix, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    cnt = np.bincount(lab.ravel(), minlength=k)
    out = [{'hex': hexcol(cen[i]), 'name': color_name(cen[i]), 'share': round(float(cnt[i]) / len(pix), 3)}
           for i in np.argsort(-cnt)]
    return out


def load_words(path, offset):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if isinstance(d, dict):
        d = d.get('words') or d.get('captions') or [w for s in d.get('segments', []) for w in s.get('words', [])]
    words = []
    for w in d or []:
        text = (w.get('text') or w.get('word') or '').strip()
        if not text:
            continue
        if 'startMs' in w:
            s, e = w['startMs'] / 1000.0, w.get('endMs', w['startMs']) / 1000.0
        else:
            s, e = float(w.get('start', 0)), float(w.get('end', w.get('start', 0)))
        words.append({'text': text, 'start': s + offset, 'end': e + offset})
    words.sort(key=lambda w: w['start'])
    return words


# ---------------------------------------------------------------------------------------------- text regions
def text_regions(bgr):
    """Burned-in text candidates on a ANALYSIS_W frame. Returns (lines [x,y,w,h,polarity], contrast mask)."""
    H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bright = (gray > 200).astype(np.uint8)
    dark = (gray < 70).astype(np.uint8)
    k3 = np.ones((3, 3), np.uint8)
    edge = cv2.dilate(bright, k3) & cv2.dilate(dark, k3)        # bright stroke touching a dark outline / ink on card
    kx = max(9, W // 36)
    closed = cv2.morphologyEx(edge, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 5)))
    closed = cv2.dilate(closed, cv2.getStructuringElement(cv2.MORPH_RECT, (kx // 2, 3)))
    n, _, st, _ = cv2.connectedComponentsWithStats(closed, 8)
    boxes = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (0.012 * H <= h <= 0.11 * H and w >= 0.07 * W and w >= 1.3 * h):
            continue
        roi_e = edge[y:y + h, x:x + w]
        dens = roi_e.mean()
        bfr = bright[y:y + h, x:x + w].mean()
        dfr = dark[y:y + h, x:x + w].mean()
        if dens < 0.10 or bfr < 0.06 or dfr < 0.05:
            continue
        # polarity: light card around dark text vs bright text with dark outline
        pad = max(4, h // 3)
        y0, y1, x0, x1 = max(0, y - pad), min(H, y + h + pad), max(0, x - pad), min(W, x + w + pad)
        ring = np.concatenate([gray[y0:y, x0:x1].ravel(), gray[y + h:y1, x0:x1].ravel()])
        pol = 'dark-on-light' if ring.size and ring.mean() > 190 else 'light-on-dark-outline'
        boxes.append([int(x), int(y), int(w), int(h), pol])
    # merge boxes on the same line
    boxes.sort(key=lambda b: (b[1], b[0]))
    lines = []
    for b in boxes:
        for L in lines:
            ov = min(L[1] + L[3], b[1] + b[3]) - max(L[1], b[1])
            gap = max(L[0], b[0]) - min(L[0] + L[2], b[0] + b[2])
            if ov > 0.5 * min(L[3], b[3]) and gap < 0.06 * W:
                x0, y0 = min(L[0], b[0]), min(L[1], b[1])
                x1, y1 = max(L[0] + L[2], b[0] + b[2]), max(L[1] + L[3], b[1] + b[3])
                L[:4] = [x0, y0, x1 - x0, y1 - y0]
                break
        else:
            lines.append(list(b))
    return lines, edge


def blocks_from_lines(lines, H):
    lines = sorted(lines, key=lambda l: l[1])
    blocks = []
    for L in lines:
        if blocks:
            B = blocks[-1]
            last = B['lines'][-1]
            gap = L[1] - (last[1] + last[3])
            xov = min(B['box'][0] + B['box'][2], L[0] + L[2]) - max(B['box'][0], L[0])
            if gap < 0.9 * max(L[3], last[3]) and xov > 0:
                B['lines'].append(L)
                x0, y0 = min(B['box'][0], L[0]), min(B['box'][1], L[1])
                x1 = max(B['box'][0] + B['box'][2], L[0] + L[2])
                y1 = max(B['box'][1] + B['box'][3], L[1] + L[3])
                B['box'] = [x0, y0, x1 - x0, y1 - y0]
                continue
        blocks.append({'lines': [L], 'box': L[:4]})
    return blocks


def block_colors(bgr, blk):
    """Fill pixels of a text block, and how many saturated (highlighted) word blobs it holds.
    A highlight pixel is saturated (S > 100, V > 80), sits inside the letter strokes (next to the dark outline for
    outlined captions) and is NOT the background's own hue (a blue shirt behind white captions is not a highlight)."""
    H, W = bgr.shape[:2]
    x, y, w, h = blk['box']
    roi = bgr[y:y + h, x:x + w]
    if roi.size == 0:
        return None, 0, None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    Hh, S, V = hsv[..., 0].astype(np.int16), hsv[..., 1], hsv[..., 2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    pol = blk['lines'][0][4]
    sat = (S > 100) & (V > 80)
    if pol == 'dark-on-light':
        fill = (gray < 90) | sat
        col = sat.copy()
    else:
        near_dark = cv2.dilate((gray < 60).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        fill = near_dark & (V > 150)
        col = sat & near_dark & (gray >= 60)
    # background hue: a ring around the block
    pad = max(6, h // 4)
    y0, y1, x0, x1 = max(0, y - pad), min(H, y + h + pad), max(0, x - pad), min(W, x + w + pad)
    ring = np.ones((y1 - y0, x1 - x0), bool)
    ring[y - y0:y - y0 + h, x - x0:x - x0 + w] = False
    rh = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)[ring]
    rs = rh[rh[:, 1] > 100]
    if len(rs) > 0.3 * len(rh) and len(rs):
        bh = int(np.median(rs[:, 0]))
        dh = np.abs(Hh - bh)
        col &= np.minimum(dh, 180 - dh) > 12
    fill_px = roi[fill | col]
    lh = int(np.median([l[3] for l in blk['lines']]))
    words, other = 0, 0
    hue = None
    if col.sum() >= max(25, 0.04 * max(1, fill.sum())):
        m = cv2.dilate(col.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, lh // 3), 3)))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        comps = [i for i in range(1, n) if st[i][4] >= 20 and st[i][3] >= 0.35 * lh]
        if comps:
            # main highlight hue = the biggest blob's; blobs of another hue (a logo behind the text...) are counted apart
            hues = {i: int(np.median(Hh[(lab == i) & col])) for i in comps if ((lab == i) & col).any()}
            main = max(hues, key=lambda i: st[i][4]) if hues else None
            for i, hv in hues.items():
                d = abs(hv - hues[main])
                if min(d, 180 - d) <= 12:
                    words += 1
                else:
                    other += 1
            if main is not None:
                hue = color_name(np.median(roi[(lab == main) & col], axis=0))
    return fill_px, words, hue, other


# ---------------------------------------------------------------------------------------------- graphics
def graphics_sample(bgr):
    H, W = bgr.shape[:2]
    small = cv2.resize(bgr, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    q = (small // 24).reshape(-1, 3)
    keys, cnt = np.unique(q, axis=0, return_counts=True)
    top = int(np.argmax(cnt))
    share = cnt[top] / len(q)
    top_bgr = keys[top] * 24 + 12
    card = {'share': round(float(share), 3), 'color': color_name(top_bgr), 'hex': hexcol(top_bgr)} if share >= 0.55 else None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    row_std = gray.std(axis=1)
    uni = row_std < BAND_ROW_STD
    runs = []
    i = 0
    while i < H:
        if uni[i]:
            j = i
            while j < H and uni[j]:
                j += 1
            c = bgr[i:j].reshape(-1, 3).mean(axis=0)
            # a thin line (progress bar, hairline) inside a band doesn't split it
            if runs and i - runs[-1][1] <= 0.015 * H and np.abs(runs[-1][2] - c).max() < 12:
                runs[-1][1] = j
            else:
                runs.append([i, j, c])
            i = j
        else:
            i += 1
    bands = [{'y0': round(a / H, 3), 'y1': round(b / H, 3), 'color': color_name(c), 'hex': hexcol(c)}
             for a, b, c in runs if (b - a) >= 0.03 * H]
    # progress-bar-like thin saturated bars in the top 25 % / bottom 15 %
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = ((hsv[..., 1] > 110) & (hsv[..., 2] > 120)).astype(np.uint8)
    bars = []
    for (r0, r1) in ((0, int(0.25 * H)), (int(0.85 * H), H)):
        rows = []
        for r in range(r0, r1):
            row = sat[r]
            if row.sum() < 0.06 * W:
                rows.append(0)
                continue
            d = np.diff(np.concatenate([[0], row, [0]]))
            st, en = np.where(d == 1)[0], np.where(d == -1)[0]
            k = int(np.argmax(en - st))
            rows.append(int(en[k] - st[k]) if (en[k] - st[k]) >= 0.06 * W else 0)
            if rows[-1]:
                rows[-1] = (rows[-1], int(st[k]))
        r = 0
        while r < len(rows):
            if rows[r]:
                s = r
                while r < len(rows) and rows[r]:
                    r += 1
                hgt = r - s
                if hgt <= max(3, int(0.012 * H)):
                    lens = [rows[k][0] for k in range(s, r)]
                    x0 = min(rows[k][1] for k in range(s, r))
                    c = bgr[r0 + s:r0 + r, x0:x0 + max(lens)].reshape(-1, 3).mean(axis=0)
                    above = r0 + s - 2
                    bars.append({'y': round((r0 + s) / H, 4), 'h_px': hgt, 'x0': round(x0 / W, 3),
                                 'len': round(max(lens) / W, 3), 'color': color_name(c), 'hex': hexcol(c)})
            else:
                r += 1
    hsv_small = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    return {'card': card, 'bands': bands, 'bars': bars,
            'bright': float(hsv_small[..., 2].mean() / 255), 'sat': float(hsv_small[..., 1].mean() / 255)}, small


# ---------------------------------------------------------------------------------------------- pass 1: frames
def analyze_frames(path, info, log):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f'cannot open {path}')
    fps = info['fps']
    W0, H0 = info['width'], info['height']
    aw = ANALYSIS_W
    ah = int(round(aw * H0 / W0 / 2)) * 2
    sx = W0 / aw
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES, fastThreshold=10)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    step = max(1, int(round(fps * SAMPLE_SEC)))
    frames = []
    samples = []
    prev = None
    n = 0
    t0 = time.time()
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        small = cv2.resize(fr, (aw, ah), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        lines, edge = text_regions(small)
        tmask = np.zeros((ah, aw), np.uint8)
        for x, y, w, h, _ in lines:
            cv2.rectangle(tmask, (x - 8, y - 8), (x + w + 8, y + h + 8), 255, -1)
        kp, des = orb.detectAndCompute(gray, cv2.bitwise_not(tmask))
        rec = {'n': n, 't': n / fps, 'mad': 0.0, 'scale': 1.0, 'scale_full': 1.0, 'tx': 0.0, 'ty': 0.0, 'inl': 0, 'matches': 0,
               'ok': False, 'cells': 0.0}
        if prev is not None:
            pg, pkp, pdes, pmask, pM = prev
            valid = cv2.bitwise_not(cv2.bitwise_or(tmask, pmask)) > 0
            diff = cv2.absdiff(gray, pg)
            rec['mad'] = float(diff[valid].mean()) if valid.any() else float(diff.mean())
            if des is not None and pdes is not None and len(kp) >= 8 and len(pkp) >= 8:
                ms = [m for m in bf.match(pdes, des) if m.distance < 64]
                rec['matches'] = len(ms)
                if len(ms) >= 8:
                    a = np.float32([pkp[m.queryIdx].pt for m in ms])
                    b = np.float32([kp[m.trainIdx].pt for m in ms])
                    M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX)
                    if M is not None:
                        ni = int(inl.sum())
                        rec['inl'] = ni
                        rec['scale'] = rec['scale_full'] = float(math.hypot(M[0, 0], M[1, 0]))
                        rec['tx'], rec['ty'] = float(M[0, 2]) * sx, float(M[1, 2]) * sx
                        rec['ok'] = ni >= MIN_INLIERS and ni >= MIN_INLIER_RATIO * len(ms)
                        if rec['ok']:
                            warped = cv2.warpAffine(pg, M, (aw, ah), borderValue=0)
                            wv = cv2.warpAffine(np.full_like(pg, 255), M, (aw, ah), borderValue=0) > 0
                            res = cv2.absdiff(gray, warped).astype(np.float32)
                            res[~(wv & valid)] = 0
                            cy, cx = GRID
                            hh, ww = ah // cy, aw // cx
                            cells = res[:hh * cy, :ww * cx].reshape(cy, hh, cx, ww).mean(axis=(1, 3)) > JUMP_CELL_DIFF
                            rec['cells'] = float(cells.mean())
                            if rec['mad'] >= MAD_ABS_MIN * 0.5:
                                rec['grid'] = cells
        frames.append(rec)
        if n % step == 0:
            g, gsmall = graphics_sample(small)
            blocks = blocks_from_lines(lines, ah)
            bl = []
            for B in blocks:
                fill_px, hw, hue, oth = block_colors(small, B)
                bl.append({'box': [int(v * sx) for v in B['box']], 'lines': len(B['lines']),
                           'line_h': [int(l[3] * sx) for l in B['lines']], 'polarity': B['lines'][0][4],
                           'hl_words': hw, 'hl_color': hue, 'other_hue_blobs': oth,
                           'fill': fill_px[::max(1, len(fill_px) // 400)] if fill_px is not None and len(fill_px) else None})
            sig = cv2.resize(edge * 255, (aw // 4, ah // 4), interpolation=cv2.INTER_AREA) > 40
            samples.append({'n': n, 't': n / fps, 'blocks': bl, 'g': g, 'sig': sig, 'px': gsmall[::4, ::4].reshape(-1, 3)})
        prev = (gray, kp, des, tmask, None)
        n += 1
        if n % 300 == 0:
            log(f'  frames {n} ({n / max(1e-6, time.time() - t0):.0f} fps)')
    cap.release()
    return frames, samples


# ---------------------------------------------------------------------------------------------- events
def detect_events(frames, fps, head=None):
    """head = [x0,y0,x1,y1] 0-1 of the frame (median head box) for the jump-cut test, or None."""
    N = len(frames)
    mad = np.array([f['mad'] for f in frames])
    ls = np.array([math.log(max(1e-3, f['scale'])) if f['ok'] else 0.0 for f in frames])
    cand = []
    for i in range(1, N):
        lo, hi = max(1, i - MAD_WIN), min(N, i + MAD_WIN + 1)
        nb = np.concatenate([mad[lo:i], mad[i + 1:hi]])
        base = float(np.median(nb)) if nb.size else 0.0
        frames[i]['base'] = base
        if mad[i] >= max(MAD_ABS_MIN, MAD_K * base):
            cand.append(i)
    events = []
    used = set()
    # fast scale runs (punches / fast pushes / layout)
    fast = [i for i in range(1, N) if frames[i]['ok'] and abs(ls[i]) > PUNCH_FAST]
    runs = []
    for i in fast:
        if runs and i - runs[-1][-1] <= 2 and np.sign(ls[i]) == np.sign(ls[runs[-1][-1]]):
            runs[-1].append(i)
        else:
            runs.append([i])
    for r in runs:
        tot = math.exp(sum(ls[k] for k in range(r[0], r[-1] + 1) if frames[k]['ok']))
        nf = r[-1] - r[0] + 1
        single = [math.exp(ls[k]) for k in r]
        if any(s < LAYOUT_LO or s > LAYOUT_HI for s in single):
            events.append({'n': r[0], 'kind': 'layout cut', 'ratio': round(tot, 3), 'frames': nf})
        elif abs(tot - 1) >= (PUNCH_MIN_INSTANT if nf <= 3 else PUNCH_MIN):
            if nf <= PUNCH_MAX_FRAMES:
                kind = 'punch in' if tot > 1 else 'punch out'
            else:
                kind = 'fast push in' if tot > 1 else 'fast pull out'
            events.append({'n': r[0], 'kind': kind, 'ratio': round(tot, 3), 'frames': nf, 'peak_n': r[-1]})
        else:
            continue
        used.update(range(r[0] - MERGE_FRAMES, r[-1] + MERGE_FRAMES + 1))
    for i in cand:
        if i in used:
            continue
        f = frames[i]
        hf = None
        if not f['ok']:
            kind = 'hard cut'
        elif f['scale'] < LAYOUT_LO or f['scale'] > LAYOUT_HI:
            kind = 'layout cut'
        else:
            if head is not None and f.get('grid') is not None:
                g = f['grid']
                r0, r1 = int(head[1] * GRID[0]), max(int(head[1] * GRID[0]) + 1, int(math.ceil(head[3] * GRID[0])))
                c0, c1 = int(head[0] * GRID[1]), max(int(head[0] * GRID[1]) + 1, int(math.ceil(head[2] * GRID[1])))
                hf = float(g[max(0, r0):r1, max(0, c0):c1].mean())
            big = f['cells'] >= JUMP_MIN_AREA and abs(f['scale_full'] - 1) <= 0.08
            nb = np.concatenate([mad[max(1, i - 3):i], mad[i + 1:i + 4]])
            iso = mad[i] / max(0.5, float(np.median(nb))) if nb.size else 99.0
            kind = ('jump cut' if big and iso >= JUMP_ISOLATION and (hf is None or hf >= JUMP_FACE_AREA)
                    else 'overlay change')
        events.append({'n': i, 'kind': kind, 'ratio': round(f['scale'], 3), 'frames': 1,
                       'inliers': f['inl'], 'changed_area': round(f['cells'], 2), 'mad': round(f['mad'], 1)})
        if hf is not None:
            events[-1]['head_changed'] = round(hf, 2)
        used.update(range(i - MERGE_FRAMES, i + MERGE_FRAMES + 1))
    events.sort(key=lambda e: e['n'])
    # merge near-duplicates (keep the strongest kind)
    pri = {'hard cut': 0, 'layout cut': 1, 'punch in': 2, 'punch out': 2, 'fast push in': 2, 'fast pull out': 2,
           'jump cut': 3, 'overlay change': 4}
    merged = []
    for e in events:
        if merged and (e['n'] - merged[-1]['n'] <= MERGE_FRAMES or
                       (merged[-1]['kind'] in ('hard cut', 'layout cut') and e['n'] - merged[-1]['n'] <= CUT_ECHO_FRAMES)):
            if pri[e['kind']] < pri[merged[-1]['kind']]:
                merged[-1] = e
            continue
        merged.append(e)
    for e in merged:
        e['t'] = round(e['n'] / fps, 3)
        e['inliers'] = e.get('inliers', frames[e['n']]['inl'])
    # absolute scale vs the shot's base frame (reset at hard / layout cuts)
    A = 0.0
    absn = np.zeros(N)
    cut_frames = {e['n'] for e in merged if e['kind'] in ('hard cut', 'layout cut')}
    for i in range(N):
        if i in cut_frames:
            A = 0.0
        elif frames[i]['ok']:
            A += ls[i]
        absn[i] = A
    for e in merged:
        if e['kind'].startswith(('punch', 'fast')):
            pk = e.get('peak_n', e['n'])
            e['scale_before'] = round(math.exp(absn[max(0, e['n'] - 1)]), 3)
            e['scale_after'] = round(math.exp(absn[pk]), 3)
            e['peak_t'] = round(pk / fps, 3)
    return merged, ls, absn


def refine_cuts(events, samples):
    """Name what a cut goes to: a full-frame card, or a change of the flat-band layout (= a layout cut)."""
    def sig(sm):
        return tuple((b['color'], round(b['y0'], 1), round(b['y1'], 1)) for b in sm['g']['bands'] if b['y1'] - b['y0'] >= 0.05)
    for e in events:
        if e['kind'] not in ('hard cut', 'layout cut'):
            continue
        bef = [sm for sm in samples if sm['t'] <= e['t'] - 0.1]
        aft = [sm for sm in samples if sm['t'] >= e['t'] + 0.1]
        if not bef or not aft:
            continue
        b, a = bef[-1], aft[0]
        if a['g']['card']:
            e['detail'] = f"to a full-frame {a['g']['card']['color']} card"
        elif b['g']['card']:
            e['detail'] = 'from a full-frame card'
        elif sig(b) != sig(a):
            e['kind'] = 'layout cut'
            e['detail'] = 'the flat-band layout changes'


def detect_pushes(frames, ls, events, fps, face_samples=None):
    N = len(frames)
    stops = sorted({0, N} | {e['n'] for e in events if e['kind'] != 'overlay change'} |
                   {e.get('peak_n', e['n']) + 1 for e in events if e['kind'] != 'overlay change'})
    pushes = []
    h = max(2, int(round(0.2 * fps)))
    for a, b in zip(stops[:-1], stops[1:]):
        a2, b2 = a + 2, b - 1
        if b2 - a2 < PUSH_MIN_SEC * fps:
            continue
        seg = np.array([ls[i] if frames[i]['ok'] and abs(ls[i]) <= PUNCH_FAST else 0.0 for i in range(a2, b2)])
        C = np.cumsum(seg)
        k = 7
        Cs = np.convolve(np.pad(C, (k // 2, k // 2), mode='edge'), np.ones(k) / k, mode='valid')
        L = len(Cs)
        slope = np.zeros(L)
        for i in range(L):
            lo, hi = max(0, i - h), min(L - 1, i + h)
            if hi > lo:
                slope[i] = (Cs[hi] - Cs[lo]) / ((hi - lo) / fps)
        for sign in (1, -1):
            on = sign * slope >= SLOW_RATE_MIN
            i = 0
            while i < L:
                if not on[i]:
                    i += 1
                    continue
                j = i
                while j < L and on[j]:
                    j += 1
                if (j - i) / fps >= PUSH_MIN_SEC and sign * (Cs[min(L - 1, j)] - Cs[i]) >= math.log(1 + PUSH_MIN_GROWTH) * 0.8:
                    pushes.append(fit_push(Cs, i, j, a2, fps, sign))
                i = j
    pushes = [p for p in pushes if p and abs(p['to'] / p['from'] - 1) >= PUSH_MIN_GROWTH]
    # a camera push on a talking head shows a full-size face; motion inside a split band / B-roll / card does not
    if face_samples:
        hs = [f['face'][3] for f in face_samples if f.get('face')]
        mh = float(np.median(hs)) if hs else 0
        for p in pushes:
            win = [f for f in face_samples if p['start'] - 0.01 <= f['t'] <= p['end'] + 0.01]
            okf = [f for f in win if f.get('face') and f['face'][3] >= 0.6 * mh]
            if win and len(okf) < 0.5 * len(win):
                p['source'] = 'motion inside a graphic / split layout / B-roll (no full-size face), not a camera push'
                p['library'] = '-'
    # a slow push that ends in a snap-out (fast scale drop) or a punch is a rendered camera move, even if the speaker
    # also moves under it (tight crops): the edit snapped it back
    for p in pushes:
        if p['direction'] != 'in':
            continue
        nxt = [e for e in events if e['kind'] in ('punch out', 'punch in') and 0 <= e['t'] - p['end'] <= SNAP_AFTER_PUSH_SEC]
        if nxt:
            p['ends_with'] = f"{nxt[0]['kind']} x{nxt[0]['ratio']:.3f} at {nxt[0]['t']:.2f}s"
            if p['source'].startswith('probably the speaker'):
                p['source'] = 'camera zoom'
                p['fit_confidence'] = 'low (speaker moves under it)'
    pushes.sort(key=lambda p: p['start'])
    for e in events:
        if e['kind'] in ('punch in', 'fast push in'):
            prev = [p for p in pushes if p['source'] == 'camera zoom' and p['direction'] == 'in' and 0 <= e['t'] - p['end'] <= SNAP_AFTER_PUSH_SEC]
            e['peak_scale_est'] = round(e['ratio'] * (prev[-1]['to'] / prev[-1]['from'] if prev else 1.0), 3)
    for e in events:
        if e['kind'] == 'punch out':
            ins = [x for x in events if x['kind'] in ('punch in', 'fast push in') and 0 < e['t'] - x['t'] <= 5.0]
            pp = [q for q in pushes if q['source'] == 'camera zoom' and q['direction'] == 'in' and 0 <= e['t'] - q['end'] <= SNAP_AFTER_PUSH_SEC]
            e['undoes'] = (f"punch in at {ins[-1]['t']:.2f}s" if ins else f"push {pp[-1]['start']:.2f}-{pp[-1]['end']:.2f}s" if pp else None)
    return pushes


def camera_pushes(pushes):
    return [p for p in pushes if p['source'] == 'camera zoom']


def fit_push(Cs, i, j, off, fps, sign):
    L = len(Cs)
    w0, w1 = max(0, i - int(fps)), min(L - 1, j + int(fps))
    t = np.arange(w0, w1 + 1)
    y = Cs[w0:w1 + 1]
    best = {}
    st = 2
    for model in ('linear', 'smoothstep', 'cubic'):
        bm = None
        for s0 in range(w0, min(i + int(0.3 * fps), w1) + 1, st):
            for s1 in range(max(j - int(0.3 * fps), s0 + int(0.5 * fps)), w1 + 1, st):
                u = np.clip((t - s0) / max(1, s1 - s0), 0, 1)
                if model == 'smoothstep':
                    u = u * u * (3 - 2 * u)
                elif model == 'cubic':
                    u = np.where(u < 0.5, 4 * u ** 3, 1 - (-2 * u + 2) ** 3 / 2)
                X = np.stack([np.ones_like(u), u], 1)
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                rm = float(np.sqrt(np.mean((X @ coef - y) ** 2)))
                if bm is None or rm < bm[0]:
                    bm = (rm, s0, s1, coef)
        best[model] = bm
    lin = best['linear']
    eas = min(best['smoothstep'], best['cubic'], key=lambda m: m[0])
    if eas[0] < EASED_MARGIN * lin[0]:
        style, use, conf = 'eased', eas, 'clear'
    elif lin[0] < EASED_MARGIN * eas[0]:
        style, use, conf = 'linear', lin, 'clear'
    else:
        style, use, conf = ('linear' if lin[0] <= eas[0] else 'eased'), (lin if lin[0] <= eas[0] else eas), 'unclear'
    rm, s0, s1, coef = use
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - (rm ** 2 * len(y)) / sst if sst > 0 else 0.0
    sc0, sc1 = math.exp(coef[0]), math.exp(coef[0] + coef[1])
    dur = (s1 - s0) / fps
    return {'start': round((off + s0) / fps, 3), 'end': round((off + s1) / fps, 3), 'duration': round(dur, 2),
            'from': round(sc0, 3), 'to': round(sc1, 3), 'rate_per_s': round((sc1 - sc0) / dur, 4) if dur else 0,
            'direction': 'in' if sign > 0 else 'out', 'easing': style, 'fit_confidence': conf,
            'rmse_linear': round(lin[0], 5), 'rmse_eased': round(eas[0], 5), 'r2': round(r2, 3),
            'source': 'camera zoom' if r2 >= PUSH_MIN_R2 else 'probably the speaker moving (lean in/out), not a zoom',
            'library': ('Steady Crawl' if style == 'linear' else 'Eased Push') if sign > 0 else 'slow pull-out (not in library)'}


# ---------------------------------------------------------------------------------------------- captions
def caption_report(samples, info, words, duration):
    H, W = info['height'], info['width']
    with_text = [s for s in samples if s['blocks']]
    zones = {}
    for s in with_text:
        for b in s['blocks']:
            yc = (b['box'][1] + b['box'][3] / 2) / H
            z = 'top' if yc < 0.30 else 'center' if yc < 0.58 else 'lower third' if yc < 0.86 else 'bottom'
            zones.setdefault(z, []).append(b)
    if not with_text:
        return {'detected': False, 'note': 'no burned-in text found by the heuristic'}, None
    main_zone = max(zones, key=lambda z: len(zones[z]))
    zb = zones[main_zone]
    y0 = np.percentile([b['box'][1] for b in zb], 10) / H
    y1 = np.percentile([b['box'][1] + b['box'][3] for b in zb], 90) / H
    lines = [b['lines'] for b in zb]
    lh = [h for b in zb for h in b['line_h']]
    pol = [b['polarity'] for b in zb]
    fills = [b['fill'] for b in zb if b['fill'] is not None]
    fill_colors = kmeans_colors(np.concatenate(fills), 4) if fills else []
    hl_blocks = [b for b in zb if b['hl_words']]
    hl_counts = [b['hl_words'] for b in zb]
    hues = {}
    for b in hl_blocks:
        hues[b['hl_color']] = hues.get(b['hl_color'], 0) + 1
    # page flips in the main zone
    zy0, zy1 = int(max(0, y0 - 0.02) * H / W * ANALYSIS_W / 4), int(min(1, y1 + 0.02) * H / W * ANALYSIS_W / 4)
    flips, present, prev = [], [], None
    for s in samples:
        sig = s['sig'][zy0:zy1]
        has = any(main_zone == ('top' if (b['box'][1] + b['box'][3] / 2) / H < 0.30 else 'center' if (b['box'][1] + b['box'][3] / 2) / H < 0.58
                               else 'lower third' if (b['box'][1] + b['box'][3] / 2) / H < 0.86 else 'bottom') for b in s['blocks'])
        present.append(has)
        if has and prev is not None:
            inter = (sig & prev).sum()
            uni = (sig | prev).sum()
            if uni and inter / uni < PAGE_IOU:
                flips.append(round(s['t'], 2))
        prev = sig if has else None
    vis = sum(present) * SAMPLE_SEC
    pages = len(flips) + max(1, sum(1 for a, b in zip([False] + present, present) if b and not a))
    rep = {
        'detected': True,
        'samples_with_text_pct': round(100 * len(with_text) / max(1, len(samples)), 1),
        'zones_pct': {z: round(100 * len(v) / sum(len(x) for x in zones.values()), 1) for z, v in zones.items()},
        'main_zone': main_zone,
        'main_zone_y_pct': [round(100 * y0, 1), round(100 * y1, 1)],
        'block_bottom_px_median': int(np.median([b['box'][1] + b['box'][3] for b in zb])),
        'lines_per_block': {str(k): int(sum(1 for l in lines if l == k)) for k in sorted(set(lines))},
        'line_height_px_median': int(np.median(lh)) if lh else None,
        'polarity': max(set(pol), key=pol.count),
        'fill_colors': fill_colors,
        'blocks_with_highlight_pct': round(100 * len(hl_blocks) / max(1, len(zb)), 1),
        'highlight_words_per_block': {str(k): int(hl_counts.count(k)) for k in sorted(set(hl_counts))},
        'max_highlight_words_in_a_block': max(hl_counts) if hl_counts else 0,
        'blocks_with_a_second_hue_pct': round(100 * sum(1 for b in zb if b.get('other_hue_blobs')) / max(1, len(zb)), 1),
        'second_hue_times': sorted({round(s['t'], 2) for s in samples for b in s['blocks'] if b.get('other_hue_blobs')})[:30],
        'multi_highlight_times': sorted({round(s['t'], 2) for s in samples for b in s['blocks'] if b['hl_words'] >= 2})[:30],
        'highlight_colors': hues,
        'page_flips': len(flips),
        'flips_per_min': round(60 * len(flips) / max(1e-6, duration), 1),
        'mean_page_sec': round(vis / max(1, pages), 2),
        'flip_times': flips[:200],
        'not_readable': 'No OCR: exact words, upper vs lower case, and verbatim vs paraphrase cannot be read.',
    }
    if words:
        on = [w for w in words if present[min(len(present) - 1, int(((w['start'] + w['end']) / 2) / SAMPLE_SEC))]]
        rep['words_per_page'] = round(len(on) / max(1, pages), 2)
        rep['sidecar_note'] = 'The sidecar transcript was used for timing (words per page) only, not to read caption text.'
    return rep, main_zone


# ---------------------------------------------------------------------------------------------- faces
def face_report(path, info, samples, duration):
    H, W = info['height'], info['width']
    times = [round(t, 3) for t in np.arange(0, max(0.0, duration - 0.05), FACE_SEC)]
    res, _ = face_safe.detect_at(path, times)
    tby = {round(s['t'], 2): s for s in samples}
    out, on_face, cap_crop, chin_crop, fh = [], [], [], [], []
    for r in res:
        if not r['face'] or r['held']:
            out.append({'t': r['t'], 'face': None})
            continue
        x, y, w, h = r['face']
        head = face_safe.head_from_face(r['face'])
        core = [x, y, w, h * (1 + face_safe.CHIN_DOWN)]   # face + chin/beard, no cap margin
        fh.append(h / H)
        s = tby.get(round(r['t'], 2))
        hit_core, hit_head = [], []
        for b in (s['blocks'] if s else []):
            bx, by, bw, bh = b['box']
            if face_safe.hits(core, b['box'], 0):
                hit_core.append(b['box'])
            elif face_safe.hits(head, b['box'], 0):
                hit_head.append(b['box'])
        g = s['g'] if s else None
        if hit_core:
            on_face.append({'t': r['t'], 'level': 'text on face/chin', 'text_box': hit_core[0],
                            'face_box': [round(v) for v in core]})
        elif hit_head:
            on_face.append({'t': r['t'], 'level': 'possible (cap margin / head edge)', 'text_box': hit_head[0],
                            'head_box': [round(v) for v in head]})
        if head[1] < 0:
            cap_crop.append({'t': r['t'], 'level': 'clear' if y <= 0.01 * H else 'possible', 'cap_top_px': round(head[1])})
        if head[1] + head[3] > H:
            chin_crop.append({'t': r['t'], 'level': 'clear' if y + h >= 0.99 * H else 'possible',
                              'chin_bottom_px': round(head[1] + head[3])})
        out.append({'t': r['t'], 'face': [round(v) for v in r['face']], 'head': [round(v) for v in head]})
    found = sum(1 for o in out if o['face'])
    rate = found / max(1, len(out))
    med = float(np.median(fh)) if fh else None
    return {'samples': len(out), 'detect_rate': round(rate, 2),
            'face_height_frac_median': round(med, 3) if med else None,
            'crop': ('tight' if med and med >= TIGHT_FACE_FRAC else 'wide' if med else 'unknown'),
            'face_center_x_median': round(float(np.median([(o['face'][0] + o['face'][2] / 2) / W for o in out if o['face']])), 3) if found else None,
            'face_center_y_median': round(float(np.median([(o['face'][1] + o['face'][3] / 2) / H for o in out if o['face']])), 3) if found else None,
            'text_overlaps': on_face, 'cap_crop': cap_crop, 'chin_crop': chin_crop,
            'note': 'Haar frontal/profile via helpers/face_safe.py; misses on profile turns / hands; held samples ignored. '
                    'Cap margin is conservative (~150 px high on 1080x1920), so cap crops are "possible" unless the face box itself touches the edge.',
            'per_sample': out}


# ---------------------------------------------------------------------------------------------- audio
def audio_report(path, duration, events, words, info):
    if not info['has_audio']:
        return {'has_audio': False}
    rep = {'has_audio': True}
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-filter_complex', 'ebur128=peak=true', '-f', 'null', '-'])
    tail = r.stderr[r.stderr.rfind('Summary:'):] if 'Summary:' in r.stderr else r.stderr
    m = re.search(r'I:\s+(-?[\d.]+) LUFS', tail)
    p = re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', tail)
    lra = re.search(r'LRA:\s+(-?[\d.]+) LU', tail)
    rep['integrated_lufs'] = float(m.group(1)) if m else None
    rep['true_peak_dbtp'] = float(p.group(1)) if p and p.group(1) != '-inf' else None
    rep['lra_lu'] = float(lra.group(1)) if lra else None
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', f'silencedetect=noise={SILENCE_DB}dB:d={SILENCE_SEC}',
             '-f', 'null', '-'])
    ss = [float(v) for v in re.findall(r'silence_start: (-?[\d.]+)', r.stderr)]
    se = [float(v) for v in re.findall(r'silence_end: (-?[\d.]+)', r.stderr)]
    sil = []
    for i, s in enumerate(ss):
        e = se[i] if i < len(se) else duration
        sil.append((max(0.0, s), min(duration, e)))
    sil_tot = sum(e - s for s, e in sil)
    rep['silencedetect'] = {'threshold_db': SILENCE_DB, 'min_sec': SILENCE_SEC, 'pauses': len(sil),
                            'pause_sec': round(sil_tot, 2), 'talk_ratio': round(1 - sil_tot / max(1e-6, duration), 3)}
    # raw samples
    sr = 32000
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    if x.size < sr // 2:
        return rep
    hop = int(0.01 * sr)
    win = int(0.05 * sr)
    nfr = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(nfr)[:, None]
    fr = x[idx]
    rms_db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    tt = (np.arange(nfr) * hop + win / 2) / sr
    # pause level: word gaps from the sidecar, else silencedetect gaps + the 10th percentile floor
    gaps = []
    if words:
        for a, b in zip(words[:-1], words[1:]):
            if b['start'] - a['end'] >= 0.30:
                gaps.append((a['end'] + 0.08, b['start'] - 0.08))
        src = 'sidecar word gaps >= 0.30 s'
    else:
        gaps = [(s + 0.05, e - 0.05) for s, e in sil]
        src = 'silencedetect pauses'
    lv = [rms_db[(tt >= s) & (tt <= e)] for s, e in gaps if e > s]
    lv = np.concatenate(lv) if lv else np.array([])
    pause_db = float(np.percentile(lv, 25)) if lv.size else None   # p25: transcript gaps leak word tails
    floor_db = float(np.percentile(rms_db, 10))
    speech_db = float(np.percentile(rms_db, 80))
    level = floor_db if pause_db is None else min(floor_db, pause_db) if words else floor_db
    bed = 'likely' if level > BED_LIKELY_DB else 'possible' if level > BED_POSSIBLE_DB else 'unlikely'
    rep['music_bed'] = {'pause_level_db': round(level, 1), 'floor_db_p10': round(floor_db, 1),
                        'gap_level_db_p25': round(pause_db, 1) if pause_db is not None else None,
                        'gap_source': src, 'gap_windows': len(gaps),
                        'speech_db_p80': round(speech_db, 1), 'verdict': bed,
                        'rule': f'quietest-10% level (and transcript-gap p25) > {BED_LIKELY_DB} dBFS = likely, > {BED_POSSIBLE_DB} = possible'}
    # SFX hits: 3-12 kHz band bumps right at visual edits, vs the same test at random non-edit times
    nfft = 1024
    nfr2 = 1 + (len(x) - nfft) // hop
    win_f = np.hanning(nfft).astype(np.float32)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    band = (freqs >= SFX_BAND[0]) & (freqs <= SFX_BAND[1])
    bdb = np.empty(nfr2, np.float32)
    for c in range(0, nfr2, 2000):
        cc = np.arange(c, min(nfr2, c + 2000))
        seg = x[np.arange(nfft)[None, :] + hop * cc[:, None]] * win_f
        sp = np.abs(np.fft.rfft(seg, axis=1))[:, band]
        bdb[cc] = 10 * np.log10((sp ** 2).sum(axis=1) + 1e-12)
    bt = (np.arange(nfr2) * hop + nfft / 2) / sr

    def bump(t):
        w = (bt >= t + SFX_WIN[0]) & (bt <= t + SFX_WIN[1])
        ctx = ((bt >= t - 2.0) & (bt <= t + 2.0)) & ~w
        if not w.any() or not ctx.any():
            return None
        return float(bdb[w].max() - np.median(bdb[ctx]))

    ev_t = [0.0] + [e['t'] for e in events if e['kind'] != 'overlay change']
    ev_t = sorted(set(round(t, 2) for t in ev_t))
    rng = np.random.default_rng(7)
    ctrl = [t for t in rng.uniform(0.5, max(1.0, duration - 0.5), 400) if all(abs(t - e) > 0.6 for e in ev_t)]
    cb = [bump(t) for t in ctrl]
    cb = [c for c in cb if c is not None]
    thr = max(SFX_DB, float(np.percentile(cb, SFX_CTRL_PCT))) if cb else SFX_DB
    hits = []
    for t in ev_t:
        d = bump(t)
        if d is not None and d >= thr:
            hits.append({'t': t, 'over_median_db': round(d, 1)})
    base_rate = sum(1 for c in cb if c >= thr) / max(1, len(cb))
    gaps_h = [round(b['t'] - a['t'], 2) for a, b in zip(hits[:-1], hits[1:])]
    rep['sfx'] = {'edits_checked': len(ev_t), 'hits_at_edits': len(hits), 'hits': hits, 'threshold_db': round(thr, 1),
                  'baseline_rate_random_times': round(base_rate, 2),
                  'expected_false_hits': round(base_rate * len(ev_t), 1),
                  'min_gap_between_hits_s': min(gaps_h) if gaps_h else None,
                  'confidence': 'low' if len(hits) - base_rate * len(ev_t) < 2 else 'medium',
                  'note': 'A hit = 3-12 kHz energy over the local median within %.2f..+%.2f s of an edit, above the %dth '
                          'percentile of the same score at random non-edit times (speech sibilants look like whooshes). '
                          'Compare with expected_false_hits. Whoosh vs pop not separated.'
                          % (SFX_WIN[0], SFX_WIN[1], SFX_CTRL_PCT)}
    return rep


# ---------------------------------------------------------------------------------------------- outputs
def contact_sheet(path, info, events, pushes, out_path, duration):
    fps = info['fps']
    items = [{'n': 0, 'label': 'start'}]
    for e in events:
        if e['kind'] == 'overlay change':
            continue
        lab = e['kind']
        if e['kind'].startswith(('punch', 'fast')):
            lab += f" x{e['ratio']:.2f} ({e['frames']}f)"
        items.append({'n': e.get('peak_n', e['n']), 'label': lab, 't': e['t']})
    for p in pushes:
        items.append({'n': int(p['end'] * fps) - 1, 'label': f"{'crawl' if p['easing'] == 'linear' else 'eased push'} end x{p['to'] / p['from']:.2f}",
                      't': p['end']})
    last = int(duration * fps) - 1
    items.append({'n': max(0, last), 'label': 'end'})
    items.sort(key=lambda i: i['n'])
    if len(items) > CONTACT_CELLS:
        mid = items[1:-1]
        keep = np.linspace(0, len(mid) - 1, CONTACT_CELLS - 2).round().astype(int)
        items = [items[0]] + [mid[k] for k in sorted(set(keep))] + [items[-1]]
    cap = cv2.VideoCapture(path)
    cw = 216
    ch = int(round(cw * info['height'] / info['width']))
    lab_h = 46
    cols = 6
    rows = math.ceil(len(items) / cols)
    sheet = Image.new('RGB', (cols * cw, rows * (ch + lab_h)), (24, 24, 24))
    try:
        font = ImageFont.truetype('arialbd.ttf', 15)
        font2 = ImageFont.truetype('arial.ttf', 13)
    except OSError:
        font = font2 = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for k, it in enumerate(items):
        cap.set(cv2.CAP_PROP_POS_FRAMES, it['n'])
        ok, fr = cap.read()
        x0, y0 = (k % cols) * cw, (k // cols) * (ch + lab_h)
        if ok:
            im = Image.fromarray(cv2.cvtColor(cv2.resize(fr, (cw, ch), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
            sheet.paste(im, (x0, y0))
        d.text((x0 + 5, y0 + ch + 3), f"{it['n'] / fps:.2f}s  f{it['n']}", fill=(255, 255, 255), font=font)
        d.text((x0 + 5, y0 + ch + 23), it['label'][:30], fill=(255, 140, 90), font=font2)
    cap.release()
    sheet.save(out_path, quality=88)
    return len(items)


def pacing_report(events, duration, words, audio, fps):
    hard = [e for e in events if e['kind'] == 'hard cut']
    jump = [e for e in events if e['kind'] == 'jump cut']
    punch = [e for e in events if e['kind'].startswith('punch') or e['kind'].startswith('fast')]
    layout = [e for e in events if e['kind'] == 'layout cut']
    vis = sorted([e['t'] for e in events if e['kind'] != 'overlay change'])
    pts = [0.0] + vis + [duration]
    holds = [b - a for a, b in zip(pts[:-1], pts[1:]) if b - a > 1e-6]
    shots = [0.0] + [e['t'] for e in hard + layout] + [duration]
    shot_len = [b - a for a, b in zip(sorted(shots)[:-1], sorted(shots)[1:]) if b - a > 1e-6]
    pm = 60.0 / max(1e-6, duration)
    rep = {'duration_s': round(duration, 2),
           'per_min': {'hard_cuts': round(len(hard) * pm, 1), 'jump_cuts': round(len(jump) * pm, 1),
                       'punches': round(len(punch) * pm, 1), 'layout_cuts': round(len(layout) * pm, 1),
                       'all_visual_edits': round(len(vis) * pm, 1)},
           'counts': {'hard_cuts': len(hard), 'jump_cuts': len(jump), 'punches': len(punch), 'layout_cuts': len(layout)},
           'hold_s': {'mean': round(float(np.mean(holds)), 2), 'median': round(float(np.median(holds)), 2),
                      'min': round(min(holds), 2), 'max': round(max(holds), 2)} if holds else None,
           'shot_s': {'mean': round(float(np.mean(shot_len)), 2), 'median': round(float(np.median(shot_len)), 2),
                      'min': round(min(shot_len), 2), 'max': round(max(shot_len), 2), 'count': len(shot_len)}}
    first_hard = hard[0]['t'] if hard else None
    first_sent = None
    if words:
        for w in words:
            if re.search(r'[.?!]["\')]*$', w['text']):
                first_sent = round(w['end'], 2)
                break
    rep['hook'] = {'first_hard_cut_s': first_hard, 'first_sentence_end_s': first_sent,
                   'hook_length_s': first_sent if first_sent is not None else (first_hard if first_hard is not None else None),
                   'basis': 'end of the first sentence (sidecar)' if first_sent is not None else 'first hard cut'}
    if words:
        span = words[-1]['end'] - words[0]['start']
        rep['words'] = len(words)
        rep['wpm_over_reel'] = round(len(words) * pm, 1)
        rep['wpm_while_talking'] = round(60 * len(words) / max(1e-6, span), 1)
        g = [b['start'] - a['end'] for a, b in zip(words[:-1], words[1:])]
        pause = sum(v for v in g if v >= SILENCE_SEC)
        rep['talk_ratio_from_words'] = round(1 - (pause + max(0, words[0]['start']) + max(0, duration - words[-1]['end'])) / duration, 3)
        rep['word_gaps'] = {'pauses_ge_0.25s': sum(1 for v in g if v >= SILENCE_SEC),
                            'longest_gap_s': round(max(g), 2) if g else None,
                            'median_gap_s': round(float(np.median(g)), 3) if g else None}
    if audio and audio.get('silencedetect'):
        rep['talk_ratio_audio'] = audio['silencedetect']['talk_ratio']
    return rep


def color_report(samples, info):
    pix = np.concatenate([s['px'] for s in samples[::2]]) if samples else np.zeros((0, 3))
    dom = kmeans_colors(pix[::3], 6)
    br = [s['g']['bright'] for s in samples]
    sa = [s['g']['sat'] for s in samples]
    cards = [(round(s['t'], 2), s['g']['card']) for s in samples if s['g']['card']]
    # card spans
    spans = []
    for t, c in cards:
        if spans and t - spans[-1]['end'] <= SAMPLE_SEC * 1.5 and spans[-1]['color'] == c['color']:
            spans[-1]['end'] = t
        else:
            spans.append({'start': t, 'end': t, 'color': c['color'], 'hex': c['hex'], 'share': c['share']})
    # bands (layout) spans
    def bsig(s):
        return tuple((b['color'], round(b['y0'], 1), round(b['y1'], 1)) for b in s['g']['bands'] if (b['y1'] - b['y0']) >= 0.05)
    lay = []
    for s in samples:
        if s['g']['card']:
            continue
        sg = bsig(s)
        if lay and lay[-1]['sig'] == sg:
            lay[-1]['end'] = round(s['t'], 2)
        else:
            lay.append({'start': round(s['t'], 2), 'end': round(s['t'], 2), 'sig': sg,
                        'bands': [b for b in s['g']['bands'] if (b['y1'] - b['y0']) >= 0.05]})
    lay = [l for l in lay if l['sig'] and l['end'] - l['start'] >= 0.5]
    for l in lay:
        ys = [(b['y0'], b['y1']) for b in l['bands']]
        mid = [y for y in ys if y[0] > 0.08 and y[1] < 0.92]
        top = any(y[0] <= 0.01 for y in ys)
        bot = any(y[1] >= 0.99 for y in ys)
        l['kind'] = ('split / stacked bands (band in the middle)' if mid else
                     'stacked layout (flat bands top AND bottom: video/graphic bands)' if top and bot else
                     'top band (headroom / title band)' if top else 'bottom band' if bot else 'bands')
        del l['sig']
    # progress bar
    bar_obs = [(s['t'], b) for s in samples for b in s['g']['bars']]
    prog = None
    if bar_obs:
        ys = {}
        for t, b in bar_obs:
            ys.setdefault(round(b['y'], 2), []).append((t, b))
        y, obs = max(ys.items(), key=lambda kv: len(kv[1]))
        if len(obs) >= 0.4 * len(samples) and len(obs) >= 6:
            tt = np.array([o[0] for o in obs])
            ll = np.array([o[1]['len'] for o in obs])
            corr = float(np.corrcoef(tt, ll)[0, 1]) if ll.std() > 0 else 0.0
            prog = {'y_pct': round(100 * y, 1), 'height_px': int(np.median([o[1]['h_px'] for o in obs]) * info['width'] / ANALYSIS_W),
                    'color': obs[len(obs) // 2][1]['color'], 'hex': obs[len(obs) // 2][1]['hex'],
                    'present_pct': round(100 * len(obs) / len(samples), 1), 'length_vs_time_corr': round(corr, 2),
                    'growing': corr > 0.8}
    return {'brightness_mean': round(float(np.mean(br)), 3) if br else None,
            'saturation_mean': round(float(np.mean(sa)), 3) if sa else None,
            'dominant_colors': dom, 'full_frame_cards': spans, 'layouts': lay, 'progress_bar': prog}


# ---------------------------------------------------------------------------------------------- style guide
def fmt_t(ts, k=8):
    ts = list(ts)
    s = ', '.join(f'{t:.2f}s' for t in ts[:k])
    return s + (f' (+{len(ts) - k} more)' if len(ts) > k else '')


def build_guide(name, src, info, bd):
    ev, pushes = bd['events'], camera_pushes(bd['pushes'])
    leans = [p for p in bd['pushes'] if p not in pushes]
    cap, face, col, aud, pac = bd['captions'], bd['faces'], bd['color'], bd['audio'], bd['pacing']
    punches = [e for e in ev if e['kind'] in ('punch in', 'punch out')]
    pin = [e for e in punches if e['kind'] == 'punch in']
    fastp = [e for e in ev if e['kind'].startswith('fast')]
    hard = [e for e in ev if e['kind'] == 'hard cut']
    jump = [e for e in ev if e['kind'] == 'jump cut']
    layout = [e for e in ev if e['kind'] == 'layout cut']
    L = []
    A = L.append
    A(f'# Style breakdown: {name}')
    A('')
    A(f'Source: `{src}` ({info["width"]}x{info["height"]}, {info["fps"]} fps, {info["duration"]:.2f} s). '
      f'Generated by `helpers/style_breakdown.py` on {time.strftime("%Y-%m-%d %H:%M")}. All numbers are heuristic '
      'measurements; check `contact_sheet.jpg` before trusting a label. Nothing here has been applied to any edit.')
    if bd.get('captions_sidecar'):
        A(f'Transcript sidecar: `{bd["captions_sidecar"]}` (offset {bd["captions_offset"]:+.2f} s), used for words / pacing '
          'and caption timing only, never to read the burned-in text.')
    A('')
    # Camera
    A('## Camera')
    A(f'- Base crop: **{face["crop"]}** (median Haar face height {face["face_height_frac_median"]} of the frame; tight >= {TIGHT_FACE_FRAC}). '
      f'Face centre ~({face["face_center_x_median"]}, {face["face_center_y_median"]}) of the frame.')
    if pin:
        fr = sorted({e['frames'] for e in pin})
        A(f'- **{len(pin)} punch-ins**, ratio {min(e["ratio"] for e in pin):.2f}-{max(e["ratio"] for e in pin):.2f}x '
          f'(estimated peak vs the base frame: {", ".join(f"{e.get("peak_scale_est", e["ratio"]):.2f}" for e in pin)}), over {fr} frame(s) '
          f'({"instant, 1-frame" if fr == [1] else "short eased ramp" if min(fr) > 1 else "mixed"}). Times: {fmt_t(e["t"] for e in pin)}.')
    else:
        A('- No punch-ins detected.')
    po = [e for e in punches if e['kind'] == 'punch out']
    if po:
        A(f'- {len(po)} punch-outs (snap back), ratio {", ".join(f"{e["ratio"]:.2f}" for e in po)}, over '
          f'{sorted({e["frames"] for e in po})} frame(s); each undoes: {", ".join(str(e.get("undoes")) for e in po)} '
          '(None = a punch-out with no punch/push before it = wider than the base).')
    for e in fastp:
        A(f'- Fast push {e["t"]:.2f}s: x{e["ratio"]:.2f} over {e["frames"]} frames (Hero-Push-like if ~12 frames to ~1.30).')
    if pushes:
        for p in pushes:
            A(f'- Slow camera zoom {p["direction"]} {p["start"]:.2f}-{p["end"]:.2f}s (R^2 {p["r2"]}): x{p["to"] / p["from"]:.3f} over {p["duration"]} s '
              f'({p["rate_per_s"]:+.4f} scale/s), **{p["easing"]}** (fit {p["fit_confidence"]}; RMSE linear {p["rmse_linear"]} vs eased {p["rmse_eased"]}).')
    else:
        A('- No slow camera zooms (>= 3 % over >= 1 s, smooth ramp) detected.')
    for p in leans:
        A(f'- Not counted: {p["start"]:.2f}-{p["end"]:.2f}s scale drift x{p["to"] / p["from"]:.3f} (R^2 {p["r2"]}): {p["source"]}.')
    for e in hard + layout:
        if e.get('detail'):
            A(f'- {e["kind"].capitalize()} at {e["t"]:.2f}s: {e["detail"]}.')
    A(f'- Hard cuts: {len(hard)} ({fmt_t(e["t"] for e in hard)}). Jump cuts (same shot, splice): {len(jump)} '
      f'({fmt_t(e["t"] for e in jump)}). Layout cuts: {len(layout)} ({fmt_t(e["t"] for e in layout)}).')
    A('')
    # Captions
    A('## Captions')
    if cap.get('detected'):
        A(f'- Burned-in text on {cap["samples_with_text_pct"]} % of samples; zones {cap["zones_pct"]}. Main zone **{cap["main_zone"]}**, '
          f'y {cap["main_zone_y_pct"][0]}-{cap["main_zone_y_pct"][1]} % of the height (block bottom ~{cap["block_bottom_px_median"]} px).')
        A(f'- Lines per block (samples): {cap["lines_per_block"]}; line height ~{cap["line_height_px_median"]} px (font-size proxy, '
          f'includes outline). Style: {cap["polarity"]} ({"bright fill with a dark outline" if cap["polarity"] != "dark-on-light" else "dark text on a light card"}).')
        A(f'- Fill colors: ' + ', '.join(f'{c["name"]} {c["hex"]} ({round(100 * c["share"])} %)' for c in cap['fill_colors']) + '.')
        A(f'- Highlighted (second-color) words: {cap["blocks_with_highlight_pct"]} % of blocks; per block {cap["highlight_words_per_block"]}; '
          f'highlight colors {cap["highlight_colors"] or "none"}.')
        A(f'- Page flips: {cap["page_flips"]} ({cap["flips_per_min"]}/min, ~{cap["mean_page_sec"]} s per page'
          + (f', ~{cap["words_per_page"]} words per page' if 'words_per_page' in cap else '') + ').')
        A(f'- {cap["not_readable"]}')
    else:
        A('- No burned-in caption text detected (heuristic). No OCR: words / case / paraphrase not readable.')
    A('')
    # Pacing
    A('## Pacing')
    A(f'- Duration {pac["duration_s"]} s. Per minute: hard {pac["per_min"]["hard_cuts"]}, jump {pac["per_min"]["jump_cuts"]}, '
      f'punch {pac["per_min"]["punches"]}, layout {pac["per_min"]["layout_cuts"]} (all visual edits {pac["per_min"]["all_visual_edits"]}).')
    if pac['hold_s']:
        h = pac['hold_s']
        A(f'- Hold between visual edits: mean {h["mean"]} s, median {h["median"]} s, min {h["min"]} s, max {h["max"]} s. '
          f'Shots (between hard/layout cuts): {pac["shot_s"]["count"]}, median {pac["shot_s"]["median"]} s.')
    hk = pac['hook']
    A(f'- Hook length: {hk["hook_length_s"]} s ({hk["basis"]}; first hard cut {hk["first_hard_cut_s"]}).')
    if 'words' in pac:
        A(f'- {pac["words"]} words, {pac["wpm_while_talking"]} wpm while talking ({pac["wpm_over_reel"]} over the whole reel); '
          f'talk ratio {pac["talk_ratio_from_words"]} (word gaps), {pac.get("talk_ratio_audio")} (silencedetect {SILENCE_DB} dB / {SILENCE_SEC} s); '
          f'longest gap {pac["word_gaps"]["longest_gap_s"]} s.')
    elif 'talk_ratio_audio' in pac:
        A(f'- Talk ratio {pac["talk_ratio_audio"]} (silencedetect {SILENCE_DB} dB / {SILENCE_SEC} s).')
    A('')
    # Color & graphics
    A('## Color & graphics')
    A(f'- Mean brightness {col["brightness_mean"]}, mean saturation {col["saturation_mean"]}. Dominant colors: '
      + ', '.join(f'{c["name"]} {c["hex"]} ({round(100 * c["share"])} %)' for c in col['dominant_colors'][:5]) + '.')
    if col['full_frame_cards']:
        for c in col['full_frame_cards']:
            A(f'- Full-frame solid card {c["start"]:.2f}-{c["end"]:.2f}s: {c["color"]} {c["hex"]} ({round(100 * c["share"])} % of the frame).')
    else:
        A('- No full-frame solid cards.')
    for l in col['layouts']:
        A(f'- Layout {l["start"]:.2f}-{l["end"]:.2f}s: {l["kind"]}: ' +
          '; '.join(f'{b["color"]} band y {round(100 * b["y0"])}-{round(100 * b["y1"])} %' for b in l['bands']) + '.')
    if col['progress_bar']:
        p = col['progress_bar']
        A(f'- Progress-bar-like thin bar at y {p["y_pct"]} %, ~{p["height_px"]} px, {p["color"]} {p["hex"]}, on {p["present_pct"]} % of samples, '
          f'{"grows with time" if p["growing"] else "does not clearly grow"} (corr {p["length_vs_time_corr"]}).')
    else:
        A('- No progress bar detected.')
    A('')
    # Audio
    A('## Audio')
    if aud.get('has_audio'):
        mb = aud.get('music_bed', {})
        A(f'- Loudness {aud["integrated_lufs"]} LUFS integrated, true peak {aud["true_peak_dbtp"]} dBTP, LRA {aud["lra_lu"]} LU.')
        A(f'- Music bed: **{mb.get("verdict")}** (level when nobody talks ~{mb.get("pause_level_db")} dBFS: quietest-10 % {mb.get("floor_db_p10")}, transcript gaps p25 '
          f'{mb.get("gap_level_db_p25")}; speech p80 {mb.get("speech_db_p80")} dBFS).')
        sf = aud.get('sfx', {})
        A(f'- SFX hits at visual edits: {sf.get("hits_at_edits")} of {sf.get("edits_checked")} edits '
          f'(chance level ~{sf.get("expected_false_hits")} from speech alone; confidence {sf.get("confidence")}); hit times {fmt_t(h["t"] for h in sf.get("hits", []))}.')
    else:
        A('- No audio stream.')
    A('')
    # Vocabulary
    A('## In our vocabulary')
    A('| What the reel does | Our library name |')
    A('|---|---|')
    for e in pin:
        if e['frames'] == 1:
            nm = 'Instant Punch' if e.get('peak_scale_est', e['ratio']) <= 1.24 else 'Instant Punch (past the 1.23 stacked palette)'
        elif e['frames'] <= 6:
            nm = f'PunchIn with a {e["frames"]}-frame ease (old default `inFrames: 4`; today Instant Punch = 1 frame)'
        else:
            nm = 'Hero Push (if once, on the payoff line)'
        A(f'| {e["t"]:.2f}s punch in x{e["ratio"]:.2f} over {e["frames"]} frame(s) -> ~{e.get("peak_scale_est", e["ratio"]):.2f} | {nm} |')
    if po:
        A(f'| {len(po)} snap-outs (ratio ~{np.median([e["ratio"] for e in po]):.2f}) over {sorted({e["frames"] for e in po})} frame(s) | '
          'snap-out of a PunchIn / PushIn (`outFrames`; Instant Punch = 1 frame) |')
    for e in fastp:
        A(f'| {e["t"]:.2f}s fast push x{e["ratio"]:.2f} over {e["frames"]} frames | Hero Push |')
    for p in pushes:
        A(f'| {p["start"]:.2f}-{p["end"]:.2f}s slow {p["easing"]} zoom {p["direction"]} x{p["to"] / p["from"]:.3f} | {p["library"]} |')
    if jump:
        A(f'| {len(jump)} jump cuts (same shot spliced) | Descript rough cut (pacing: tight, keep the 0.4-0.6 s punchline pause) |')
    if hard:
        A(f'| {len(hard)} hard cuts | hard cut (our rules: B-roll in/out only) |')
    if layout:
        A(f'| {len(layout)} layout cuts | Split Frame / Solo Frame (talking-head-motion) |')
    if cap.get('detected'):
        A(f'| {cap["main_zone"]} burned-in captions, {cap["lines_per_block"]} lines | '
          f'{"Lower-Third Captions" if cap["main_zone"] in ("lower third", "bottom") else "captions outside our lower third (plain language)"} |')
        if cap['blocks_with_highlight_pct'] > 0:
            A(f'| a second-color word in {cap["blocks_with_highlight_pct"]} % of blocks ({cap["highlight_colors"]}) | money word (one accent word per block) |')
    for c in col['full_frame_cards']:
        A(f'| full-frame {c["color"]} card {c["start"]:.2f}-{c["end"]:.2f}s | '
          f'{"Hook Card / Hook Caption" if c["start"] < 0.5 else "Takeover Frame / Statement Card"} |')
    if bd['hook_text_frame0']:
        h0 = bd['hook_text_frame0']
        A(f'| text on frame 0 ({h0["polarity"]}, {h0["zone"]}) | {"Hook Card (white card)" if h0["polarity"] == "dark-on-light" else "Hook Caption"} |')
    for l in col['layouts']:
        if l['kind'].startswith('top band'):
            A(f'| {l["kind"]} {l["start"]:.2f}-{l["end"]:.2f}s | Solo Frame (ink headroom band) |')
    if col['progress_bar']:
        A('| thin bar near the top | Progress Bar |')
    if aud.get('sfx', {}).get('hits_at_edits'):
        A('| sound bumps on edits | Whoosh / Pop SFX |')
    mb = aud.get('music_bed', {})
    if mb.get('verdict') in ('likely', 'possible'):
        A('| music bed under the voice | not our default (`"music": null`; you add the IG sound) |')
    A('')
    # Borrow
    A('## What we could borrow')
    ideas = []
    if pin:
        ideas.append(f'Punch rhythm: {len(pin)} punch-ins in {info["duration"]:.0f} s (one every ~{info["duration"] / max(1, len(pin)):.1f} s), '
                     'locked to the first word of a clause -> **Instant Punch** (1-frame, 1.16 from a wide base; 1.10-1.12 on tight crops).')
    for p in pushes:
        ideas.append(f'{p["easing"].title()} slow zoom under the {p["start"]:.1f}-{p["end"]:.1f}s stretch at {p["rate_per_s"]:+.3f}/s -> **{p["library"]}**.')
    if jump:
        ideas.append(f'Tight splices ({pac["per_min"]["jump_cuts"]} jump cuts/min) -> the Descript rough-cut step (no new effect).')
    if cap.get('detected'):
        ideas.append(f'Caption page length ~{cap["mean_page_sec"]} s' + (f' / ~{cap["words_per_page"]} words' if 'words_per_page' in cap else '')
                     + ' -> **Lower-Third Captions** (`maxWords`, `maxLineChars`).')
    if col['full_frame_cards']:
        ideas.append('Full-frame card beat -> **Takeover Frame** (talking-head-motion, one per reel) or **Statement Card** (`position: "full"`).')
    if col['progress_bar']:
        ideas.append('Persistent progress bar -> **Progress Bar** (talking-head-motion only).')
    if any(l['kind'].startswith('split') for l in col['layouts']):
        ideas.append('Stacked/split layout -> **Split Frame**.')
    if [e for e in po if not e.get('undoes')]:
        ideas.append('Punch-outs that go WIDER than the base frame -> NEW — would need approval to add to the library.')
    if [p for p in pushes if p['direction'] == 'out']:
        ideas.append('Slow pull-out -> NEW — would need approval to add to the library (Steady Crawl is in only).')
    if not ideas:
        ideas.append('Nothing distinctive measured beyond our defaults.')
    for i in ideas:
        A(f'- {i}')
    A('')
    # Conflicts
    A('## CONFLICTS')
    A('Rule book: `CLAUDE.md` + `style/effects-library.md`. Each item: CONFLICT / OK / UNKNOWN, when, evidence, rule.')
    A('')
    for c in bd['conflicts']:
        A(f'- **{c["status"]}** — {c["what"]}. When: {c["when"]}. Evidence: {c["evidence"]}. Rule: {c["rule"]}.')
    A('')
    A('## Limits')
    A('- No OCR: caption words, upper/lower case and verbatim-vs-paraphrase cannot be read; only regions, lines, colors and timing.')
    A('- Haar face detection misses profile turns, hands over the face and tiny faces in split bands; those samples are skipped.')
    A('- Cut classification is heuristic (ORB + RANSAC similarity): a cut between two similar angles can read as a punch, '
      'fast gestures can read as jump cuts, multi-frame card animations as one event. Check the contact sheet.')
    A('- SFX detection cannot tell a whoosh from a pop or from a loud "s"; compare hits with the chance level.')
    A('')
    A('Waiting for you to pick what to apply.')
    return '\n'.join(L) + '\n'


def build_conflicts(bd, info):
    C = []
    face, cap, col, aud, ev = bd['faces'], bd['captions'], bd['color'], bd['audio'], bd['events']

    def add(status, what, when, evidence, rule):
        C.append({'status': status, 'what': what, 'when': when, 'evidence': evidence, 'rule': rule})

    rf = 'CLAUDE.md "Text never touches his face" / effects-library brand rules'
    hard_hits = [o for o in face['text_overlaps'] if o['level'].startswith('text on face')]
    soft_hits = [o for o in face['text_overlaps'] if not o['level'].startswith('text on face')]
    if hard_hits:
        add('CONFLICT', 'Text on the face / chin', fmt_t(o['t'] for o in hard_hits),
            f'{len(hard_hits)} samples where a text box overlaps the Haar face box extended to the chin (e.g. text {hard_hits[0]["text_box"]} vs face {hard_hits[0]["face_box"]})', rf)
    elif face['detect_rate'] < 0.4:
        add('UNKNOWN', 'Text on the face', 'whole reel', f'face found on only {round(100 * face["detect_rate"])} % of samples', rf)
    else:
        add('OK', 'Text on the face', 'whole reel', f'no text box hit the face/chin box on {face["samples"]} samples', rf)
    if soft_hits:
        add('UNKNOWN', 'Text near the head (inside the conservative cap / side margin only)', fmt_t(o['t'] for o in soft_hits),
            f'{len(soft_hits)} samples; check by eye', rf)
    rc = 'CLAUDE.md "Zoom & punch style": whole cap and chin in frame at every scale'
    clear = [o for o in face['cap_crop'] + face['chin_crop'] if o['level'] == 'clear']
    poss_cap = [o for o in face['cap_crop'] if o['level'] == 'possible']
    poss_chin = [o for o in face['chin_crop'] if o['level'] == 'possible']
    if clear:
        add('CONFLICT', 'Cap or chin cropped (face box at the frame edge)', fmt_t(o['t'] for o in clear), f'{len(clear)} samples', rc)
    if poss_cap or poss_chin:
        add('UNKNOWN', 'Cap / chin possibly cropped (estimated head box past the edge; cap margin is conservative)',
            fmt_t(o['t'] for o in poss_cap + poss_chin),
            f'{len(poss_cap)} cap / {len(poss_chin)} chin samples; look at those frames', rc)
    if not clear and not poss_cap and not poss_chin:
        add('OK', 'Cap / chin in frame', 'whole reel', 'estimated head box inside the frame on every detected sample', rc)
    mb = aud.get('music_bed', {})
    rm = 'CLAUDE.md style defaults: Music `"music": null` (creator adds a trending sound in the app)'
    if not aud.get('has_audio'):
        add('UNKNOWN', 'Music bed', '-', 'no audio stream', rm)
    elif mb.get('verdict') == 'likely':
        add('CONFLICT', 'Music bed under the voice', 'speech pauses', f'pause level {mb["pause_level_db"]} dBFS (> {BED_LIKELY_DB})', rm)
    elif mb.get('verdict') == 'possible':
        add('UNKNOWN', 'Possible quiet music bed / room tone', 'speech pauses', f'pause level {mb["pause_level_db"]} dBFS', rm)
    else:
        add('OK', 'No music bed', 'speech pauses', f'pause level {mb.get("pause_level_db")} dBFS (near-silent)', rm)
    add('UNKNOWN', 'Paraphrased captions', 'whole reel', 'cannot verify without OCR', 'CLAUDE.md "On-screen words must match the audio. Never invent quotes."')
    rcol = 'brand.config.json: ONE accent color is the only caption highlight; support color never a caption highlight'
    hues = cap.get('highlight_colors') or {} if cap.get('detected') else {}
    acc = {h for h in hues if h and h not in ('white', 'light gray')}
    if len(acc) >= 2:
        add('CONFLICT', 'Sentiment / multi-colored caption highlights', 'see multi-color blocks', f'highlight colors {hues}', rcol)
    elif cap.get('detected'):
        add('OK', 'Sentiment-colored captions (one highlight hue at most)', 'whole reel', f'highlight colors {hues or "none"}', rcol)
    bad = sorted({h for h in acc if any(k in h for k in ('red', 'yellow', 'green', 'blue', 'cyan'))})
    fills = [c for c in cap.get('fill_colors', []) if c['share'] >= 0.05 and any(k in c['name'] for k in ('red', 'yellow', 'green'))] if cap.get('detected') else []
    gfx = [c for c in col['full_frame_cards'] if any(k in c['color'] for k in ('red', 'yellow', 'green'))]
    gbar = col['progress_bar'] if col['progress_bar'] and any(k in col['progress_bar']['color'] for k in ('red', 'yellow', 'green')) else None
    if bad or fills or gfx or gbar:
        note = ' (compare with the accent in brand.config.json; a match is fine)'
        add('UNKNOWN', 'Strong accent colors in the reference (red / yellow / green / blue)', 'captions / graphics',
            f'highlights {bad}, caption fills {[c["name"] for c in fills]}, cards {[c["color"] for c in gfx]}, bar {gbar and gbar["color"]}{note}', rcol)
    else:
        add('OK', 'No red / yellow / green accents in captions or graphics', 'whole reel',
            f'caption fills {[c["name"] for c in cap.get("fill_colors", [])]}; highlights {hues or "none"}', rcol)
    rmw = 'CLAUDE.md: ONE accent money word per on-screen caption block (both lines together)'
    if cap.get('detected'):
        if cap['max_highlight_words_in_a_block'] >= 2:
            add('CONFLICT', 'More than one accent word in a caption block', fmt_t(cap['multi_highlight_times']),
                f'up to {cap["max_highlight_words_in_a_block"]} highlighted blobs in one block (blob count can split one long word; check the frames)', rmw)
        else:
            add('OK', 'At most one accent word per block', 'whole reel', f'per-block highlight counts {cap["highlight_words_per_block"]}', rmw)
        if cap.get('second_hue_times'):
            add('UNKNOWN', 'A second saturated hue inside some caption blocks (a second highlight color, or a logo/prop behind the text)',
                fmt_t(cap['second_hue_times']), f'{cap["blocks_with_a_second_hue_pct"]} % of blocks; check by eye', rmw)
    sf = aud.get('sfx', {})
    rs = 'Whoosh / Pop SFX caps: ~4 whooshes / 3 pops per reel, whoosh gap >= 8 s; "DO NOT OVERDO IT"'
    if sf:
        n = sf['hits_at_edits']
        excess = n - sf['expected_false_hits']
        if n > RULE_CAPS['whooshes'] + RULE_CAPS['pops'] and excess > 2:
            add('CONFLICT', 'Heavy SFX', fmt_t(h['t'] for h in sf['hits']), f'{n} hits at edits (chance ~{sf["expected_false_hits"]})', rs)
        elif sf.get('min_gap_between_hits_s') is not None and sf['min_gap_between_hits_s'] < RULE_CAPS['whoosh_gap_s'] and n >= 3 and excess > 1:
            add('UNKNOWN', 'SFX hits closer than 8 s', fmt_t(h['t'] for h in sf['hits']),
                f'{n} hits, min gap {sf["min_gap_between_hits_s"]} s (whoosh vs pop not separable)', rs)
        else:
            add('OK', 'SFX light', 'whole reel', f'{n} hits at {sf["edits_checked"]} edits (chance ~{sf["expected_false_hits"]})', rs)
    rp = 'CLAUDE.md "Zoom & punch style": standard 1.16, stacked 1.22-1.23, hero 1.30 once; tight crops stay 1.10-1.12'
    pin = [e for e in ev if e['kind'] in ('punch in', 'fast push in')]
    if pin:
        tight = face['crop'] == 'tight'
        cap_ = RULE_CAPS['tight_punch_max'] if tight else RULE_CAPS['stacked_max']
        pk = lambda e: e.get('peak_scale_est', e['ratio'])
        over = [e for e in pin if pk(e) > cap_ + 0.01]
        hero = [e for e in over if pk(e) <= RULE_CAPS['hero'] + 0.02 and not tight]
        if over and not (len(over) == 1 and hero):
            add('CONFLICT', f'Punches past the {"tight-crop" if tight else "stacked"} cap ({cap_})', fmt_t(e['t'] for e in over),
                f'peak scales vs the base ~{[pk(e) for e in over]} on a {face["crop"]} crop', rp)
        else:
            add('OK', 'Punch scales within the palette', fmt_t(e['t'] for e in pin), f'peak scales vs the base ~{[pk(e) for e in pin]} ({face["crop"]} crop)', rp)
        slow = [e for e in pin if e['kind'] == 'punch in' and e['frames'] > 1]
        if slow:
            add('UNKNOWN', 'Punches are not 1-frame', fmt_t(e['t'] for e in slow),
                f'ramps of {sorted({e["frames"] for e in slow})} frames (our Instant Punch is 1 frame; older props used 4)', rp)
    else:
        add('OK', 'Punch scales', '-', 'no punches', rp)
    add('UNKNOWN', 'AI likenesses / AI-generated faces or voices', 'whole reel', 'not detectable automatically — check by eye',
        'you\'s brand: authentic, his own footage')
    # graphic (non-caption) on the face: card-like panels that don't cover the whole frame
    rg = 'effects-library: Callout Chip / cards only where face_safe says SAFE; never over the face'
    chips = [o for o in face['text_overlaps'] if o['level'].startswith('text on face')]
    if chips:
        add('CONFLICT', 'A chip, card or text box covering the face', fmt_t(o['t'] for o in chips),
            'text/graphic box over the face box (same evidence as "Text on the face")', rg)
    else:
        add('OK', 'No chip / graphic box over a detected face', 'whole reel',
            'full-frame cards hide the video entirely and are not counted as covering the face', rg)
    if bd['hook_text_frame0'] and bd['hook_text_frame0']['polarity'] == 'dark-on-light':
        add('UNKNOWN', 'Hook is a white card, not a Hook Caption', '0.00s', 'dark text on a light card at frame 0',
            'effects-library Hook Card: only if you ask; default is Hook Caption')
    return C


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('reel')
    ap.add_argument('--captions', help='sidecar word-level transcript JSON (our captions.json or {words:[...]})')
    ap.add_argument('--captions-offset', type=float, default=0.0, help='seconds to add to sidecar times (trim / hook shift)')
    ap.add_argument('--out')
    ap.add_argument('--name')
    a = ap.parse_args()
    if re.match(r'^[a-z]+://', a.reel, re.I):
        raise SystemExit('files only: no URLs (no downloads, no scraping). Ask you for the file.')
    src = os.path.abspath(a.reel)
    if not os.path.isfile(src):
        raise SystemExit(f'not a file: {a.reel}')
    name = a.name or re.sub(r'(_final|-shorts|-feed)+$', '', os.path.splitext(os.path.basename(src))[0]) or 'reel'
    out = os.path.abspath(a.out or os.path.join('out', 'style-breakdown', name))
    if os.path.normcase(out) == os.path.normcase(os.path.dirname(src)):
        raise SystemExit('refusing to write next to the input reel: pass a different --out')
    os.makedirs(out, exist_ok=True)
    log = lambda m: print(m, flush=True)
    t_start = time.time()
    info = probe(src)
    log(f'style_breakdown: {src} {info["width"]}x{info["height"]} {info["fps"]} fps {info["duration"]:.2f}s')
    words = load_words(a.captions, a.captions_offset) if a.captions else None
    log('pass 1: frames (motion, text, graphics)...')
    frames, samples = analyze_frames(src, info, log)
    fps = info['fps']
    duration = info['duration'] or len(frames) / fps
    log('faces (face_safe Haar)...')
    faces = face_report(src, info, samples, duration)
    heads = [o['head'] for o in faces['per_sample'] if o.get('face')]
    head01 = None
    if heads:
        W0, H0 = info['width'], info['height']
        head01 = [float(np.median([h[0] for h in heads])) / W0, float(np.median([h[1] for h in heads])) / H0,
                  float(np.median([h[0] + h[2] for h in heads])) / W0, float(np.median([h[1] + h[3] for h in heads])) / H0]
        head01 = [min(1.0, max(0.0, v)) for v in head01]
    events, ls, absn = detect_events(frames, fps, head01)
    refine_cuts(events, samples)
    pushes = detect_pushes(frames, ls, events, fps, faces['per_sample'])
    log(f'  {len(frames)} frames, {len(events)} events, {len(pushes)} slow zooms')
    log('captions...')
    cap, _ = caption_report(samples, info, words, duration)
    f0 = samples[0]['blocks'] if samples else []
    hook0 = None
    if f0:
        b = max(f0, key=lambda b: b['box'][2] * b['box'][3])
        yc = (b['box'][1] + b['box'][3] / 2) / info['height']
        hook0 = {'polarity': b['polarity'], 'box': b['box'], 'lines': b['lines'],
                 'zone': 'top' if yc < 0.30 else 'center' if yc < 0.58 else 'lower third' if yc < 0.86 else 'bottom'}
    log('color / graphics...')
    color = color_report(samples, info)
    log('audio...')
    audio = audio_report(src, duration, events, words, info)
    pacing = pacing_report(events, duration, words, audio, fps)
    bd = {'tool': 'helpers/style_breakdown.py', 'source': src, 'name': name, 'info': info,
          'captions_sidecar': os.path.abspath(a.captions) if a.captions else None, 'captions_offset': a.captions_offset,
          'thresholds': {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float, tuple, dict))},
          'events': events, 'pushes': pushes, 'pacing': pacing, 'captions': cap, 'hook_text_frame0': hook0,
          'faces': {k: v for k, v in faces.items() if k != 'per_sample'}, 'color': color, 'audio': audio}
    bd['conflicts'] = build_conflicts(bd, info)
    # cuts.json / cuts.csv
    rows = []
    shot = 0
    for e in events:
        if e['kind'] in ('hard cut', 'layout cut'):
            shot += 1
        rows.append({'time_s': e['t'], 'frame': e['n'], 'kind': e['kind'], 'is_cut': e['kind'] != 'overlay change',
                     'ratio': e.get('ratio'), 'frames': e.get('frames'), 'scale_before': e.get('scale_before'),
                     'scale_after': e.get('scale_after'), 'inliers': e.get('inliers'), 'changed_area': e.get('changed_area'),
                     'end_s': e.get('peak_t'), 'shot': shot})
    for p in pushes:
        kind = (f'push {p["easing"]} {p["direction"]}' if p['source'] == 'camera zoom' else
                'subject motion (not a zoom)' if p['source'].startswith('probably') else 'graphic/B-roll motion (not a zoom)')
        rows.append({'time_s': p['start'], 'frame': int(round(p['start'] * fps)), 'kind': kind,
                     'is_cut': False, 'ratio': round(p['to'] / p['from'], 3), 'frames': int(round(p['duration'] * fps)),
                     'scale_before': p['from'], 'scale_after': p['to'], 'inliers': None, 'changed_area': None,
                     'end_s': p['end'], 'shot': None})
    rows.sort(key=lambda r: r['time_s'])
    with open(os.path.join(out, 'cuts.json'), 'w', encoding='utf-8') as f:
        json.dump({'source': src, 'fps': fps, 'duration': duration, 'events': events, 'pushes': pushes}, f, indent=2)
    with open(os.path.join(out, 'cuts.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['time_s'])
        w.writeheader()
        w.writerows(rows)
    log('contact sheet...')
    cells = contact_sheet(src, info, events, camera_pushes(pushes), os.path.join(out, 'contact_sheet.jpg'), duration)
    with open(os.path.join(out, 'breakdown.json'), 'w', encoding='utf-8') as f:
        json.dump(bd, f, indent=2, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    guide = build_guide(name, src, info, bd)
    with open(os.path.join(out, 'style_guide.md'), 'w', encoding='utf-8') as f:
        f.write(guide)
    # summary
    print('\n=== style breakdown summary ===')
    for e in events:
        if e['kind'] == 'overlay change':
            continue
        extra = (f" x{e['ratio']:.3f} {e['frames']}f (peak ~{e.get('peak_scale_est', e['ratio'])})" if e['kind'].startswith(('punch in', 'fast'))
                 else f" x{e['ratio']:.3f} {e['frames']}f" if e['kind'] == 'punch out' else f" ({e['detail']})" if e.get('detail') else '')
        print(f"  {e['t']:7.2f}s  {e['kind']}{extra}")
    for p in pushes:
        print(f"  {p['start']:7.2f}-{p['end']:.2f}s  {'push ' + p['easing'] if p['source'] == 'camera zoom' else p['source'][:40]} "
              f"{p['from']:.3f}->{p['to']:.3f} ({p['rate_per_s']:+.4f}/s, R2 {p['r2']})")
    print(f"  overlay changes (not cuts): {sum(1 for e in events if e['kind'] == 'overlay change')}")
    print(f"  pacing: {pacing['per_min']}")
    if cap.get('detected'):
        print(f"  captions: {cap['main_zone']} y {cap['main_zone_y_pct']} %, lines {cap['lines_per_block']}, "
              f"highlights {cap['highlight_colors']}, {cap['flips_per_min']} flips/min")
    if audio.get('has_audio'):
        print(f"  audio: {audio['integrated_lufs']} LUFS, TP {audio['true_peak_dbtp']}, bed {audio['music_bed']['verdict']}, "
              f"sfx hits {audio['sfx']['hits_at_edits']}")
    print('  conflicts: ' + '; '.join(f"{c['status']}: {c['what']}" for c in bd['conflicts'] if c['status'] != 'OK'))
    for fn in ('cuts.json', 'cuts.csv', 'contact_sheet.jpg', 'breakdown.json', 'style_guide.md'):
        print('  ' + os.path.join(out, fn))
    print(f'done in {time.time() - t_start:.0f}s ({cells} contact-sheet cells). Waiting for you to pick what to apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
