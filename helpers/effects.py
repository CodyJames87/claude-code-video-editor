#!/usr/bin/env python3
"""Effects toolbox: speed_ramp, zoom_to_detail (punch-in), spotlight (dim all but a region).

Library use (render.py imports these):
  speed_pieces(pieces, ramps, fps)          -> pieces split with eased speed steps
  zoom_filter(zooms, W, H, fps)             -> zoompan filter string (or None)
  make_spotlight_mask(path, W, H, spot)     -> writes feathered ellipse mask PNG
  spotlight_chain(inp, mask, out, spot)     -> filter_complex snippet
Standalone (apply one effect to a whole clip, times in clip seconds, x/y/w/h as 0-1 fractions):
  python scripts/effects.py zoom_to_detail IN OUT --start 2 --end 4 --x 0.5 --y 0.4 --zoom 2
  python scripts/effects.py spotlight IN OUT --start 2 --end 5 --x 0.5 --y 0.5 --w 0.3 --h 0.2
  python scripts/effects.py speed_ramp IN OUT --start 2 --end 6 --speed 4 [--audio tempo|mute]
"""
import argparse, math, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu


def _snap(t, fps):
    return round(round(t * fps) / fps, 6)


# ---------------------------------------------------------------- speed ramp
def speed_pieces(pieces, ramps, fps=30.0, steps=4):
    """pieces: [{start,end,speed,mute}] in source seconds. ramps: [{start,end,speed,ease,audio}].
    Returns new piece list where ramp ranges become eased steps 1 -> speed -> 1."""
    out = [dict(p) for p in pieces]
    for r in ramps:
        F = float(r.get("speed", 3.0))
        s, e = float(r["start"]), float(r["end"])
        E = min(float(r.get("ease", 0.4)), (e - s) / 2.0)
        mute = r.get("audio", "mute") == "mute"
        # sub-ranges with speeds
        subs = []
        if E > 0:
            for i in range(steps):
                a, b = s + E * i / steps, s + E * (i + 1) / steps
                k = (i + 0.5) / steps; k = k * k * (3 - 2 * k)
                subs.append((a, b, 1 + (F - 1) * k))
        subs.append((s + E, e - E, F))
        if E > 0:
            for i in range(steps):
                a, b = e - E + E * i / steps, e - E + E * (i + 1) / steps
                k = 1 - (i + 0.5) / steps; k = k * k * (3 - 2 * k)
                subs.append((a, b, 1 + (F - 1) * k))
        subs = [(_snap(a, fps), _snap(b, fps), sp) for a, b, sp in subs]
        subs = [x for x in subs if x[1] - x[0] >= 1.0 / fps]
        new = []
        for p in out:
            if p["end"] <= s or p["start"] >= e or p.get("speed", 1) != 1:
                new.append(p); continue
            cur = p["start"]
            if cur < s:
                new.append({**p, "end": _snap(s, fps)}); cur = _snap(s, fps)
            for a, b, sp in subs:
                a2, b2 = max(a, cur, p["start"]), min(b, p["end"])
                if b2 - a2 >= 1.0 / fps:
                    new.append({"start": a2, "end": b2, "speed": round(sp, 3), "mute": mute, "ramp": True})
                    cur = b2
            if cur < p["end"] - 1.0 / fps:
                new.append({**p, "start": max(cur, _snap(e, fps)) if p["end"] > e else cur})
        out = [p for p in new if p["end"] - p["start"] >= 1.0 / fps]
    return out


def atempo_chain(speed):
    """atempo factors (each within 0.5..2.0) whose product is speed."""
    f, parts = float(speed), []
    while f > 2.0:
        parts.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5"); f /= 0.5
    if abs(f - 1.0) > 1e-3:
        parts.append(f"atempo={f:.5f}")
    return ",".join(parts)


# ---------------------------------------------------------------- zoom to detail
def zoom_filter(zooms, W, H, fps):
    """zooms: [{start,end (output s), x,y (output px center), zoom, ease}] -> zoompan string."""
    if not zooms:
        return None
    zt, xt, yt = [], [], []
    for z in zooms:
        s, e, Z = float(z["start"]), float(z["end"]), float(z.get("zoom", 1.8))
        r = max(0.04, float(z.get("ease", 0.3)))
        k = f"min(clip((it-{s:.3f})/{r:.3f},0,1),clip(({e:.3f}-it)/{r:.3f},0,1))"
        ez = f"(({k})*({k})*(3-2*({k})))"
        zt.append(f"{Z - 1:.4f}*{ez}")
        xt.append(f"({z['x'] - W / 2:.2f})*{ez}")
        yt.append(f"({z['y'] - H / 2:.2f})*{ez}")
    Z = "1+" + "+".join(zt)
    cx = f"{W / 2:.2f}+" + "+".join(xt)
    cy = f"{H / 2:.2f}+" + "+".join(yt)
    x = f"clip(({cx})-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(({cy})-ih/zoom/2,0,ih-ih/zoom)"
    return f"zoompan=z='{Z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps:g}"


# ---------------------------------------------------------------- spotlight
def make_spotlight_mask(path, W, H, spot):
    """spot: {x,y (center px), w,h (full size px), feather (0-1 fraction of radius)} -> gray PNG."""
    cx, cy = spot["x"], spot["y"]
    rx, ry = max(4, spot["w"] / 2), max(4, spot["h"] / 2)
    f = max(0.02, float(spot.get("feather", 0.35)))
    d = f"sqrt(pow((X-{cx:.1f})/{rx:.1f},2)+pow((Y-{cy:.1f})/{ry:.1f},2))"
    lum = f"255*clip((1+{f:.3f}-{d})/{f:.3f},0,1)"
    fu.run([fu.find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:d=1",
            "-vf", f"format=gray,geq=lum='{lum}'", "-frames:v", "1", path])
    return path


def spotlight_chain(inp, mask, out, spot, tag="sp"):
    """Filter snippet: dims everything outside the mask by `dim` (0.3-0.4 brand), fades 0.25 s."""
    s, e = float(spot["start"]), float(spot["end"])
    dim = float(spot.get("dim", 0.38))
    m = 1.0 - dim
    fd = min(0.25, (e - s) / 3)
    return (f"[{inp}]split=3[{tag}b][{tag}d][{tag}h];"
            f"[{tag}d]colorchannelmixer=rr={m:.3f}:gg={m:.3f}:bb={m:.3f}[{tag}dk];"
            f"[{tag}h]format=yuva420p[{tag}ha];[{tag}ha][{mask}]alphamerge[{tag}hl];"
            f"[{tag}dk][{tag}hl]overlay=0:0:format=auto[{tag}sp];"
            f"[{tag}sp]format=yuva420p,fade=t=in:st={s:.3f}:d={fd:.3f}:alpha=1,"
            f"fade=t=out:st={e - fd:.3f}:d={fd:.3f}:alpha=1[{tag}spf];"
            f"[{tag}b][{tag}spf]overlay=0:0:format=auto:shortest=1[{out}]")


# ---------------------------------------------------------------- standalone CLI
def _probe(path):
    import probe
    return probe.probe(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("effect", choices=["speed_ramp", "zoom_to_detail", "spotlight"])
    ap.add_argument("input"); ap.add_argument("output")
    ap.add_argument("--start", type=float, required=True); ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--x", type=float, default=0.5); ap.add_argument("--y", type=float, default=0.5)
    ap.add_argument("--w", type=float, default=0.3); ap.add_argument("--h", type=float, default=0.2)
    ap.add_argument("--zoom", type=float, default=2.0); ap.add_argument("--ease", type=float, default=0.3)
    ap.add_argument("--speed", type=float, default=4.0); ap.add_argument("--audio", default="mute")
    ap.add_argument("--dim", type=float, default=0.38); ap.add_argument("--feather", type=float, default=0.35)
    a = ap.parse_args()
    info = _probe(a.input)
    W, H, fps = info["display_width"], info["display_height"], info.get("fps") or 30
    W -= W % 2; H -= H % 2
    ff = fu.find_ffmpeg()
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
           "-movflags", "+faststart"]
    if a.effect == "zoom_to_detail":
        zf = zoom_filter([{"start": a.start, "end": a.end, "x": a.x * W, "y": a.y * H, "zoom": a.zoom,
                           "ease": a.ease}], W, H, fps)
        fu.run([ff, "-y", "-v", "error", "-i", a.input, "-vf", f"scale={W}:{H},{zf},format=yuv420p"] + enc + [a.output])
    elif a.effect == "spotlight":
        td = tempfile.mkdtemp()
        spot = {"start": a.start, "end": a.end, "x": a.x * W, "y": a.y * H, "w": a.w * W, "h": a.h * H,
                "dim": a.dim, "feather": a.feather}
        mask = make_spotlight_mask(os.path.join(td, "mask.png"), W, H, spot)
        fc = f"[0:v]scale={W}:{H},format=yuv420p[v0];[1:v]format=gray[m];" + spotlight_chain("v0", "m", "vout", spot)
        fu.run([ff, "-y", "-v", "error", "-i", a.input, "-loop", "1", "-framerate", f"{fps:g}", "-t",
                f"{info['duration']:.3f}", "-i", mask, "-filter_complex", fc, "-map", "[vout]", "-map", "0:a?"]
               + enc + [a.output])
    else:
        pieces = speed_pieces([{"start": 0.0, "end": info["duration"], "speed": 1, "mute": False}],
                              [{"start": a.start, "end": a.end, "speed": a.speed, "ease": a.ease,
                                "audio": a.audio}], fps)
        parts, labels = [], []
        n = len(pieces)
        parts.append(f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)))
        parts.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)))
        for i, p in enumerate(pieces):
            sp = p["speed"]
            parts.append(f"[vs{i}]trim={p['start']:.4f}:{p['end']:.4f},setpts=(PTS-STARTPTS)/{sp},fps={fps:g}[v{i}]")
            at = atempo_chain(sp)
            vol = ",volume=0" if p.get("mute") else ""
            parts.append(f"[as{i}]atrim={p['start']:.4f}:{p['end']:.4f},asetpts=PTS-STARTPTS"
                         f"{',' + at if at else ''}{vol}[a{i}]")
            labels.append(f"[v{i}][a{i}]")
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[vout][aout]")
        fu.run([ff, "-y", "-v", "error", "-i", a.input, "-filter_complex", ";".join(parts),
                "-map", "[vout]", "-map", "[aout]"] + enc + [a.output])
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()
