#!/usr/bin/env python3
"""Opt-in per-speaker 9:16 reframing for multi-person shots.

Used only when render.py is passed --speaker-track. Default render path is unchanged.
Uses OpenCV Haar (frontal + profile) and existing transcript speaker labels.
MediaPipe is not imported or installed here.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


HOLD_MIN = 1.5
HOLD_MAX = 2.0
IGNORE_MAX = 0.8
CHIN_ANCHOR = 0.85  # fraction of the face box (chin-safe; not a forehead-only anchor)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def crop_box_chin_safe(W, H, tw, th, cx, cy, face_h=None):
    """Crop (x,y,w,h) in source px for target aspect, anchored on the speaker.

    Horizontal: centered on face cx. Vertical: if the source is taller than the
    target aspect, anchor at the chin (cy already passed as the chin-safe point,
    ~0.85 down the face box) rather than a forehead-only 0.4 placement.
    For 16:9 -> 9:16 the crop uses the full source height, so y stays 0.
    """
    ar = tw / th
    if W / H > ar:
        cw, ch = int(round(H * ar)) // 2 * 2, H
        x = min(max(0, cx * W - cw / 2), W - cw)
        y = 0
    else:
        cw, ch = W, int(round(W / ar)) // 2 * 2
        # Place the chin-safe point about 45% down the 9:16 frame so the face
        # sits in the upper-middle and the chest stays clear for captions.
        y = min(max(0, cy * H - ch * 0.45), H - ch)
        x = 0
    return int(x), int(y), int(cw), int(ch)


def _classifiers():
    import cv2
    frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    if frontal.empty():
        raise RuntimeError("haarcascade_frontalface_default.xml missing")
    return cv2, frontal, profile if not profile.empty() else None


def _detect_faces_in_gray(cv2, gray, frontal, profile, w, h):
    min_side = int(min(w, h) * 0.05)
    min_size = (min_side, min_side)
    boxes = []
    for casc, tag in ((frontal, "frontal"),):
        for x, y, fw, fh in casc.detectMultiScale(gray, 1.1, 5, minSize=min_size):
            boxes.append((int(x), int(y), int(fw), int(fh), tag))
    if profile is not None:
        for x, y, fw, fh in profile.detectMultiScale(gray, 1.1, 4, minSize=min_size):
            boxes.append((int(x), int(y), int(fw), int(fh), "profile"))
        flipped = cv2.flip(gray, 1)
        for x, y, fw, fh in profile.detectMultiScale(flipped, 1.1, 4, minSize=min_size):
            boxes.append((int(w - (x + fw)), int(y), int(fw), int(fh), "profile_flip"))
    # Reject obvious low false positives (laps, pillows): faces live in the top 62%.
    kept = []
    for x, y, fw, fh, tag in boxes:
        cx, cy = (x + fw / 2) / w, (y + fh / 2) / h
        if cy > 0.62 or fh < min_side:
            continue
        kept.append((x, y, fw, fh, tag, cx, cy))
    # NMS
    kept.sort(key=lambda b: b[2] * b[3], reverse=True)
    out = []
    for b in kept:
        x, y, fw, fh, tag, cx, cy = b
        overlap = False
        for o in out:
            ox, oy, ofw, ofh = o[0], o[1], o[2], o[3]
            ix = max(0, min(x + fw, ox + ofw) - max(x, ox))
            iy = max(0, min(y + fh, oy + ofh) - max(y, oy))
            inter = ix * iy
            if inter > 0.4 * min(fw * fh, ofw * ofh):
                overlap = True
                break
        if not overlap:
            out.append(b)
    return out


def sample_faces(path, t0, t1, step=0.4):
    """Return [{t, faces:[{x,y,w,h,cx,cy,tag}]}] over [t0, t1]."""
    cv2, frontal, profile = _classifiers()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    samples = []
    t = t0
    # include t1
    while t <= t1 + 1e-6:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
        ok, frame = cap.read()
        if ok:
            h, w = frame.shape[:2]
            W, H = w, h
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = _detect_faces_in_gray(cv2, g, frontal, profile, w, h)
            samples.append({
                "t": t,
                "frame": frame,  # kept for lip-motion; released later
                "faces": [
                    {"x": x, "y": y, "w": fw, "h": fh, "cx": cx, "cy": cy, "tag": tag}
                    for x, y, fw, fh, tag, cx, cy in faces
                ],
            })
        t = round(t + step, 4)
    cap.release()
    return samples, W, H


def cluster_faces(samples, gap=0.12):
    """Stable person clusters by x position. Returns list of {id, cx, cy, fh, count}."""
    pts = []
    for s in samples:
        for f in s["faces"]:
            pts.append(f)
    if not pts:
        return []
    pts = sorted(pts, key=lambda f: f["cx"])
    groups = [[pts[0]]]
    for f in pts[1:]:
        if f["cx"] - statistics.median([g["cx"] for g in groups[-1]]) <= gap:
            groups[-1].append(f)
        else:
            groups.append([f])
    clusters = []
    for i, g in enumerate(groups):
        if len(g) < 2 and len(pts) >= 6:
            # drop one-off ghosts unless we have very few detections overall
            continue
        clusters.append({
            "id": f"F{i+1}",
            "cx": float(statistics.median([f["cx"] for f in g])),
            "cy": float(statistics.median([f["cy"] for f in g])),
            "fh": float(statistics.median([f["h"] for f in g])),
            "fw": float(statistics.median([f["w"] for f in g])),
            "count": len(g),
        })
    clusters.sort(key=lambda c: c["cx"])
    # re-id left-to-right
    for i, c in enumerate(clusters):
        c["id"] = f"F{i+1}"
    return clusters


def _nearest_cluster(cx, clusters):
    if not clusters:
        return None
    return min(clusters, key=lambda c: abs(c["cx"] - cx))


def lip_activity(samples, clusters, t0, t1):
    """Mean mouth-region motion per cluster during [t0, t1]."""
    import cv2
    import numpy as np
    scores = {c["id"]: [] for c in clusters}
    prev = {c["id"]: None for c in clusters}
    for s in samples:
        if s["t"] < t0 - 0.05 or s["t"] > t1 + 0.05:
            continue
        frame = s.get("frame")
        if frame is None:
            continue
        h, w = frame.shape[:2]
        assigned = {}
        for f in s["faces"]:
            c = _nearest_cluster(f["cx"], clusters)
            if c is None or abs(c["cx"] - f["cx"]) > 0.12:
                continue
            # mouth: lower third of the face box
            x, y, fw, fh = f["x"], f["y"], f["w"], f["h"]
            my = y + int(fh * 0.55)
            mh = max(4, int(fh * 0.45))
            mx = x + int(fw * 0.15)
            mw = max(4, int(fw * 0.70))
            x2, y2 = min(w, mx + mw), min(h, my + mh)
            mx, my = max(0, mx), max(0, my)
            if x2 <= mx or y2 <= my:
                continue
            roi = cv2.cvtColor(frame[my:y2, mx:x2], cv2.COLOR_BGR2GRAY)
            roi = cv2.resize(roi, (32, 16), interpolation=cv2.INTER_AREA)
            assigned[c["id"]] = roi
        for cid, roi in assigned.items():
            if prev[cid] is not None:
                scores[cid].append(float(np.mean(cv2.absdiff(prev[cid], roi))))
            prev[cid] = roi
    return {cid: (sum(v) / len(v) if v else 0.0) for cid, v in scores.items()}


def turns_from_words(words, t0, t1, hold_min=HOLD_MIN, ignore_max=IGNORE_MAX):
    """Build held speaker turns in source time.

    - Ignore interjections under ignore_max (0.8 s).
    - Hold at least hold_min (1.5 s) before switching.
    - Never cut away for brief silence alone; fill gaps with the current speaker.
    """
    labeled = [w for w in words if w.get("speaker") and w["end"] > t0 and w["start"] < t1]
    if not labeled:
        return [], "no speaker labels on words"
    labeled.sort(key=lambda w: w["start"])
    raw = []
    cur = {"speaker": str(labeled[0]["speaker"]), "start": max(t0, labeled[0]["start"]), "end": labeled[0]["end"]}
    for w in labeled[1:]:
        sp = str(w["speaker"])
        if sp == cur["speaker"]:
            cur["end"] = max(cur["end"], w["end"])
        else:
            raw.append(cur)
            cur = {"speaker": sp, "start": w["start"], "end": w["end"]}
    raw.append(cur)
    # clip to window and drop tiny interjections
    cleaned = []
    for t in raw:
        s, e = max(t0, t["start"]), min(t1, t["end"])
        if e - s < ignore_max:
            # ignore: do not start a new turn
            if cleaned:
                cleaned[-1]["end"] = max(cleaned[-1]["end"], e)
            continue
        if cleaned and t["speaker"] == cleaned[-1]["speaker"]:
            cleaned[-1]["end"] = e
        else:
            cleaned.append({"speaker": t["speaker"], "start": s, "end": e})
    if not cleaned:
        return [], "all turns were shorter than the 0.8 s ignore threshold"
    # enforce hold before switching: merge a new speaker back if their
    # *sustained* turn is under hold_min
    held = [dict(cleaned[0])]
    for t in cleaned[1:]:
        dur = t["end"] - t["start"]
        if dur < hold_min:
            held[-1]["end"] = t["end"]
            held[-1]["absorbed"] = held[-1].get("absorbed", []) + [t]
        else:
            # start the new turn at the later of its start and hold_min after previous start
            # (stay on current speaker until the new one is sustained)
            held.append(dict(t))
    # fill the window: never cut away for brief silence
    held[0]["start"] = t0
    held[-1]["end"] = t1
    for a, b in zip(held, held[1:]):
        a["end"] = b["start"]
    for t in held:
        t["start"] = round(t["start"], 3)
        t["end"] = round(t["end"], 3)
        t.pop("absorbed", None)
    return held, None


def auto_match(samples, clusters, turns):
    """Auto-match speaker labels to face clusters via lip-motion. Unique assignment."""
    if not clusters:
        return {}, ["no face clusters — OpenCV missed faces (MediaPipe is the fallback, not installed)"]
    speakers = []
    for t in turns:
        if t["speaker"] not in speakers:
            speakers.append(t["speaker"])
    # score each speaker against each cluster
    table = {}
    for sp in speakers:
        # union of that speaker's turns
        spans = [(t["start"], t["end"]) for t in turns if t["speaker"] == sp]
        scores = defaultdict(float)
        weights = defaultdict(float)
        for s0, s1 in spans:
            act = lip_activity(samples, clusters, s0, s1)
            dur = max(0.001, s1 - s0)
            for cid, v in act.items():
                scores[cid] += v * dur
                weights[cid] += dur
        table[sp] = {cid: (scores[cid] / weights[cid] if weights[cid] else 0.0) for cid in [c["id"] for c in clusters]}
    # greedy unique assignment by best remaining score
    mapping = {}
    notes = []
    remaining = {c["id"]: c for c in clusters}
    order = sorted(speakers, key=lambda sp: max(table[sp].values() or [0]), reverse=True)
    for sp in order:
        if not remaining:
            notes.append(f"{sp}: no remaining face cluster")
            continue
        cid = max(remaining, key=lambda k: table[sp].get(k, 0.0))
        mapping[sp] = remaining.pop(cid)
        mapping[sp] = dict(mapping[sp])  # copy
        sc = table[sp].get(cid, 0.0)
        mapping[sp]["match_score"] = round(sc, 3)
        mapping[sp]["confidence"] = "high" if sc >= 2.0 else ("medium" if sc >= 0.8 else "low")
        if mapping[sp]["confidence"] == "low":
            notes.append(f"{sp} -> {cid} low-confidence lip-match (score {sc:.2f}); fix by hand")
    return mapping, notes


def plan(path, t0, t1, words, tw, th, hold_min=HOLD_MIN, ignore_max=IGNORE_MAX, step=0.4):
    """Build an opt-in speaker-crop plan for [t0, t1] on path."""
    samples, W, H = sample_faces(path, t0, t1, step=step)
    clusters = cluster_faces(samples)
    turns, turn_note = turns_from_words(words, t0, t1, hold_min, ignore_max)
    notes = []
    if turn_note:
        notes.append(turn_note)
    if not turns:
        # follow whoever is moving their mouth, no speaker labels
        notes.append("no usable speaker turns; falling back to lip-activity follow (no speaker bias)")
        # one window: pick most active cluster, stay there (no brief-silence cuts)
        act = lip_activity(samples, clusters, t0, t1)
        if clusters:
            cid = max(act, key=lambda k: act[k]) if act else clusters[0]["id"]
            c = next(c for c in clusters if c["id"] == cid)
            turns = [{"speaker": cid, "start": t0, "end": t1}]
            mapping = {cid: dict(c, match_score=round(act.get(cid, 0.0), 3), confidence="medium")}
        else:
            mapping = {}
    else:
        mapping, mnotes = auto_match(samples, clusters, turns)
        notes.extend(mnotes)

    crops = []
    for t in turns:
        sp = t["speaker"]
        face = mapping.get(sp)
        if face:
            cx, cy_face, fh = face["cx"], face["cy"], face["fh"]
            # chin-safe point: 0.85 down the face box (cy is face center ~0.5)
            cy_chin = cy_face + (CHIN_ANCHOR - 0.5) * (fh / H)
            box = crop_box_chin_safe(W, H, tw, th, cx, cy_chin, fh)
            conf = face.get("confidence", "medium")
        else:
            cx, cy_chin, box, conf = 0.5, 0.5, crop_box_chin_safe(W, H, tw, th, 0.5, 0.5), "missing"
            notes.append(f"{sp}: no matched face, using center crop")
        crops.append({
            "start": t["start"], "end": t["end"], "speaker": sp,
            "cx": round(cx, 4), "cy": round(cy_chin, 4),
            "box": box, "confidence": conf,
        })

    # drop raw frames so the plan is JSON-serializable
    for s in samples:
        s.pop("frame", None)

    return {
        "source": os.path.abspath(path),
        "window": [t0, t1],
        "frame_size": [W, H],
        "clusters": clusters,
        "turns": turns,
        "match": {sp: {k: v for k, v in face.items() if k != "frame"} for sp, face in mapping.items()},
        "crops": crops,
        "notes": notes,
        "rules": {
            "hold_s": [HOLD_MIN, HOLD_MAX],
            "ignore_under_s": IGNORE_MAX,
            "cut_vs_pan": "hard cut on a speaker change; short pan only if the next face is already in frame",
            "follow": "whoever is speaking, no speaker bias",
            "opt_in": True,
        },
    }


def release_samples(samples):
    for s in samples:
        s.pop("frame", None)
