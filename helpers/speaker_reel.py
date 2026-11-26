#!/usr/bin/env python3
"""Speaker-tracking 9:16 reel builder for multi-person podcast shots (opt-in).

Extends helpers/speaker_track.py (Haar faces + clustering). Pipeline:

  faces     sample + cluster faces in the clip -> <stem>.faces.json  (edit names / boxes by hand if needed)
  activity  per-frame mouth activity per person; labels each caption word with a speaker
            -> <stem>.speakers.json (words with speaker + confidence)
  plan      turns -> shots, applying CLAUDE.md rules: hard cut on sustained change, 1.5-2 s hold,
            ignore interjections < 0.8 s, reaction cuts only where listed, stacked composite during
            rapid back-and-forth -> <stem>.shots.json  (edit before render)
  render    ffmpeg reframe of the 16:9 source to 1080x1920 per the shot list (single = chin-safe crop on
            that face; stack = dark #111418 bg with full-face bands) -> mp4 (audio copied)

Captions / PunchIns / SFX are then added by Remotion (ShortsVideo) on top of the reframed video, so
bottomRanges come from `plan` too (caption band per shot type).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speaker_track as st  # noqa: E402

TW, TH = 1080, 1920
BG = "0x111418"  # functional dark layout canvas (not typography ink); 
HOLD_MIN, HOLD_MAX, IGNORE_MAX = st.HOLD_MIN, st.HOLD_MAX, st.IGNORE_MAX


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jsave(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    log(f"wrote {p}")


# ---------------------------------------------------------------- faces
def cmd_faces(a):
    samples, W, H = st.sample_faces(a.video, a.start, a.end, step=a.step)
    clusters = st.cluster_faces(samples, gap=a.gap)
    st.release_samples(samples)
    names = (a.names or "").split(",") if a.names else []
    people = []
    for i, c in enumerate(clusters):
        fw, fh = c["fw"], c["fh"]
        people.append({
            "name": names[i] if i < len(names) else c["id"],
            "cluster": c["id"], "count": c["count"],
            # face box in source px (median)
            "box": [round(c["cx"] * W - fw / 2), round(c["cy"] * H - fh / 2), round(fw), round(fh)],
        })
    jsave(a.out, {"video": a.video, "frame_size": [W, H], "people": people})


# ---------------------------------------------------------------- activity
def mouth_box(box, W, H):
    x, y, w, h = box
    mx, my = x + int(w * 0.15), y + int(h * 0.58)
    mw, mh = int(w * 0.70), int(h * 0.50)
    return max(0, mx), max(0, my), min(W, mx + mw), min(H, my + mh)


def frame_activity(video, people, W, H):
    """Per frame: mouth-motion minus head-motion for each person (robust to nodding)."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev = None
    rows = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(g, (5, 5), 0)
        row = []
        for p in people:
            x0, y0, x1, y1 = mouth_box(p["box"], W, H)
            bx, by, bw, bh = p["box"]
            if prev is None:
                row.append(0.0)
                continue
            m = float(np.mean(cv2.absdiff(g[y0:y1, x0:x1], prev[y0:y1, x0:x1])))
            # upper face (eyes/forehead) = head motion reference
            u = float(np.mean(cv2.absdiff(g[by:by + bh // 2, bx:bx + bw], prev[by:by + bh // 2, bx:bx + bw])))
            row.append(max(0.0, m - 0.6 * u))
        rows.append(row)
        prev = g
    cap.release()
    return fps, np.array(rows)


def cmd_activity(a):
    import numpy as np
    fx = jload(a.faces)
    W, H = fx["frame_size"]
    people = fx["people"]
    fps, act = frame_activity(a.video, people, W, H)
    # z-score per person so a big face doesn't win just by pixel count
    mu, sd = act.mean(axis=0), act.std(axis=0) + 1e-6
    z = (act - mu) / sd
    cap = jload(a.captions)
    words = cap if isinstance(cap, list) else cap.get("words", cap.get("captions", []))
    out = []
    for w in words:
        s = (w.get("startMs", 0) / 1000.0) if "startMs" in w else w["start"]
        e = (w.get("endMs", 0) / 1000.0) if "endMs" in w else w["end"]
        f0, f1 = int(s * fps), max(int(s * fps) + 1, int(e * fps) + 1)
        seg = z[f0:f1] if f1 <= len(z) else z[f0:]
        if len(seg) == 0:
            continue
        m = seg.mean(axis=0)
        order = np.argsort(-m)
        best, second = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
        out.append({"text": w.get("text", ""), "start": round(s, 3), "end": round(e, 3),
                    "speaker": people[best]["name"], "margin": round(float(m[best] - m[second]), 3),
                    "scores": {people[i]["name"]: round(float(m[i]), 2) for i in range(len(people))}})
    # per-second activity table for eyeballing
    sec = []
    for t in range(int(len(z) / fps) + 1):
        seg = z[int(t * fps):int((t + 1) * fps)]
        if len(seg):
            sec.append({"t": t, **{people[i]["name"]: round(float(seg[:, i].mean()), 2) for i in range(len(people))}})
    jsave(a.out, {"fps": fps, "words": out, "per_second": sec})


# ---------------------------------------------------------------- plan
def raw_turns(words):
    turns = []
    for w in words:
        sp = w["speaker"]
        if turns and turns[-1]["speaker"] == sp and w["start"] - turns[-1]["end"] < 1.2:
            turns[-1]["end"] = w["end"]
            turns[-1]["words"] += 1
        else:
            turns.append({"speaker": sp, "start": w["start"], "end": w["end"], "words": 1})
    return turns


def cmd_plan(a):
    """Shot list from labeled words, applying the rules. Manual hints in --hints JSON:
       {"reactions": [{"at": s, "dur": s, "who": name, "why": "..."}],
        "composites": [{"from": s, "to": s, "who": [names top->bottom], "why": "..."}]}
       Composite windows are also proposed automatically (>= 3 sustained-or-not turn changes within 6 s)."""
    sp = jload(a.speakers)
    words = sp["words"]
    hints = jload(a.hints) if a.hints else {}
    dur = a.duration
    turns = raw_turns(words)
    # 1) ignore interjections under IGNORE_MAX (absorbed into the current shot)
    sustained = [t for t in turns if t["end"] - t["start"] >= IGNORE_MAX]
    ignored = [t for t in turns if t["end"] - t["start"] < IGNORE_MAX]
    # 2) auto composite proposal: rapid back-and-forth (>= 3 changes within 6 s among sustained+short turns)
    auto_comp = []
    ch = [t for i, t in enumerate(turns) if i and t["speaker"] != turns[i - 1]["speaker"]]
    for i in range(len(ch) - 2):
        if ch[i + 2]["start"] - ch[i]["start"] <= 6.0:
            auto_comp.append((ch[i]["start"], ch[i + 2]["end"]))
    comps = hints.get("composites", [])
    # 3) base single-speaker shots with hold: switch only to a speaker whose turn lasts >= HOLD_MIN,
    #    and never less than HOLD_MIN after the previous cut.
    shots = []
    cur = None
    for t in sustained:
        if cur is None:
            cur = {"type": "single", "who": t["speaker"], "start": 0.0}
            continue
        if t["speaker"] == cur["who"]:
            continue
        if t["end"] - t["start"] < HOLD_MIN:
            continue  # not sustained: stay on current speaker
        cut = max(t["start"], cur["start"] + HOLD_MIN)
        cur["end"] = round(cut, 3)
        shots.append(cur)
        cur = {"type": "single", "who": t["speaker"], "start": round(cut, 3)}
    cur["end"] = dur
    shots.append(cur)

    def overlay(shots, s0, s1, new):
        out = []
        for sh in shots:
            if sh["end"] <= s0 or sh["start"] >= s1:
                out.append(sh)
                continue
            if sh["start"] < s0:
                out.append(dict(sh, end=s0))
            if sh["end"] > s1:
                out.append(dict(sh, start=s1))
        out.append(dict(new, start=s0, end=s1))
        return sorted(out, key=lambda x: x["start"])

    for c in comps:
        shots = overlay(shots, c["from"], c["to"], {"type": "stack", "who": c["who"], "why": c.get("why", "")})
    for r in hints.get("reactions", []):
        shots = overlay(shots, r["at"], r["at"] + r["dur"], {"type": "reaction", "who": r["who"], "why": r.get("why", "")})
    # merge adjacent identical shots
    merged = []
    for sh in shots:
        if merged and merged[-1]["type"] == sh["type"] and merged[-1]["who"] == sh["who"]:
            merged[-1]["end"] = sh["end"]
        else:
            merged.append(dict(sh))
    for sh in merged:
        sh["start"], sh["end"] = round(sh["start"], 3), round(sh["end"], 3)
        sh["len"] = round(sh["end"] - sh["start"], 3)
    jsave(a.out, {"shots": merged, "turns": turns, "ignored_interjections": ignored,
                  "auto_composite_windows": auto_comp,
                  "rules": {"hold_s": [HOLD_MIN, HOLD_MAX], "ignore_under_s": IGNORE_MAX}})


# ---------------------------------------------------------------- render
def single_crop(box, W, H, ch=960, face_out_y=640):
    """Chin-safe 9:16 crop: crop height ch (2x upscale at 960), face center at face_out_y in the output."""
    cw = int(round(ch * TW / TH)) // 2 * 2
    x, y, w, h = box
    fcx, fcy = x + w / 2, y + h / 2
    scale = TH / ch
    cx0 = min(max(0, fcx - cw / 2), W - cw)
    cy0 = min(max(0, fcy - face_out_y / scale), H - ch)
    return int(cx0), int(cy0), cw, ch


def band_crop(box, W, H, bw, bh, zoom):
    """Crop for a full-width band bw x bh at `zoom` source px per output px^-1; face centered a bit high."""
    cw, ch = int(round(bw / zoom)) // 2 * 2, int(round(bh / zoom)) // 2 * 2
    x, y, w, h = box
    fcx, fcy = x + w / 2, y + h / 2
    cx0 = min(max(0, fcx - cw / 2), W - cw)
    cy0 = min(max(0, fcy - ch * 0.45), H - ch)  # 0.45: hair/cap top stays inside the band
    return int(cx0), int(cy0), cw, ch


def render_box(p):
    """Face box shifted by an optional look-room offset (profile faces: leave space in the look direction)."""
    x, y, w, h = p["box"]
    return [x + p.get("crop_dx", 0), y, w, h]


def stack_layout(n):
    """Band rects (x,y,w,h) on 1080x1920 + caption bottom for the dark caption band."""
    if n == 2:
        return [(0, 150, 1080, 700), (0, 1110, 1080, 700)], 1085  # caption band y 850-1110
    if n == 3:
        # caption band = dark gap y 580-830 between band 1 and 2 (block bottom 815); band 3 face stays above IG's UI
        return [(0, 100, 1080, 480), (0, 830, 1080, 480), (0, 1320, 1080, 480)], 815
    raise SystemExit("stack supports 2 or 3 people")


def cmd_render(a):
    fx = jload(a.faces)
    W, H = fx["frame_size"]
    people = {p["name"]: p for p in fx["people"]}
    shots = jload(a.shots)["shots"]
    fps = a.fps
    g, labels = [], []
    n = len(shots)
    g.append(f"[0:v]fps={fps},split={n}" + "".join(f"[s{i}]" for i in range(n)))
    for i, sh in enumerate(shots):
        # Frame-exact cuts: trim by frame number so the cut lands on the same frame Remotion's
        # captions.bottomRanges (byFrame) uses. Time-based trim can round a cut 1 frame early/late,
        # which leaves a caption at the wrong height (on a face) for one frame at each layout cut.
        f0, f1 = round(sh["start"] * fps), round(sh["end"] * fps)
        sh["start_frame"], sh["end_frame"] = f0, f1
        sh["cut_in_s"], sh["cut_out_s"] = round(f0 / fps, 4), round(f1 / fps, 4)
        tr = f"trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS"
        who = sh["who"]
        if sh["type"] in ("single", "reaction"):
            x, y, cw, ch = single_crop(render_box(people[who]), W, H, a.crop_h, a.face_y)
            sh["crop"] = [x, y, cw, ch]
            g.append(f"[s{i}]{tr},crop={cw}:{ch}:{x}:{y},scale={TW}:{TH}:flags=lanczos,setsar=1,format=yuv420p[v{i}]")
        else:
            rects, cap_bottom = stack_layout(len(who))
            sh["caption_bottom"] = cap_bottom
            sh["bands"] = []
            g.append(f"[s{i}]{tr},split={len(who)}" + "".join(f"[s{i}b{k}]" for k in range(len(who))))
            g.append(f"color=c={BG}:s={TW}x{TH}:r={fps}:d={(f1 - f0) / fps:.4f}[bg{i}]")
            cur = f"bg{i}"
            for k, nm in enumerate(who):
                rx, ry, rw, rh = rects[k]
                x, y, cw, ch = band_crop(render_box(people[nm]), W, H, rw, rh, people[nm].get("band_zoom", a.band_zoom))
                sh["bands"].append({"who": nm, "rect": [rx, ry, rw, rh], "crop": [x, y, cw, ch]})
                g.append(f"[s{i}b{k}]crop={cw}:{ch}:{x}:{y},scale={rw}:{rh}:flags=lanczos,setsar=1[s{i}p{k}]")
                g.append(f"[{cur}][s{i}p{k}]overlay={rx}:{ry}:shortest=1[s{i}o{k}]")
                cur = f"s{i}o{k}"
            g.append(f"[{cur}]format=yuv420p,setsar=1[v{i}]")
        labels.append(f"[v{i}]")
    g.append("".join(labels) + f"concat=n={n}:v=1:a=0[out]")
    fc = os.path.splitext(a.out)[0] + ".filter.txt"
    with open(fc, "w", encoding="utf-8") as f:
        f.write(";\n".join(g))
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.video, "-/filter_complex", fc, "-map", "[out]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-color_range", "tv",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", a.out]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)
    jsave(os.path.splitext(a.out)[0] + ".render.json", {"shots": shots, "crop_h": a.crop_h, "face_y": a.face_y,
                                                        "band_zoom": a.band_zoom})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("faces"); p.add_argument("video"); p.add_argument("--start", type=float, default=0)
    p.add_argument("--end", type=float, required=True); p.add_argument("--step", type=float, default=0.25)
    p.add_argument("--gap", type=float, default=0.12); p.add_argument("--names", default="")
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_faces)
    p = sub.add_parser("activity"); p.add_argument("video"); p.add_argument("--faces", required=True)
    p.add_argument("--captions", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_activity)
    p = sub.add_parser("plan"); p.add_argument("--speakers", required=True); p.add_argument("--hints", default="")
    p.add_argument("--duration", type=float, required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("render"); p.add_argument("video"); p.add_argument("--faces", required=True)
    p.add_argument("--shots", required=True); p.add_argument("--out", required=True)
    p.add_argument("--fps", type=float, default=30); p.add_argument("--crop-h", type=int, default=960)
    p.add_argument("--face-y", type=int, default=640); p.add_argument("--band-zoom", type=float, default=1.5)
    p.set_defaults(fn=cmd_render)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
