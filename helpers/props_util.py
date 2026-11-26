#!/usr/bin/env python3
"""Shared props / timeline helpers for the editor tools (qa_gate.py, remap_edl.py, crop_previews.py, review_page.py).

Mirrors the Remotion side exactly where it matters:
  - word anchors resolve like src/types.ts resolveOverlays (same norm(), first occurrence by default, offset added,
    times relative to the trimmed timeline = caption startMs/1000 - trim.start);
  - captions JSON = Remotion Caption[] in SOURCE milliseconds (or {"captions": [...]});
  - layout geometry (Solo Frame band, Split Frame bands, caption block) from src/components (design px on 1080x1920).
Text boxes are APPROXIMATE (fonts wrap differently per line); they are for gates and QC hints, not pixel truth.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")
FPS = 30

# Geometry constants copied from src/components (design px on 1080x1920). Keep in sync if those files change.
BAR_Y = 226            # motion/design.ts
SLOT_Y = 324           # motion/design.ts
SPLIT = {"graphicTop": 258, "graphicH": 600, "videoTopWhenBottom": 1150, "videoTopWhenTop": 258, "videoH": 608, "captionBottom": 1068}
CAPTION_FS = 84        # Captions.tsx lowerThird on 9:16 (lineHeight 1.08, two lines)
CAPTION_BOTTOM = 1150  # Captions.tsx default block bottom on 9:16

# overlays that hide the video entirely while they're up (no face expected on screen)
VIDEO_HIDDEN = {"TakeoverFrame", "FullScreenList", "ComparisonCard", "ProcessFlow"}
CAMERA = {"PushIn", "PunchIn"}


def norm(s):
    return re.sub(r"[^a-z0-9$%']", "", str(s).lower())


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, p):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def public_path(rel):
    """props paths are relative to public/ (e.g. media/x.mp4)."""
    if not rel or re.match(r"^(https?:|blob:|data:)", rel):
        return rel
    rel = re.sub(r"^/?public[\\/]", "", rel)
    return os.path.join(PUBLIC, rel)


def load_captions(path_or_list):
    if isinstance(path_or_list, list):
        return path_or_list
    if not path_or_list:
        return []
    p = path_or_list if os.path.exists(path_or_list) else public_path(path_or_list)
    data = load_json(p)
    caps = data if isinstance(data, list) else data.get("captions") or data.get("words") or []
    out = []
    for c in caps:  # accept Remotion Caption or {text,start,end} seconds
        if "startMs" in c:
            out.append(dict(c))
        elif "start" in c:
            out.append({"text": c.get("text") or c.get("word", ""), "startMs": float(c["start"]) * 1000,
                        "endMs": float(c["end"]) * 1000, "timestampMs": None, "confidence": c.get("confidence", 1)})
    return out


def load_props(path):
    p = load_json(path)
    p["_path"] = os.path.abspath(path)
    return p


def trim_start(props):
    t = props.get("trim") or {}
    return float(t.get("start") or 0)


def resolve_anchor(at, caps, trim0=0.0):
    """-> (seconds on the trimmed timeline or None, word index or None). Same rules as src/types.ts."""
    if isinstance(at, (int, float)):
        return float(at), None
    target = [norm(t) for t in str(at.get("word", "")).split() if norm(t)]
    words = [norm(c["text"]) for c in caps]
    seen = 0
    want = at.get("occurrence", 1) or 1
    for i in range(len(words)):
        if target and all(i + k < len(words) and words[i + k] == t for k, t in enumerate(target)):
            seen += 1
            if seen == want:
                return caps[i]["startMs"] / 1000 - trim0 + float(at.get("offset", 0) or 0), i
    return None, None


def resolved_overlays(props, caps=None):
    caps = caps if caps is not None else load_captions(props.get("transcriptJson"))
    t0 = trim_start(props)
    out = []
    for i, o in enumerate(props.get("overlays") or []):
        s, wi = resolve_anchor(o.get("at", 0), caps, t0)
        out.append({**o, "_i": i, "start": s, "end": None if s is None else s + float(o.get("duration", 0)),
                    "_word_index": wi, "_missing": s is None})
    return out


def timeline_duration(props, caps, media_dur=None):
    t0 = trim_start(props)
    tr = props.get("trim") or {}
    if media_dur is not None:
        end = tr.get("end") or media_dur
        return end - t0 + float(props.get("tailHoldSec") or 0)
    return (caps[-1]["endMs"] / 1000 - t0) if caps else 0


def camera_events(ovs):
    """Punch / push windows + their peak sample times (timeline s)."""
    ev = []
    for o in ovs:
        if o["type"] not in CAMERA or o["_missing"]:
            continue
        p = o.get("props", {})
        if o["type"] == "PunchIn":
            inf = p.get("inFrames", 4)
            peak = o["start"] + (inf + 1) / FPS
            to = p.get("to", 1.16)
        else:
            peak = o["end"] - 1 / FPS
            to = p.get("to") or (1 + 0.048 * o["duration"] if p.get("style") == "crawl" else 1.08)
        ev.append({"type": o["type"], "start": o["start"], "end": o["end"], "peak": round(peak, 3), "to": to,
                   "x": p.get("x", 0.5), "y": p.get("y", 0.35), "label": f"{o['type']} {to}"})
    return ev


def active(ovs, t, types=None):
    return [o for o in ovs if not o["_missing"] and o["start"] <= t < o["end"] and (types is None or o["type"] in types)]


def panel_at(props, ovs, t, H=1920):
    """Video panel [x, y, w, h] in design px at timeline t (Solo Frame band / Split band), or None if video is hidden."""
    if active(ovs, t, VIDEO_HIDDEN):
        return None
    sp = active(ovs, t, {"SplitFrame"})
    if sp:
        band = sp[0].get("props", {}).get("videoBand", "bottom")
        top = SPLIT["videoTopWhenBottom"] if band == "bottom" else SPLIT["videoTopWhenTop"]
        return [0, top, 1080, SPLIT["videoH"]]
    lay = props.get("layout") or {}
    band = float(lay.get("topBand") or 0)
    return [0, band, 1080, H - band]


def caption_bottom_at(props, ovs, t):
    sp = active(ovs, t, {"SplitFrame"})
    if sp:
        return float(sp[0].get("props", {}).get("captionBottom", SPLIT["captionBottom"]))
    cc = props.get("captions") or {}
    for r in cc.get("bottomRanges") or []:
        if r["from"] <= t < r["to"]:
            return float(r["bottom"])
    return float(CAPTION_BOTTOM)


def caption_visible(props, ovs, caps, t):
    cc = props.get("captions") or {}
    if cc.get("enabled") is False:
        return False
    if any(o.get("hideCaptions", o["type"] in {"ComparisonCard", "ProcessFlow", "FullScreenList"}) for o in active(ovs, t)):
        return False
    t0 = trim_start(props)
    # Captions.tsx (lowerThird/karaoke): a line shows from its first word and holds until the next line starts,
    # at most +350 ms after its last word. Approximation: on screen during a word, up to 0.35 s after it, and across
    # short (< 0.5 s) gaps inside a phrase.
    ws = [(c["startMs"] / 1000 - t0, c["endMs"] / 1000 - t0) for c in caps]
    for i, (s, e) in enumerate(ws):
        if s - 0.03 <= t <= e + 0.35:
            return True
        if i + 1 < len(ws) and e < t < ws[i + 1][0] and ws[i + 1][0] - e < 0.5:
            return True
    return False


def text_boxes_at(props, ovs, caps, t):
    """Approximate text / graphic boxes [x, y, w, h] (design px) on screen at timeline t: [(name, box), ...]."""
    boxes = []
    cc = props.get("captions") or {}
    one = any(r["from"] <= t < r["to"] for r in cc.get("oneLineRanges") or [])
    if caption_visible(props, ovs, caps, t):
        b = caption_bottom_at(props, ovs, t)
        # glyph extents: Anton caps sit inside the 1.08 line box; measured on a render, two lines put the glyph top
        # ~178 px above the block bottom (1690 -> ~1515). Keep the box on the glyphs, not the leading.
        h = CAPTION_FS * 1.08 * (1 if one else 2) - 4
        boxes.append(("captions", [110, b - h, 860, h]))
    hook = props.get("hook")
    if hook and t < float(hook.get("duration", 2.0)):
        if hook.get("position", "top") == "lower":
            b = float(hook.get("bottom") or 1150)
            boxes.append(("hook", [90, b - 330, 900, 330]))
        else:
            boxes.append(("hook", [90, 300, 900, 330]))
    pb = props.get("progressBar")
    if pb and pb.get("enabled", True):
        y = 1920 - float(pb.get("y") or 120) if pb.get("position") == "bottom" else float(pb.get("y") or BAR_Y)
        ins = float(pb.get("inset", 60))
        boxes.append(("progressBar", [ins, y, 1080 - 2 * ins, float(pb.get("height", 7))]))
    for o in active(ovs, t):
        p, ty = o.get("props", {}), o["type"]
        if ty == "CalloutChip" and p.get("box"):
            boxes.append((f"CalloutChip#{o['_i']}", [float(v) for v in p["box"]]))
        elif ty == "TitleBanner":
            fs = float(p.get("fontSize", 60))
            lines = max(1, -(-len(p.get("text", "")) * fs * 0.55 // 940))
            boxes.append((f"TitleBanner#{o['_i']}", [60, float(p.get("y", SLOT_Y)) - fs * 0.6, 960, lines * fs * 1.15 + fs * 0.6]))
        elif ty == "CountUpCard":
            ns = float(p.get("numberSize", 96))
            boxes.append((f"CountUpCard#{o['_i']}", [140, float(p.get("y", SLOT_Y)) - ns * 0.75, 800, ns * 1.5]))
        elif ty == "StatementCard":
            pos = p.get("position", "center")
            y = {"top": 230, "center": 700, "lower": 900, "full": 0}.get(pos, 700)
            boxes.append((f"StatementCard#{o['_i']}", [90, y, 900, 1920 if pos == "full" else 520]))
        elif ty == "PillList":
            pos = p.get("position", "center")
            y = {"top": 300, "center": 860, "bottom": 1150}.get(pos, 860)
            boxes.append((f"PillList#{o['_i']}", [90, y, 900, 200]))
        elif ty == "SplitFrame":
            band = p.get("videoBand", "bottom")
            gt = SPLIT["graphicTop"] if band == "bottom" else SPLIT["videoTopWhenTop"] + SPLIT["videoH"] + 250
            boxes.append((f"SplitFrame-graphic#{o['_i']}", [60, gt, 960, SPLIT["graphicH"]]))
    return boxes


def allowed_still_ranges(props, ovs, final_dur=None):
    """Windows where a frozen picture is intentional: Takeover Frame / full-screen cards, the tailHoldSec end hold
    (the last tailHoldSec of the final)."""
    rng = []
    for o in ovs:
        if not o["_missing"] and o["type"] in VIDEO_HIDDEN | {"StatementCard"}:
            rng.append((o["start"], o["end"], o["type"]))
    th = float(props.get("tailHoldSec") or 0)
    if th and final_dur:
        rng.append((final_dur - th - 0.15, final_dur + 0.1, "tailHoldSec"))
    return rng
