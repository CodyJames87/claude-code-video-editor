#!/usr/bin/env python3
"""Probe a clip before editing: rotation, display size, fps (VFR?), duration, audio, size.

Usage: python scripts/probe.py INPUT [--json out.json]
Works with ffprobe, or falls back to parsing `ffmpeg -i` when only imageio-ffmpeg exists.
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu


def _frac(s):
    try:
        if "/" in str(s):
            n, d = str(s).split("/"); return float(n) / float(d) if float(d) else 0.0
        return float(s)
    except Exception:
        return 0.0


def probe_ffprobe(path, ffprobe):
    r = fu.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in d["streams"] if s.get("codec_type") == "audio"), None)
    info = {"duration": float(d["format"].get("duration", 0) or 0),
            "bitrate_kbps": round(int(d["format"].get("bit_rate", 0) or 0) / 1000)}
    if v:
        rot = 0
        if "rotate" in v.get("tags", {}):
            rot = int(float(v["tags"]["rotate"]))
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        info.update(width=v["width"], height=v["height"], codec=v.get("codec_name"),
                    pix_fmt=v.get("pix_fmt"), rotation=rot,
                    fps=round(_frac(v.get("avg_frame_rate")), 3),
                    r_fps=round(_frac(v.get("r_frame_rate")), 3))
    if a:
        info.update(audio=True, audio_codec=a.get("codec_name"),
                    sample_rate=int(a.get("sample_rate", 0) or 0), channels=a.get("channels"))
    else:
        info["audio"] = False
    return info


def probe_ffmpeg(path):
    r = fu.run([fu.find_ffmpeg(), "-hide_banner", "-i", path], check=False)
    e = r.stderr
    info = {"probe_method": "ffmpeg -i (no ffprobe)"}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", e)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"bitrate: (\d+) kb/s", e)
    info["bitrate_kbps"] = int(m[1]) if m else 0
    vm = re.search(r"Stream #\S+.*Video: (\w+).*?, (\d{2,5})x(\d{2,5})", e)
    if vm:
        info.update(codec=vm[1], width=int(vm[2]), height=int(vm[3]))
        fm = re.search(r"([\d.]+) fps", e)
        info["fps"] = info["r_fps"] = float(fm[1]) if fm else 0.0
    rm = re.search(r"rotate\s*:\s*(-?\d+)", e) or re.search(r"rotation of (-?[\d.]+) degrees", e)
    info["rotation"] = int(float(rm[1])) if rm else 0
    am = re.search(r"Stream #\S+.*Audio: (\w+).*?(\d+) Hz, (\w+)", e)
    if am:
        info.update(audio=True, audio_codec=am[1], sample_rate=int(am[2]),
                    channels=2 if "stereo" in am[3] else (1 if "mono" in am[3] else am[3]))
    else:
        info["audio"] = False
    return info


def probe(path):
    if not os.path.exists(path):
        raise SystemExit(f"not found: {path}")
    fp = fu.find_ffprobe()
    info = probe_ffprobe(path, fp) if fp else probe_ffmpeg(path)
    info["path"] = os.path.abspath(path)
    info["size_mb"] = round(os.path.getsize(path) / 1e6, 2)
    rot = abs(info.get("rotation", 0)) % 180
    w, h = info.get("width", 0), info.get("height", 0)
    info["display_width"], info["display_height"] = (h, w) if rot == 90 else (w, h)
    dw, dh = info["display_width"], info["display_height"]
    info["orientation"] = "vertical" if dh > dw else ("horizontal" if dw > dh else "square")
    warn = []
    if info.get("rotation"):
        warn.append(f"rotation {info['rotation']} deg: ffmpeg auto-rotates on decode; crop math uses display size")
    if info.get("fps") and info.get("r_fps") and abs(info["fps"] - info["r_fps"]) > 0.5:
        warn.append("likely variable frame rate (phone clip): render forces constant fps")
    if not info.get("audio"):
        warn.append("no audio stream: transcript/captions impossible, loudness skipped")
    if info["size_mb"] > 30:
        warn.append("over 30 MB: too big for claude.ai upload/download; use Descript or a proxy")
    if dw and dh and min(dw, dh) < 720:
        warn.append("low resolution source (<720p): 1080 export will be upscaled")
    info["warnings"] = warn
    return info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--json")
    a = ap.parse_args()
    i = probe(a.input)
    if a.json:
        fu.save_json(i, a.json)
    print(json.dumps(i, indent=2))
