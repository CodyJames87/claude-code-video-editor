#!/usr/bin/env python3
"""Loose vs tight 9:16 framing previews, BEFORE a render, so you can pick per key moment.

  python helpers/crop_previews.py public/media/<src>.mp4 --times 0.5,2.9,9.0,17.6 [--focus 0.52,0.5]
         [--props props/<name>.json] [--panel x,y,w,h] [--frame 1080x1920] [--scales 1.16,1.12,1.10,1.08]
         [--out out/crop-previews/<name>]

For each time: LOOSE = the wide base frame (scale 1.00: the source cover-fit into the video panel at --focus) and
TIGHT = the biggest scale from --scales (standard 1.16 first, then 1.12 / 1.10 / 1.08) that keeps the WHOLE head
inside the panel, using face_safe.py's own margins (CAP_UP above the Haar box for the cap, CHIN_DOWN below for the
chin/beard, SIDE each side). The tight crop scales about the head centre (Camera.tsx semantics), and the JSON gives
the PunchIn props for it. If no tight scale is legal, TIGHT is marked UNSAFE and only the loose still is offered
(no illegal still is drawn). If even the loose base clips the cap or chin, LOOSE is marked UNSAFE too (loosen the
layout: Solo Frame band, or a different focus). Already-tight bases (head > 45 % of the panel height) are capped at
1.12 per CLAUDE.md "Zoom & punch style". If the detector finds no face at a time: UNSURE, nothing is proposed.
--props pulls the layout (Solo Frame topBand / cropTop), focus, and default times (hook 0.5 s, every punch/push
peak, mid, end). Times are on the edit timeline (props trim applied); stills come from the SOURCE.
Outputs: strip.jpg (rows = moments, loose | tight, labelled), <t>_loose.png / <t>_tight.png full-res frames,
crop_previews.json (per moment: face, head box, verdicts, proposed scale + PunchIn props). Nothing is rendered or
written to props: you pick, then the pick goes into props by hand.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import face_safe as fs  # noqa: E402  (exits with a message if OpenCV is missing)
import props_util as pu  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

INK = (33, 33, 33)
ORANGE = (255, 87, 34)
NEUTRAL = (89, 89, 89)
TIGHT_BASE = 0.45  # head height / panel height above this = an already-tight base (cap the punch at 1.12)


def font(sz):
    for f in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def grab(src, t, path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", path], check=True)
    return Image.open(path).convert("RGB")


def render(img, frame_wh, panel, vis_top, focus, scale, origin, band_color=INK):
    """Compose the output frame: band canvas + the cover-fit video panel with the camera scale, clipped at vis_top."""
    FW, FH = frame_wh
    px, py, pw, ph = panel
    sw, sh = img.size
    s = max(pw / sw, ph / sh)
    base = img.resize((round(sw * s), round(sh * s)), Image.LANCZOS)
    ox, oy = (pw - base.width) * focus[0], (ph - base.height) * focus[1]
    pan = Image.new("RGB", (int(pw), int(ph)), band_color)
    pan.paste(base, (round(ox), round(oy)))
    if scale != 1.0:
        cx, cy = origin[0] * pw, origin[1] * ph
        box = (cx - cx / scale, cy - cy / scale, cx + (pw - cx) / scale, cy + (ph - cy) / scale)
        pan = pan.crop(tuple(round(v) for v in box)).resize((int(pw), int(ph)), Image.LANCZOS)
    out = Image.new("RGB", (FW, FH), band_color)
    out.paste(pan, (int(px), int(py)))
    if vis_top > py:  # the band covers the panel's top edge (cropTop)
        ImageDraw.Draw(out).rectangle([0, 0, FW, vis_top - 1], fill=band_color)
    return out


def legal(head, panel, vis_top):
    x, y, w, h = head
    px, py, pw, ph = panel
    issues = []
    if y < vis_top:
        issues.append(f"cap clipped by {vis_top - y:.0f}px")
    if y + h > py + ph:
        issues.append(f"chin clipped by {y + h - py - ph:.0f}px")
    return issues


def side_note(head, panel):
    x, _, w, _ = head
    return "ear/headphone margin touches a side edge (note only)" if x < panel[0] or x + w > panel[0] + panel[2] else None


def main():
    ap = argparse.ArgumentParser(description="Loose vs tight 9:16 framing previews (see docstring).")
    ap.add_argument("video")
    ap.add_argument("--times")
    ap.add_argument("--focus")
    ap.add_argument("--props")
    ap.add_argument("--panel", help="x,y,w,h of the video panel (default: whole frame, or the props Solo Frame panel)")
    ap.add_argument("--frame", default="1080x1920")
    ap.add_argument("--scales", default="1.16,1.12,1.10,1.08")
    ap.add_argument("--out")
    a = ap.parse_args()
    FW, FH = [int(v) for v in a.frame.lower().split("x")]
    props = pu.load_props(a.props) if a.props else None
    trim0 = pu.trim_start(props) if props else 0.0
    focus = [float(v) for v in a.focus.split(",")] if a.focus else \
        [float((props or {}).get("focus", {}).get("x", 0.5)), float((props or {}).get("focus", {}).get("y", 0.4))]
    lay = (props or {}).get("layout") or {}
    band, crop = float(lay.get("topBand") or 0) * FH / 1920, float(lay.get("cropTop") or 0) * FH / 1920
    if a.panel:
        panel = [float(v) for v in a.panel.split(",")]
        vis_top = panel[1]
    else:
        panel = [0.0, band - crop if band else 0.0, float(FW), FH - (band - crop if band else 0.0)]
        vis_top = band
    if a.times:
        times = [float(v) for v in a.times.split(",") if v.strip()]
    elif props:
        caps = pu.load_captions(props.get("transcriptJson"))
        ovs = pu.resolved_overlays(props, caps)
        end = (caps[-1]["endMs"] / 1000 - trim0) if caps else 10
        times = sorted(set([0.5] + [e["peak"] for e in pu.camera_events(ovs)] + [round(end / 2, 2), round(end - 0.5, 2)]))
    else:
        raise SystemExit("give --times or --props")
    scales = sorted([float(v) for v in a.scales.split(",")], reverse=True)
    name = os.path.splitext(os.path.basename(a.video))[0]
    od = a.out or os.path.join(pu.ROOT, "out", "crop-previews", name)
    os.makedirs(od, exist_ok=True)

    samples, src_wh = fs.detect_at(a.video, [t + trim0 for t in times], max_hold=0.5)
    moments, rows = [], []
    f_big, f_small = font(34), font(24)
    for t, smp in zip(times, samples):
        tag = f"{t:06.2f}s"
        img = grab(a.video, t + trim0, os.path.join(od, f"_src_{tag}.png"))
        m = {"t": t, "source_t": round(t + trim0, 3), "focus": focus, "panel": panel, "face": smp["face"], "held": smp["held"]}
        if not smp["face"]:
            m.update({"verdict": "UNSURE", "reason": "no face detected: nothing proposed (look at the source frame)"})
            loose = render(img, (FW, FH), panel, vis_top, focus, 1.0, (0.5, 0.35))
            loose.save(os.path.join(od, f"{tag}_loose.png"))
            rows.append((t, loose, "LOOSE 1.00  (face UNSURE)", None, "TIGHT: not offered (no face found)"))
            moments.append(m)
            continue
        head_src = fs.head_from_face(smp["face"])
        base_map = fs.mapper(src_wh, panel, focus)
        head0 = base_map(head_src)
        loose_issues = legal(head0, panel, vis_top)
        m["side_note"] = side_note(head0, panel)
        hc = ((head0[0] + head0[2] / 2 - panel[0]) / panel[2], (head0[1] + head0[3] / 2 - panel[1]) / panel[3])
        origin = (round(min(1, max(0, hc[0])), 3), round(min(1, max(0, hc[1])), 3))
        tight_base = head0[3] / (panel[3] - (vis_top - panel[1])) > TIGHT_BASE
        cap = 1.12 if tight_base else max(scales)
        pick, tried = None, []
        for s in scales:
            if s > cap + 1e-6:
                continue
            hs = fs.mapper(src_wh, panel, focus, s, origin)(head_src)
            iss = legal(hs, panel, vis_top)
            tried.append({"scale": s, "issues": iss})
            if not iss:
                pick = (s, hs)
                break
        m.update({"head_base": [round(v) for v in head0], "loose": {"scale": 1.0, "verdict": "UNSAFE" if loose_issues else "SAFE",
                  "issues": loose_issues}, "tight_base": tight_base, "tight_tried": tried})
        loose = render(img, (FW, FH), panel, vis_top, focus, 1.0, origin)
        d = ImageDraw.Draw(loose)
        d.rectangle([head0[0], head0[1], head0[0] + head0[2], head0[1] + head0[3]], outline=(66, 165, 245), width=3)
        loose.save(os.path.join(od, f"{tag}_loose.png"))
        llab = f"LOOSE 1.00" + ("  UNSAFE: " + ", ".join(loose_issues) if loose_issues else "  SAFE")
        if pick and not loose_issues:
            s, hs = pick
            tight = render(img, (FW, FH), panel, vis_top, focus, s, origin)
            ImageDraw.Draw(tight).rectangle([hs[0], hs[1], hs[0] + hs[2], hs[1] + hs[3]], outline=(66, 165, 245), width=3)
            tight.save(os.path.join(od, f"{tag}_tight.png"))
            m["tight"] = {"scale": s, "verdict": "SAFE", "origin": origin, "head": [round(v) for v in hs],
                          "punchin_props": {"to": s, "inFrames": 1, "outFrames": 1, "x": origin[0], "y": origin[1]},
                          "note": "capped at 1.12 (already-tight base)" if tight_base else None}
            tlab = f"TIGHT {s:.2f} @ x {origin[0]:.2f} y {origin[1]:.2f}  SAFE"
            rows.append((t, loose, llab, tight, tlab))
        else:
            why = "loose base already clips the head" if loose_issues else \
                f"every scale clips the head (at {tried[-1]['scale']:.2f}: {', '.join(tried[-1]['issues'])})" if tried else "no scale allowed"
            m["tight"] = {"verdict": "UNSAFE", "reason": why}
            rows.append((t, loose, llab, None, f"TIGHT UNSAFE: not offered ({why})"))
        m["verdict"] = "OK" if not loose_issues else "LOOSE UNSAFE"
        moments.append(m)

    # contact strip: one row per moment, loose | tight
    TW = 300
    TH = round(TW * FH / FW)
    LAB = 92
    strip = Image.new("RGB", (TW * 2 + 3 * 12 + 150, len(rows) * (TH + LAB + 12) + 12), (255, 255, 255))
    d = ImageDraw.Draw(strip)
    for i, (t, li, ll, ti, tl) in enumerate(rows):
        y = 12 + i * (TH + LAB + 12)
        d.text((12, y + TH // 2 - 20), f"{t:.2f}s", fill=INK, font=f_big)
        for j, (im, lab) in enumerate(((li, ll), (ti, tl))):
            x = 150 + j * (TW + 12)
            if im is not None:
                strip.paste(im.resize((TW, TH), Image.LANCZOS), (x, y))
            else:
                d.rectangle([x, y, x + TW, y + TH], fill=(229, 229, 229))
                d.text((x + 20, y + TH // 2 - 14), "not offered", fill=NEUTRAL, font=f_big)
            col = ORANGE if "UNSAFE" in lab or "UNSURE" in lab else INK
            words, line, ly = lab.split(), "", y + TH + 6
            for w in words:  # wrap the label to the tile width
                if d.textlength(line + " " + w, font=f_small) > TW and line:
                    d.text((x, ly), line, fill=col, font=f_small)
                    ly += 26
                    line = w
                else:
                    line = (line + " " + w).strip()
            d.text((x, ly), line, fill=col, font=f_small)
    strip.save(os.path.join(od, "strip.jpg"), quality=90)
    for f in os.listdir(od):
        if f.startswith("_src_"):
            os.remove(os.path.join(od, f))
    res = {"video": os.path.abspath(a.video), "props": os.path.abspath(a.props) if a.props else None, "frame": [FW, FH],
           "panel": panel, "visible_top": vis_top, "focus": focus, "margins": {"CAP_UP": fs.CAP_UP, "CHIN_DOWN": fs.CHIN_DOWN, "SIDE": fs.SIDE},
           "scales_tried": scales, "moments": moments,
           "next": "Pick loose or tight per moment; copy the chosen punchin_props into props by hand. Nothing was rendered."}
    pu.save_json(res, os.path.join(od, "crop_previews.json"))
    for m in moments:
        tt = m.get("tight", {})
        print(f"{m['t']:7.2f}s  loose {m.get('loose', {}).get('verdict', m.get('verdict'))}  tight "
              + (f"{tt['scale']:.2f} SAFE {tt['punchin_props']}" if tt.get("verdict") == "SAFE" else tt.get("verdict", "UNSURE") + " " + tt.get("reason", m.get("reason", ""))))
    print(f"strip: {os.path.join(od, 'strip.jpg')}\njson:  {os.path.join(od, 'crop_previews.json')}")


if __name__ == "__main__":
    main()
