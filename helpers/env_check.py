#!/usr/bin/env python3
"""Room check: run FIRST in any new sandbox. Prints a JSON report of what the editor can use.

Usage: python scripts/env_check.py [--no-install]
"""
import argparse, json, os, platform, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-install", action="store_true", help="don't pip-install imageio-ffmpeg")
    a = ap.parse_args()
    rep = {"python": sys.version.split()[0], "platform": platform.platform()}
    try:
        ff = fu.find_ffmpeg(install=not a.no_install)
        rep["ffmpeg"] = ff
        rep["ffmpeg_source"] = "system" if shutil.which("ffmpeg") == ff else "imageio-ffmpeg/env"
        rep["ffmpeg_version"] = fu.run([ff, "-version"]).stdout.splitlines()[0]
    except SystemExit as e:
        rep["ffmpeg"] = None
        rep["error"] = str(e)
        print(json.dumps(rep, indent=2))
        sys.exit(1)
    rep["ffprobe"] = fu.find_ffprobe()
    rep["filters"] = {f: fu.has_filter(f) for f in
                      ["ass", "subtitles", "loudnorm", "zoompan", "alphamerge", "overlay",
                       "sidechaincompress", "atempo", "silencedetect", "ebur128", "tile"]}
    rep["encoders"] = {e: fu.has_encoder(e) for e in ["libx264", "aac"]}
    rep["bundled_font"] = os.path.exists(os.path.join(fu.FONTS_DIR, "Anton-Regular.ttf"))
    # smoke test: 1s render with ASS captions + loudnorm
    td = tempfile.mkdtemp()
    ass = os.path.join(td, "t.ass")
    with open(ass, "w") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 240\n\n[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Alignment, MarginV\n"
                "Style: D,Anton,40,&H00FFFFFF,&H00181411,1,3,2,20\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Text\nDialogue: 0,0:00:00.00,0:00:01.00,D,TEST {\\c&H2257FF&}OK\n")
    out = os.path.join(td, "smoke.mp4")
    vf = f"ass='{fu.ff_escape_path(ass)}':fontsdir='{fu.ff_escape_path(fu.FONTS_DIR)}'" if rep["filters"]["ass"] else "null"
    r = fu.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=1:r=30",
                "-f", "lavfi", "-i", "sine=f=440:d=1", "-vf", vf, "-af", "loudnorm=I=-14:TP=-1",
                "-c:v", "libx264" if rep["encoders"]["libx264"] else "mpeg4", "-c:a", "aac", "-ar", "48000", "-shortest", out],
               check=False)
    rep["smoke_render_ok"] = r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000
    if r.returncode != 0:
        rep["smoke_error"] = r.stderr[-800:]
    # transcription options
    tx = {}
    for mod in ["faster_whisper", "whisper", "cv2", "numpy"]:
        try:
            __import__(mod); tx[mod] = True
        except Exception:
            tx[mod] = False
    rep["python_modules"] = tx
    try:
        du = shutil.disk_usage(tempfile.gettempdir()); rep["free_disk_gb"] = round(du.free / 1e9, 1)
    except Exception:
        pass
    rep["cpu_count"] = os.cpu_count()
    ok = rep["smoke_render_ok"] and rep["filters"]["ass"] and rep["filters"]["loudnorm"]
    rep["verdict"] = "READY" if ok else "DEGRADED (see filters/smoke_error)"
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
