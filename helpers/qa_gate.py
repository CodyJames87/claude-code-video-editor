#!/usr/bin/env python3
"""Finished-MP4 QA gate: automatic checks + ONE pass/fail report, run between finish.mjs and deliver.py.

  python helpers/qa_gate.py out/<name>-shorts_final.mp4 [--props props/<name>.json] [--captions <captions.json>]
         [--edl <cut.json>] [--out-dir <dir>] [--times 1.2,4.5] [--allow-still 30.1-33.0 ...]
         [--accept-unsure "reason"] [--no-frames]

It does NOT replace looking at the frames: it calls helpers/qc_frames.py for the stills + contact sheet, adds a
face-safe sheet, and tells you to LOOK. deliver.py refuses to deliver a final whose latest gate report is FAIL unless
`--qa-override "reason"` is given (the reason is logged in review/review-log.json).

Checks (status PASS / FAIL / WARN / SKIP + a one-line reason; WARN never blocks, FAIL always does):
  encode       qc_frames.py spec checks (h264, yuv420p, aac 48 kHz, size) + yuv420p/tv range (iPhone-safe)
  black        near-black run >= BLACK_SEC (0.20 s) (ffmpeg blackdetect, pix_th 0.10, 98 % of the picture)
  freeze       still picture >= FREEZE_SEC (1.0 s) outside the allowed still windows (Takeover / full-screen cards /
               tailHoldSec from props, plus --allow-still a-b) (ffmpeg freezedetect, noise -60 dB)
  flash        a 1-2 frame picture spike that jumps away and comes straight back (luma OR colour, e.g. a raw 4-up
               frame at a layout cut): mean abs diff >= FLASH_DIFF (40/255) out and back within 2 frames
  loudness     -14 +/-1 LUFS integrated, true peak <= -1 dBTP: finish.mjs's own verdict from <final>.finish.json
               when it matches this file (size + mtime), else measured with the SAME ebur128 filter + thresholds
  clipping     sample-peak flat tops (>= 3 samples at |x| >= 0.999, digital clipping) or true peak over the cap
  cut-seams    splices from --edl (cutlist.py output / {"segments"|"keep": [{start,end}]}, SOURCE seconds), the props
               trim in/out, and jump cuts detected in the picture (heuristic): clipped word (cut inside a word),
               doubled word (same word both sides of a splice), splice click (short HF transient at the cut).
               EDL / trim issues FAIL; issues at detected (heuristic) cuts WARN.
  face-safe    helpers/face_safe.py detector run ON THE FINAL at sampled times + every punch/push peak + card mids:
               text/graphic boxes (from props, approximate) hitting the padded head = FAIL; cap/chin outside the video
               panel = FAIL; detector UNSURE (face missed at a peak, or found in < 60 % of samples) = FAIL unless
               --accept-unsure "reason" (then WARN, reason recorded).
Exit: 0 = PASS (still LOOK at the sheets), 1 = FAIL, 2 = usage error.
Outputs (default <final dir>/qa_<stem>/): qa_report.json, qa_report.md, frames/ + contact_sheet.jpg (qc_frames.py),
face_safe_sheet.jpg (annotated: blue = head incl. cap/chin margins, orange = text boxes, magenta = a conflict).
"""
import argparse, datetime, json, os, re, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import props_util as pu  # noqa: E402

BLACK_SEC = 0.20
FREEZE_SEC = 1.0
FLASH_DIFF = 40.0     # mean abs diff (0-255) of a 36x64 RGB thumbnail: "jumped away"
FLASH_BACK = 14.0     # ... and "came back" (frame n+k vs n-1)
CLIP_RUN = 3          # consecutive samples at full scale = a flat top
CLIP_LEVEL = 0.999
JUMP_SCORE = 6.0      # scdet score (0-100) that counts as a picture jump (talking-head jump cut)
EVENT_GUARD = 4 / 30  # s: a detected jump this close to a known overlay / camera / layout event is that event
CLICK_RATIO = 8.0     # HF energy in the 1 ms window at the splice vs the median around it (~18 dB)
CLICK_FLOOR = 10 ** (-42 / 20)
WORD_EDGE = 0.035     # s: a cut must be this far inside a word to count as "clipped" (transcript timing slop)
FACE_PAD = 40.0       # px between text boxes and the head box (face_safe.py default)
CAP_REAL, CHIN_REAL = 0.47, 0.24  # measured cap / chin extents (face heights) for the crop test (face_safe margins are padded)


def ff(args, **kw):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, **kw)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,pix_fmt,color_range,r_frame_rate,sample_rate",
                        "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in j.get("streams", []) if s["codec_type"] == "audio"), None)
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(j.get("format", {}).get("duration", 0)), "w": v.get("width"), "h": v.get("height"),
            "fps": float(num) / float(den or 1), "pix_fmt": v.get("pix_fmt"), "color_range": v.get("color_range"),
            "vcodec": v.get("codec_name"), "audio": a}


def chk(name, status, reason, **details):
    return {"name": name, "status": status, "reason": reason, "details": details}


# ---------------------------------------------------------------- picture checks
def black_freeze(path):
    r = ff(["-i", path, "-an", "-vf", f"scale=270:-2,blackdetect=d={BLACK_SEC}:pix_th=0.10:pic_th=0.98,"
            f"freezedetect=n=-60dB:d={FREEZE_SEC}", "-f", "null", "-"], text=True)
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]
    fs = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r.stderr)]
    fe = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", r.stderr)]
    freezes = [(s, fe[i] if i < len(fe) else None) for i, s in enumerate(fs)]
    return blacks, freezes


def thumbs(path, w, h):
    tw, th = (36, 64) if (h or 1) >= (w or 1) else (64, 36)
    r = ff(["-v", "error", "-i", path, "-an", "-vf", f"scale={tw}:{th}:flags=area,format=rgb24", "-f", "rawvideo", "-"])
    a = np.frombuffer(r.stdout, np.uint8)
    n = a.size // (tw * th * 3)
    return a[: n * tw * th * 3].reshape(n, th, tw, 3).astype(np.float32)


def flashes(fr, fps):
    out = []
    d = lambda i, j: float(np.abs(fr[i] - fr[j]).mean())
    i = 1
    while i < len(fr) - 1:
        if d(i, i - 1) >= FLASH_DIFF:
            for k in (1, 2):  # the spike lasts k frames, then the picture is back to what it was
                if i + k < len(fr) and d(i + k, i - 1) <= FLASH_BACK and d(i + k, i + k - 1) >= FLASH_DIFF:
                    out.append({"t": round(i / fps, 3), "frame": i, "frames": k, "jump": round(d(i, i - 1), 1)})
                    i += k
                    break
        i += 1
    return out


def jump_cuts(path):
    r = ff(["-i", path, "-an", "-vf", f"scale=360:-2,scdet=threshold={JUMP_SCORE}", "-f", "null", "-"], text=True)
    return [(float(t), float(s)) for s, t in re.findall(r"lavfi\.scd\.score: ([\d.]+), lavfi\.scd\.time: ([\d.]+)", r.stderr)]


# ---------------------------------------------------------------- audio checks
def loudness(path, info):
    side = os.path.splitext(path)[0] + ".finish.json"
    st = os.stat(path)
    if os.path.exists(side):
        try:
            j = pu.load_json(side)
            if j.get("size") == st.st_size and abs(j.get("mtime_ms", 0) - st.st_mtime * 1000) < 2000 and j.get("loudnorm"):
                return {"source": "finish.mjs sidecar", "I": j["integrated_lufs"], "TP": j["true_peak_dbtp"],
                        "finish_exit": j.get("exit_code")}
        except Exception:
            pass
    r = ff(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], text=True)
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    TP = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return {"source": "measured (finish.mjs filter: ebur128 peak=true)", "I": float(I[-1]) if I else None,
            "TP": float(TP[-1]) if TP else None, "finish_exit": None}


def audio_pcm(path):
    r = ff(["-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", "48000", "-f", "f32le", "-"])
    a = np.frombuffer(r.stdout, np.float32)
    return a[: a.size // 2 * 2].reshape(-1, 2)


def flat_tops(pcm):
    runs = 0
    for ch in range(pcm.shape[1]):
        m = np.abs(pcm[:, ch]) >= CLIP_LEVEL
        if not m.any():
            continue
        dm = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
        starts, ends = np.where(dm == 1)[0], np.where(dm == -1)[0]
        runs += int(((ends - starts) >= CLIP_RUN).sum())
    return runs


def click_at(mono, t, sr=48000):
    """HF transient at a splice: 1 ms RMS of the first difference, peak within +/-8 ms of t vs the median of +/-40 ms."""
    c = int(t * sr)
    a, b = max(1, c - int(0.04 * sr)), min(len(mono), c + int(0.04 * sr))
    if b - a < sr * 0.02:
        return None
    hf = np.diff(mono[a - 1:b])
    win = int(0.001 * sr)
    n = len(hf) // win
    rms = np.sqrt((hf[: n * win].reshape(n, win) ** 2).mean(axis=1))
    mid = (c - a) // win
    near = rms[max(0, mid - 8): mid + 9]
    far = np.concatenate([rms[: max(0, mid - 8)], rms[mid + 9:]])
    if not len(near) or not len(far):
        return None
    pk, med = float(near.max()), float(np.median(far)) + 1e-9
    return {"ratio": round(pk / med, 1), "level_db": round(20 * np.log10(pk + 1e-12), 1),
            "click": pk / med >= CLICK_RATIO and pk >= CLICK_FLOOR}


# ---------------------------------------------------------------- cut seams
def load_edl(path):
    j = pu.load_json(path)
    if isinstance(j, dict) and j.get("picks"):
        return j["picks"][0]["segments"], j.get("transcript")
    if isinstance(j, dict):
        return j.get("segments") or j.get("keep") or [], j.get("transcript")
    return j, None


def seam_checks(edl_segs, src_words, tl_words, trim, jumps, events, mono, final_dur):
    issues, splices = [], []
    # 1) EDL splices: segment k ends at e_k (source), next starts at s_{k+1}; output time = sum of durations
    tout = 0.0
    for k, s in enumerate(edl_segs):
        tout += s["end"] - s["start"]
        if k + 1 < len(edl_segs) and abs(edl_segs[k + 1]["start"] - s["end"]) > 0.01:  # contiguous = no splice
            splices.append({"t": round(tout, 3), "kind": "edl", "left": s["end"], "right": edl_segs[k + 1]["start"]})
    # 2) trim in / out (source seconds)
    if trim:
        if trim.get("start"):
            splices.append({"t": 0.0, "kind": "trim-in", "left": None, "right": float(trim["start"])})
        if trim.get("end"):
            splices.append({"t": round(float(trim["end"]) - float(trim.get("start") or 0), 3), "kind": "trim-out",
                            "left": float(trim["end"]), "right": None})
    # 3) picture jumps not explained by a known event
    for t, sc in jumps:
        if not any(abs(t - e) <= EVENT_GUARD for e in events) and 0.1 < t < final_dur - 0.1:
            splices.append({"t": round(t, 3), "kind": "detected", "score": sc})
    nw = lambda w: pu.norm(w["text"])
    for sp in splices:
        hard = sp["kind"] != "detected"
        sev = "FAIL" if hard else "WARN"
        if sp["kind"] in ("edl", "trim-in", "trim-out"):
            for side in ("left", "right"):
                b = sp.get(side)
                if b is None:
                    continue
                for w in src_words:
                    if w["start"] + WORD_EDGE < b < w["end"] - WORD_EDGE:
                        issues.append({"sev": sev, "t": sp["t"], "type": "clipped word",
                                       "msg": f'{sp["kind"]} cut at source {b:.3f}s lands inside "{w["text"].strip()}" ({w["start"]:.3f}-{w["end"]:.3f})'})
            if sp["kind"] == "edl":
                # heard before the cut = any word that STARTED before it (a partly kept word is still heard)
                before = [w for w in src_words if w["start"] < sp["left"] - WORD_EDGE and w["end"] > sp["left"] - 1.2]
                after = [w for w in src_words if w["end"] > sp["right"] + WORD_EDGE and w["start"] < sp["right"] + 1.2]
                if before and after:
                    b2 = [nw(w) for w in before[-2:]]
                    a2 = [nw(w) for w in after[:2]]
                    if b2[-1] and b2[-1] == a2[0] or (len(b2) == 2 and len(a2) == 2 and b2 == a2):
                        issues.append({"sev": sev, "t": sp["t"], "type": "doubled word",
                                       "msg": f'"{before[-1]["text"].strip()}" heard on both sides of the splice at {sp["t"]:.2f}s'})
        else:
            near = [w for w in tl_words if w["start"] + WORD_EDGE < sp["t"] < w["end"] - WORD_EDGE]
            for w in near:
                issues.append({"sev": sev, "t": sp["t"], "type": "clipped word?",
                               "msg": f'picture jump at {sp["t"]:.2f}s inside "{w["text"].strip()}" (transcript timing; check by ear)'})
            before = [w for w in tl_words if sp["t"] - 1.0 < w["end"] <= sp["t"] + WORD_EDGE]
            after = [w for w in tl_words if sp["t"] - WORD_EDGE <= w["start"] < sp["t"] + 1.0]
            if before and after and nw(before[-1]) and nw(before[-1]) == nw(after[0]):
                issues.append({"sev": sev, "t": sp["t"], "type": "doubled word?",
                               "msg": f'"{after[0]["text"].strip()}" on both sides of the jump at {sp["t"]:.2f}s'})
        if mono is not None and 0 < sp["t"] < final_dur:
            c = click_at(mono, sp["t"])
            sp["click"] = c
            if c and c["click"]:
                issues.append({"sev": sev, "t": sp["t"], "type": "splice click",
                               "msg": f'HF transient at {sp["t"]:.3f}s ({c["ratio"]}x the surrounding level, {c["level_db"]} dBFS)'})
    # 4) immediate word repeats anywhere (info: a natural "that that" is fine, a splice double is not)
    reps = []
    for a, b in zip(tl_words, tl_words[1:]):
        if nw(a) and nw(a) == nw(b) and b["start"] - a["end"] < 0.6 and len(nw(a)) > 1:
            reps.append(f'"{a["text"].strip()} {b["text"].strip()}" at {a["start"]:.2f}s')
    return splices, issues, reps


# ---------------------------------------------------------------- face-safe on the final
def face_check(path, info, props, ovs, caps, extra_times, accept_unsure, out_dir):
    try:
        import cv2  # noqa
        import face_safe as fsafe
    except SystemExit:
        return chk("face-safe", "FAIL", "OpenCV missing: cannot run the face-safe gate (pip install opencv-python-headless<5)"), None
    W, H = info["w"], info["h"]
    tall = H and W and H / W > 1.7
    dur = info["duration"]
    k = H / 1920.0
    # regular grid: every 0.5 s, every 0.25 s inside small video panels (split bands) where Haar is flakier
    times = set()
    for t in np.arange(0.25, dur - 0.2, 0.25):
        pnl = pu.panel_at(props, ovs, t) if props else [0, 0, 1080, 1920]
        if abs(t * 2 - round(t * 2)) < 1e-6 or (pnl and pnl[3] < 1000):
            times.add(round(float(t), 2))
    peaks = []
    if props:
        for e in pu.camera_events(ovs):
            peaks.append(e["peak"])
            times.add(round(e["peak"], 3))
        for o in ovs:
            if not o["_missing"] and o["type"] not in pu.CAMERA:
                times.add(round(o["start"] + min(0.5, o["duration"] / 2), 3))
                times.add(round(o["start"] + o["duration"] / 2, 3))
    times |= set(t for t in extra_times if 0 <= t < dur)
    times = sorted(t for t in times if t < dur - 0.05)
    # group samples by layout (the detector's outlier rejection assumes one face size per call)
    groups = {}
    for t in times:
        panel = pu.panel_at(props, ovs, t) if props else [0, 0, 1080, 1920]
        if panel is None:
            continue  # video hidden (takeover / full-screen card): no face expected
        groups.setdefault(tuple(panel), []).append(t)
    rows, conflicts, unsure = [], [], []
    for panel, ts in groups.items():
        frac = max(0.04, 0.12 * (panel[3] / 1920.0) * (1.0 if panel[3] >= 1000 else 0.8))
        samples, _ = fsafe.detect_at(path, ts, min_face=frac, max_hold=0.6)
        direct = sum(1 for s in samples if s["face"] and not s["held"])
        rate = direct / max(1, len(samples))
        if rate < 0.6:
            unsure.append(f"face found directly in {direct}/{len(samples)} samples in panel {list(panel)}")
        for s in samples:
            t = s["t"]
            is_peak = any(abs(t - p) < 0.02 for p in peaks)
            if s["face"] is None or (is_peak and s["held"]):
                if is_peak:
                    unsure.append(f"no direct face detection at the camera peak {t:.2f}s")
                rows.append({"t": t, "head": None, "held": s["held"], "peak": is_peak, "hits": [], "crop": None})
                continue
            x, y, w, h = s["face"]
            head = [v / k for v in fsafe.head_from_face(s["face"])]          # design px, conservative (text test)
            real = [x / k, (y - CAP_REAL * h) / k, w / k, (h * (1 + CAP_REAL + CHIN_REAL)) / k]  # measured extents (crop test)
            p = [v for v in panel]
            crop = []
            if real[1] < p[1] - 2:
                crop.append(f"cap above the panel top by {p[1] - real[1]:.0f}px")
            if real[1] + real[3] > p[1] + p[3] + 2:
                crop.append(f"chin below the panel bottom by {real[1] + real[3] - p[1] - p[3]:.0f}px")
            hits = []
            if props and tall:
                # the face is only visible inside the video panel: clip the head to it, and a box that sits wholly on
                # the band / layout canvas outside the panel can't be on the face (the cap-crop test guards that edge)
                hx0, hy0 = max(head[0], p[0]), max(head[1], p[1])
                hx1, hy1 = min(head[0] + head[2], p[0] + p[2]), min(head[1] + head[3], p[1] + p[3])
                head = [hx0, hy0, max(0, hx1 - hx0), max(0, hy1 - hy0)]
                for name, b in pu.text_boxes_at(props, ovs, caps, t):
                    if b[1] + b[3] <= p[1] or b[1] >= p[1] + p[3] or head[2] <= 0 or head[3] <= 0:
                        continue
                    if fsafe.hits(b, head, FACE_PAD):
                        gap_y = max(head[1] - (b[1] + b[3]), b[1] - (head[1] + head[3]))
                        hits.append({"box": name, "rect": [round(v) for v in b], "gap_px": round(gap_y)})
            rows.append({"t": t, "head": [round(v) for v in head], "real": [round(v) for v in real], "held": s["held"],
                         "peak": is_peak, "hits": hits, "crop": crop or None, "panel": list(panel)})
            for hh in hits:
                conflicts.append(f'{t:.2f}s: {hh["box"]} {hh["rect"]} within {FACE_PAD:.0f}px of the head (incl. cap/chin margins)')
            for c in crop:
                conflicts.append(f"{t:.2f}s: {c}" + (" (punch/push peak)" if is_peak else ""))
    sheet = face_sheet(path, rows, props, ovs, caps, out_dir, k, tall) if rows else None
    notes = []
    if props and not tall:
        notes.append("text boxes are modelled on 9:16 only: on this aspect only cap/chin framing was checked")
    if not props:
        notes.append("no props: text boxes unknown, only cap/chin framing was checked")
    if conflicts:
        st, why = "FAIL", f"{len(conflicts)} face conflict(s): " + "; ".join(conflicts[:3])
    elif unsure:
        if accept_unsure:
            st, why = "WARN", f"detector UNSURE ({'; '.join(unsure[:2])}), accepted: {accept_unsure}"
        else:
            st, why = "FAIL", f"detector UNSURE ({'; '.join(unsure[:2])}): not a silent pass. LOOK at the frames, then re-run with --accept-unsure \"reason\""
    else:
        st, why = "PASS", f"{len(rows)} samples ({len(peaks)} camera peaks): no text on the head, cap + chin inside the picture"
    return chk("face-safe", st, why, conflicts=conflicts, unsure=unsure, notes=notes, samples=rows,
               pad_px=FACE_PAD, sheet=sheet), sheet


def face_sheet(path, rows, props, ovs, caps, out_dir, k, tall):
    """Annotated full frames for camera peaks, conflicts and a few regular samples."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    pick = [r for r in rows if r["peak"] or r["hits"] or r["crop"] or r["head"] is None]
    rest = [r for r in rows if r not in pick]
    pick += rest[:: max(1, len(rest) // 6)][: max(0, 12 - len(pick))]
    pick = sorted(pick, key=lambda r: r["t"])[:16]
    d = os.path.join(out_dir, "face_frames")
    os.makedirs(d, exist_ok=True)
    tiles = []
    for r in pick:
        fp = os.path.join(d, f"face_{r['t']:07.3f}.png")
        ff(["-v", "error", "-y", "-ss", f"{r['t']:.3f}", "-i", path, "-frames:v", "1", fp])
        if not os.path.exists(fp):
            continue
        im = Image.open(fp).convert("RGB")
        dr = ImageDraw.Draw(im)
        S = lambda b: [b[0] * k, b[1] * k, (b[0] + b[2]) * k, (b[1] + b[3]) * k]
        if props and tall:
            for name, b in pu.text_boxes_at(props, ovs, caps, r["t"]):
                dr.rectangle(S(b), outline=(255, 87, 34), width=4)
        if r["head"]:
            dr.rectangle(S(r["head"]), outline=(66, 165, 245), width=5)
            dr.rectangle(S(r["real"]), outline=(66, 165, 245), width=2)
        for hh in r["hits"]:
            dr.rectangle(S(hh["rect"]), outline=(255, 0, 255), width=10)
        if r["crop"]:
            dr.rectangle([0, 0, im.width - 1, im.height - 1], outline=(255, 0, 255), width=16)
        tag = f"{r['t']:.2f}s" + (" PEAK" if r["peak"] else "") + (" NO FACE" if r["head"] is None else "") + \
              (" HIT" if r["hits"] else "") + (" CROP" if r["crop"] else "")
        im = im.resize((270, int(270 * im.height / im.width)))
        ImageDraw.Draw(im).rectangle([0, 0, 270, 22], fill=(33, 33, 33))
        ImageDraw.Draw(im).text((6, 5), tag, fill=(255, 255, 255))
        tiles.append(im)
    if not tiles:
        return None
    cols = 4
    rows_n = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (cols * (tw + 6) + 6, rows_n * (th + 6) + 6), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, (6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + 6)))
    p = os.path.join(out_dir, "face_safe_sheet.jpg")
    sheet.save(p, quality=88)
    return p


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Finished-MP4 QA gate (see module docstring).")
    ap.add_argument("video")
    ap.add_argument("--props")
    ap.add_argument("--captions", help="word-timed captions (SOURCE time, Remotion Caption[]); default: props.transcriptJson")
    ap.add_argument("--edl", help="cut list: cutlist.py output or {segments|keep: [{start,end}]} in SOURCE seconds")
    ap.add_argument("--source-captions", help="source transcript for --edl (default: the EDL's own transcript or --captions)")
    ap.add_argument("--out-dir")
    ap.add_argument("--times", default="", help="extra QC times (s), comma-separated")
    ap.add_argument("--allow-still", action="append", default=[], help="a-b seconds where a still picture is intended")
    ap.add_argument("--accept-unsure", default="", help='reason: turns a face-detector UNSURE into a WARN (recorded)')
    ap.add_argument("--no-frames", action="store_true", help="skip qc_frames.py stills/contact sheet (not for delivery)")
    a = ap.parse_args()
    if not os.path.exists(a.video):
        print(f"missing {a.video}", file=sys.stderr)
        sys.exit(2)
    video = os.path.abspath(a.video)
    stem = os.path.splitext(os.path.basename(video))[0]
    od = os.path.abspath(a.out_dir or os.path.join(os.path.dirname(video), "qa_" + stem))
    os.makedirs(od, exist_ok=True)
    info = probe(video)
    dur, fps = info["duration"], info["fps"] or 30
    props = pu.load_props(a.props) if a.props else None
    caps = pu.load_captions(a.captions or (props or {}).get("transcriptJson")) if (a.captions or props) else []
    ovs = pu.resolved_overlays(props, caps) if props else []
    t0 = pu.trim_start(props) if props else 0.0
    tl_words = [{"text": c["text"], "start": c["startMs"] / 1000 - t0, "end": c["endMs"] / 1000 - t0} for c in caps]
    extra = [float(x) for x in a.times.split(",") if x.strip()]
    checks = []
    print(f"QA gate: {video} ({dur:.2f}s {info['w']}x{info['h']} @ {fps:.2f})", flush=True)

    # encode / spec + frames + contact sheet (qc_frames.py: the existing look-at-the-frames step)
    cev = pu.camera_events(ovs) if props else []
    qtimes = sorted(set([0.03, 1.0] + [e["peak"] for e in cev] + [round(e["end"] - 1 / fps, 3) for e in cev if e["type"] == "PushIn"]
                        + [round(o["start"] + o["duration"] / 2, 2) for o in ovs if not o["_missing"] and o["type"] not in pu.CAMERA]
                        + extra))
    qtimes = [t for t in qtimes if 0 <= t < dur]
    sheet = None
    if a.no_frames:
        checks.append(chk("encode", "SKIP", "--no-frames: qc_frames.py not run (not allowed for delivery)"))
    else:
        r = subprocess.run([sys.executable, os.path.join(HERE, "qc_frames.py"), video, "--out-dir", os.path.join(od, "frames"),
                            "--max-frames", "20", "--times", ",".join(f"{t:.2f}" for t in qtimes)], capture_output=True, text=True)
        rep = os.path.join(od, "frames", "qc_report.json")
        issues = []
        if os.path.exists(rep):
            q = pu.load_json(rep)
            sheet = q.get("contact_sheet")
            issues = [i for i in q.get("issues", []) if not re.search(r"loudness|true peak", i)]
        else:
            issues = [f"qc_frames.py failed: {r.stderr.strip()[-300:]}"]
        if info["pix_fmt"] != "yuv420p" or info["color_range"] not in ("tv", None):
            issues.append(f"{info['pix_fmt']} / {info['color_range']} range: not the iPhone-safe yuv420p / tv encode (run finish.mjs)")
        checks.append(chk("encode", "FAIL" if issues else "PASS",
                          "; ".join(issues) if issues else f"{info['vcodec']} {info['pix_fmt']}/{info['color_range']}, stills + contact sheet written",
                          contact_sheet=sheet, qc_times=qtimes))

    # black / freeze
    blacks, freezes = black_freeze(video)
    bad_b = [b for b in blacks if b[1] - b[0] >= BLACK_SEC]
    checks.append(chk("black", "FAIL" if bad_b else "PASS",
                      f"{len(bad_b)} near-black run(s) >= {BLACK_SEC}s: " + ", ".join(f"{s:.2f}-{e:.2f}s" for s, e in bad_b) if bad_b
                      else f"no near-black run >= {BLACK_SEC}s", runs=blacks))
    allowed = pu.allowed_still_ranges(props, ovs, dur) if props else []
    for s in a.allow_still:
        x, y = s.split("-")
        allowed.append((float(x), float(y), "--allow-still"))
    bad_f, ok_f = [], []
    for s, e in freezes:
        e = e if e is not None else dur
        why = next((w for (x, y, w) in allowed if s >= x - 0.25 and e <= y + 0.25), None)
        (ok_f if why else bad_f).append({"start": round(s, 2), "end": round(e, 2), "allowed_by": why})
    checks.append(chk("freeze", "FAIL" if bad_f else "PASS",
                      f"{len(bad_f)} still hold(s) >= {FREEZE_SEC}s outside allowed windows: " + ", ".join(f"{f['start']}-{f['end']}s" for f in bad_f)
                      if bad_f else f"no unintended still >= {FREEZE_SEC}s" + (f" ({len(ok_f)} allowed: " + ", ".join(f"{f['start']}-{f['end']}s {f['allowed_by']}" for f in ok_f) + ")" if ok_f else ""),
                      freezes=bad_f + ok_f, allowed_windows=allowed))

    # flash
    fr = thumbs(video, info["w"], info["h"])
    fl = flashes(fr, fps)
    checks.append(chk("flash", "FAIL" if fl else "PASS",
                      f"{len(fl)} flash frame(s): " + ", ".join(f"{f['t']:.2f}s ({f['frames']}f, diff {f['jump']})" for f in fl) if fl
                      else f"no 1-2 frame spike (diff >= {FLASH_DIFF:.0f} out and back) in {len(fr)} frames", flashes=fl))

    # loudness + clipping
    pcm = mono = None
    if info["audio"]:
        L = loudness(video, info)
        ok = L["I"] is not None and -15 <= L["I"] <= -13 and L["TP"] is not None and L["TP"] <= -1
        checks.append(chk("loudness", "PASS" if ok else "FAIL",
                          f"{L['I']} LUFS, TP {L['TP']} dBTP ({L['source']}); need -14 +/-1 LUFS, TP <= -1", **L))
        pcm = audio_pcm(video)
        mono = pcm.mean(axis=1) if pcm.size else None
        runs = flat_tops(pcm) if pcm.size else 0
        sp = float(20 * np.log10(np.abs(pcm).max() + 1e-12)) if pcm.size else None
        over = L["TP"] is not None and L["TP"] > -1
        checks.append(chk("clipping", "FAIL" if runs or over else "PASS",
                          (f"{runs} flat-top run(s) (>= {CLIP_RUN} samples at full scale)" if runs else "") +
                          ("; " if runs and over else "") + (f"true peak {L['TP']} dBTP over the -1 cap" if over else "")
                          if runs or over else f"sample peak {sp:.1f} dBFS, no flat tops, TP within the cap",
                          sample_peak_dbfs=round(sp, 2) if sp is not None else None, flat_top_runs=runs))
    else:
        checks.append(chk("loudness", "FAIL", "no audio stream"))
        checks.append(chk("clipping", "SKIP", "no audio stream"))

    # cut seams
    edl_segs, src_words = [], []
    if a.edl:
        edl_segs, edl_tr = load_edl(a.edl)
        src = a.source_captions or a.captions or edl_tr or (props or {}).get("transcriptJson")
        import cutlist as cl
        try:
            srcj = pu.load_json(src if os.path.exists(src) else pu.public_path(src))
            src_words = cl.normalize_words(srcj) if not (isinstance(srcj, list) and srcj and "startMs" in srcj[0]) else \
                [{"text": c["text"], "start": c["startMs"] / 1000, "end": c["endMs"] / 1000} for c in srcj]
        except Exception as e:  # noqa
            src_words = []
    elif caps:
        src_words = [{"text": c["text"], "start": c["startMs"] / 1000, "end": c["endMs"] / 1000} for c in caps]
    events = []
    for o in ovs:
        if o["_missing"]:
            continue
        events += [o["start"], o["end"]]
        if o["type"] in pu.CAMERA:
            p = o.get("props", {})
            events += [o["start"] + p.get("inFrames", 4) / fps, o["end"] + p.get("outFrames", 4) / fps]
    if props and props.get("hook"):
        events.append(float(props["hook"].get("duration", 2.0)))
    jumps = jump_cuts(video)
    splices, issues, reps = seam_checks(edl_segs, src_words, tl_words, (props or {}).get("trim"), jumps, events, mono, dur)
    fails = [i for i in issues if i["sev"] == "FAIL"]
    warns = [i for i in issues if i["sev"] == "WARN"]
    nk = {k: sum(1 for s in splices if s["kind"] == k) for k in ("edl", "trim-in", "trim-out", "detected")}
    summary = f"splices: {nk['edl']} EDL, {nk['trim-in'] + nk['trim-out']} trim, {nk['detected']} detected jump(s)"
    if not tl_words and not src_words:
        checks.append(chk("cut-seams", "SKIP", f"no word-timed transcript ({summary}); pass --props or --captions",
                          splices=splices))
    else:
        st = "FAIL" if fails else "WARN" if warns or reps else "PASS"
        why = "; ".join(i["msg"] for i in (fails or warns)[:3]) if (fails or warns) else \
            (f"{summary}; repeated words to check by ear: " + ", ".join(reps[:3]) if reps else f"{summary}: no clipped/doubled word, no click")
        if not a.edl and not (props or {}).get("trim") and not fails:
            why += " (no --edl given: only trim + picture-detected cuts were checked)"
        checks.append(chk("cut-seams", st, why, splices=splices, issues=issues, repeats=reps,
                          known_events=sorted(round(e, 3) for e in events)))

    # face-safe
    fc, fsheet = face_check(video, info, props, ovs, caps, extra + qtimes, a.accept_unsure, od)
    checks.append(fc)

    overall = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    st = os.stat(video)
    report = {"tool": "helpers/qa_gate.py", "video": video, "size": st.st_size, "mtime_ms": round(st.st_mtime * 1000),
              "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "props": os.path.abspath(a.props) if a.props else None, "edl": os.path.abspath(a.edl) if a.edl else None,
              "duration": dur, "resolution": f"{info['w']}x{info['h']}", "fps": fps, "overall": overall,
              "accept_unsure": a.accept_unsure or None, "contact_sheet": sheet, "face_safe_sheet": fsheet,
              "thresholds": {"black_sec": BLACK_SEC, "freeze_sec": FREEZE_SEC, "flash_diff": FLASH_DIFF, "flash_back": FLASH_BACK,
                             "clip_run": CLIP_RUN, "jump_score": JUMP_SCORE, "click_ratio": CLICK_RATIO, "face_pad_px": FACE_PAD},
              "checks": checks,
              "look": "Automatic checks are not the QC. LOOK at contact_sheet.jpg and face_safe_sheet.jpg before delivering."}
    pu.save_json(report, os.path.join(od, "qa_report.json"))
    md = [f"# QA gate: {os.path.basename(video)}", "", f"**Overall: {overall}**  ({report['time']})", "",
          f"- File: `{video}` ({dur:.2f} s, {info['w']}x{info['h']}, {fps:.2f} fps)",
          f"- Props: `{report['props']}`" if report["props"] else "- Props: none (face/text checks limited)",
          f"- Contact sheet: `{sheet}`" if sheet else "- Contact sheet: not made",
          f"- Face-safe sheet: `{fsheet}`" if fsheet else "- Face-safe sheet: not made", "",
          "| Check | Status | Reason |", "|---|---|---|"]
    md += [f"| {c['name']} | {c['status']} | {c['reason'].replace('|', '/')} |" for c in checks]
    md += ["", "WARN never blocks; any FAIL blocks `deliver.py` unless `--qa-override \"reason\"` (logged in review/review-log.json).",
           "", "**Now LOOK at the contact sheet and the face-safe sheet.** The gate does not replace the visual QC.", ""]
    with open(os.path.join(od, "qa_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    for c in checks:
        print(f"  {c['status']:<5} {c['name']:<10} {c['reason']}")
    print(f"QA GATE: {overall}  report: {os.path.join(od, 'qa_report.md')}")
    if sheet:
        print(f"contact sheet: {sheet}")
    if fsheet:
        print(f"face-safe sheet: {fsheet}")
    print("Now LOOK at the sheets: the gate adds checks, it does not replace looking.")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
