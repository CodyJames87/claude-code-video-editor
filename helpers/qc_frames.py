#!/usr/bin/env python3
"""QC a finished render: stills at key moments + contact sheet, size/loudness/spec checks, caption-vs-audio.

Usage:
  python scripts/qc_frames.py OUTPUT.mp4 [--edit out/name.edit.json] [--out-dir qc/] [--max-frames 16]
         [--transcribe]                  # re-transcribe the render locally (faster-whisper) and compare to captions
         [--transcript words.json]       # or compare against a transcript of the render (ElevenLabs/Descript)
Then LOOK at every frame (Claude: open the JPGs / contact sheet) before delivering.
Exit code 0 = all automatic checks pass, 2 = something to fix (see "issues").
"""
import argparse, difflib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu
import probe as pr


def norm_tokens(s):
    return [t for t in re.sub(r"[^a-z0-9$%' ]", " ", s.lower()).split() if t]


def caption_match(caption_text, heard_text):
    a, b = norm_tokens(caption_text), norm_tokens(heard_text)
    sm = difflib.SequenceMatcher(None, a, b)
    diffs = [(op, " ".join(a[i1:i2]), " ".join(b[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    return round(sm.ratio(), 3), diffs[:20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--edit", help="<name>.edit.json written by render.py")
    ap.add_argument("--out-dir")
    ap.add_argument("--max-frames", type=int, default=16)
    ap.add_argument("--max-mb", type=float, default=30.0)
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--transcribe", action="store_true"); ap.add_argument("--transcript")
    ap.add_argument("--times", help="extra comma-separated seconds to grab, e.g. 1.2,4.5 (overlay/effect moments)")
    a = ap.parse_args()
    ff = fu.find_ffmpeg()
    base = os.path.splitext(os.path.basename(a.video))[0]
    od = a.out_dir or os.path.join(os.path.dirname(os.path.abspath(a.video)), "qc_" + base)
    os.makedirs(od, exist_ok=True)
    info = pr.probe(a.video)
    dur = info.get("duration", 0)
    edit = fu.load_json(a.edit) if a.edit else None

    # ---- pick frame times: start, cuts, effect windows, caption samples, end
    marks = [(0.15, "start")]
    if edit:
        for c in edit.get("cut_points", []):
            marks.append((c + 0.1, "after-cut"))
        for e in edit.get("effects", []):
            s, t = e["out_start"], e["out_end"]
            marks += [((s + t) / 2, f"{e['type']}-mid"), (max(0, s - 0.3), f"{e['type']}-before")]
        caps = edit.get("captions", [])
        step = max(1, len(caps) // 6)
        for c in caps[::step]:
            marks.append(((c["start"] + c["end"]) / 2, "caption"))
    else:
        for i in range(1, 8):
            marks.append((dur * i / 8, "even"))
    for x in (a.times or "").split(","):
        if x.strip():
            marks.append((float(x), "mark-mid"))
    marks.append((max(0, dur - 0.2), "end"))
    marks = sorted({round(t, 2): l for t, l in marks if 0 <= t < dur}.items())
    # thin out to max-frames, keeping effect frames first
    if len(marks) > a.max_frames:
        pri = [m for m in marks if "mid" in m[1] or m[1] in ("start", "end")]
        rest = [m for m in marks if m not in pri]
        k = max(0, a.max_frames - len(pri))
        rest = rest[:: max(1, len(rest) // max(1, k))][:k]
        marks = sorted(pri + rest)

    frames = []
    for i, (t, label) in enumerate(marks):
        p = os.path.join(od, f"f{i:02d}_{t:06.2f}s_{label}.jpg")
        fu.run([ff, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", a.video, "-frames:v", "1", "-q:v", "3", p])
        expect = None
        if edit:
            expect = next((c["text"] for c in edit.get("captions", []) if c["start"] <= t < c["end"]), None)
        frames.append({"t": t, "label": label, "path": p, "expected_caption": expect})
    # contact sheet (labels via filename order); 4 columns
    sheet = os.path.join(od, "contact_sheet.jpg")
    cols = 4; rows = (len(frames) + cols - 1) // cols
    W = 270
    lst = os.path.join(od, "frames.txt")
    with open(lst, "w") as f:
        for fr in frames:
            f.write(f"file '{fr['path']}'\n")
    fu.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf",
            f"scale={W}:-2,tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", "-q:v", "3", sheet], check=False)

    # ---- automatic checks
    issues = []
    size = info["size_mb"]
    if size > a.max_mb:
        issues.append(f"file is {size} MB (> {a.max_mb} MB claude.ai cap): deliver the _small.mp4 or re-render with lower --bitrate")
    if info.get("codec") != "h264": issues.append(f"video codec {info.get('codec')} (want h264)")
    if info.get("pix_fmt") not in (None, "yuv420p"): issues.append(f"pix_fmt {info.get('pix_fmt')} (want yuv420p)")
    if info.get("audio"):
        if info.get("audio_codec") != "aac": issues.append(f"audio codec {info.get('audio_codec')} (want aac)")
        if info.get("sample_rate") != 48000: issues.append(f"audio {info.get('sample_rate')} Hz (want 48000)")
    import render as rd
    loud = rd.measure_loudness(ff, a.video) if info.get("audio") else {}
    if loud:
        if loud["integrated_lufs"] is not None and abs(loud["integrated_lufs"] - a.lufs) > 1.0:
            issues.append(f"loudness {loud['integrated_lufs']} LUFS (target {a.lufs} +/-1)")
        if loud["true_peak_dbtp"] is not None and loud["true_peak_dbtp"] > a.tp:
            issues.append(f"true peak {loud['true_peak_dbtp']} dBTP (> {a.tp})")
    mbps = round(info.get("bitrate_kbps", 0) / 1000, 2)

    # ---- caption vs audio
    cap = None
    heard = None
    if a.transcript:
        import cutlist as cl
        heard = " ".join(w["text"] for w in cl.normalize_words(fu.load_json(a.transcript)))
    elif a.transcribe:
        import subprocess, tempfile
        tj = os.path.join(tempfile.mkdtemp(), "heard.json")
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "transcribe.py"), a.video, "-o", tj],
                           capture_output=True, text=True)
        if r.returncode == 0:
            heard = fu.load_json(tj)["text"]
        else:
            issues.append("could not re-transcribe render (use --transcript from ElevenLabs/Descript)")
    if edit and heard is not None:
        ratio, diffs = caption_match(edit.get("caption_text", ""), heard)
        cap = {"match_ratio": ratio, "differences": diffs}
        if ratio < 0.85:
            issues.append(f"captions match audio only {ratio:.0%}: review differences")

    rep = {"video": os.path.abspath(a.video), "duration": dur, "resolution": f"{info.get('width')}x{info.get('height')}",
           "fps": info.get("fps"), "video_codec": info.get("codec"), "bitrate_mbps": mbps, "size_mb": size,
           "audio": {"codec": info.get("audio_codec"), "sample_rate": info.get("sample_rate"), **loud},
           "caption_check": cap, "frames": frames, "contact_sheet": sheet, "issues": issues,
           "verdict": "PASS (now look at every frame)" if not issues else "FIX"}
    fu.save_json(rep, os.path.join(od, "qc_report.json"))
    print(json.dumps(rep, indent=2))
    sys.exit(0 if not issues else 2)


if __name__ == "__main__":
    main()
