#!/usr/bin/env python3
"""Finish any render (e.g. Remotion output): two-pass loudnorm to -14 LUFS, verify true peak <= -1 dBTP,
AAC 160k 48 kHz, video re-encoded iPhone-safe (yuv420p, TV range, High@4.1, CRF 21, maxrate 10M); plus a <30 MB copy if needed.

Usage: python helpers/finish.py out/video.mp4 [-o out/video_final.mp4] [--lufs -14] [--tp -1] [--max-mb 30]
"""
import argparse, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu
import probe as pr
import render as rd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("-o", "--out")
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--max-mb", type=float, default=30.0); ap.add_argument("--bitrate", default=None,
                    help="re-encode video at this bitrate (e.g. 10M) instead of stream copy")
    a = ap.parse_args()
    ff = fu.find_ffmpeg()
    info = pr.probe(a.input)
    out = a.out or a.input.replace(".mp4", "_final.mp4")
    td = tempfile.mkdtemp()
    raw, norm = os.path.join(td, "a.wav"), os.path.join(td, "n.wav")
    fu.run([ff, "-y", "-v", "error", "-i", a.input, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", raw])
    rep = rd.normalize_audio(ff, raw, norm, a.lufs, a.tp)
    # iPhone-safe final : never yuvj420p / full range. High@4.1, yuv420p, TV range, CRF 21, maxrate 10M.
    vcodec = ["-vf", "scale=out_range=tv:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-profile:v", "high",
              "-level:v", "4.1", "-preset", "medium", "-crf", "21", "-maxrate", a.bitrate or "10M", "-bufsize", "20M",
              "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
              "-color_trc", "bt709"]
    fu.run([ff, "-y", "-v", "error", "-i", a.input, "-i", norm, "-map", "0:v:0", "-map", "1:a:0"] + vcodec +
           ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-shortest", out])
    chk = rd.measure_loudness(ff, out)
    res = {"output": os.path.abspath(out), "size_mb": round(os.path.getsize(out) / 1e6, 2), "loudnorm": rep,
           "final": chk, "true_peak_ok": chk["true_peak_dbtp"] is not None and chk["true_peak_dbtp"] <= a.tp}
    print(f"[loudnorm] I={chk['integrated_lufs']} LUFS  TP={chk['true_peak_dbtp']} dBTP  "
          f"({'OK' if res['true_peak_ok'] else 'OVER'})", file=sys.stderr)
    if res["size_mb"] > a.max_mb:
        dur = info["duration"]
        kbps = int((a.max_mb * 0.92 * 8000) / dur - 192)
        small = out.replace(".mp4", "_small.mp4")
        fu.run([ff, "-y", "-v", "error", "-i", out, "-c:v", "libx264", "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps*1.2)}k",
                "-bufsize", f"{kbps*2}k", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", small])
        res["small"] = {"path": os.path.abspath(small), "size_mb": round(os.path.getsize(small) / 1e6, 2)}
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
