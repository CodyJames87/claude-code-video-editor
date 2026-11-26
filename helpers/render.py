#!/usr/bin/env python3
"""Render a picked moment: cut -> reframe (9:16, 4:5) -> effects -> Clean Line captions -> loudnorm -> export.

Usage:
  python scripts/render.py --input clip.mp4 --cutlist cut.json --pick 1 --out-dir out/ --name my-clip
  python scripts/render.py --input clip.mp4 --start 12.5 --end 41 --transcript words.json --out-dir out/
Options:
  --aspects 9x16,4x5 (also 1x1, 16x9)   --effects effects.json   --crop-x auto|0-1   --crop-y auto|0-1
  --caption-mode active|keyword  --keywords "IPO,13 years"  --no-captions  --no-upper
  --caption-engine auto|ass|drawtext    --bitrate 10M --maxrate 12M  --max-mb 30  --lufs -14 --tp -1
effects.json (ALL times in SOURCE seconds, x/y/w/h as 0-1 fractions of the SOURCE frame):
  {"effects":[{"type":"speed_ramp","start":..,"end":..,"speed":4,"ease":0.4,"audio":"mute"},
              {"type":"zoom","start":..,"end":..,"x":0.5,"y":0.4,"zoom":2.0,"ease":0.3},
              {"type":"spotlight","start":..,"end":..,"x":0.5,"y":0.5,"w":0.3,"h":0.2,"dim":0.38}],
   "music":{"file":"bed.mp3","db":-20,"duck":true},
   "sfx":[{"file":"whoosh.mp3","at":12.4,"db":-10}]}
Writes per aspect: <name>_9x16.mp4 (+ _small.mp4 if over --max-mb) and <name>.edit.json for qc_frames.py.
"""
import argparse, json, math, os, re, statistics, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu
import effects as fx
import probe as pr
import cutlist as cl
try:
    import speaker_track as st
except ImportError:
    st = None

ASPECTS = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080), "16x9": (1920, 1080)}
# caption layout per aspect: font size, bottom margin (keeps clear of IG/FB UI)
CAP = {"9x16": (132, 600), "4x5": (112, 250), "1x1": (104, 200), "16x9": (92, 110)}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ timeline mapping
def build_pieces(segments, fps):
    snap = lambda t: round(round(t * fps) / fps, 6)
    return [{"start": snap(s["start"]), "end": snap(s["end"]), "speed": 1.0, "mute": False}
            for s in segments if snap(s["end"]) - snap(s["start"]) >= 1.0 / fps]


def out_len(p):
    return (p["end"] - p["start"]) / p["speed"]


def src_to_out(pieces, t):
    """Map a source time to output time (times inside cut gaps snap to the next kept piece)."""
    acc = 0.0
    for p in pieces:
        if t < p["start"]:
            return acc
        if t <= p["end"]:
            return acc + (t - p["start"]) / p["speed"]
        acc += out_len(p)
    return acc


def piece_at(pieces, t):
    for p in pieces:
        if p["start"] <= t <= p["end"]:
            return p
    return None


# ------------------------------------------------------------------ crop
def detect_face_center(path, t0, t1, samples=12):
    """Median center of the largest face across sampled frames (fractions), or None."""
    try:
        return _detect_face_center(path, t0, t1, samples)
    except Exception as e:  # missing/odd OpenCV build: fall back to center crop
        log(f"[crop] face detection unavailable ({type(e).__name__}); using center. "
            "For speaker-centered crops: pip install \"opencv-python-headless<5\" (OpenCV 5 dropped Haar cascades)")
        return None


def _detect_face_center(path, t0, t1, samples):
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs, ys = [], []
    for i in range(samples):
        t = t0 + (t1 - t0) * (i + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = casc.detectMultiScale(g, 1.1, 6, minSize=(int(min(w, h) * 0.06),) * 2)
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + fw / 2) / w); ys.append((y + fh / 2) / h)
    cap.release()
    if len(xs) < max(2, samples // 4):
        return None
    return statistics.median(xs), statistics.median(ys)


def crop_box(W, H, tw, th, cx, cy):
    """Crop (x,y,w,h) in source px for target aspect, centered on (cx,cy) fractions.
    Vertical placement puts the face ~40% down the frame."""
    ar = tw / th
    if W / H > ar:
        cw, ch = int(round(H * ar)) // 2 * 2, H
        x = min(max(0, cx * W - cw / 2), W - cw); y = 0
    else:
        cw, ch = W, int(round(W / ar)) // 2 * 2
        y = min(max(0, cy * H - ch * 0.4), H - ch); x = 0
    return int(x), int(y), cw, ch


def map_point(box, tw, th, x, y, W, H):
    cx, cy, cw, ch = box
    return (x * W - cx) / cw * tw, (y * H - cy) / ch * th


# ------------------------------------------------------------------ captions
def chunk_words(words, max_words=4, max_chars=16, gap=0.6):
    chunks, cur = [], []
    for i, w in enumerate(words):
        if cur:
            prev = cur[-1]
            chars = sum(len(x["text"]) + 1 for x in cur) + len(w["text"])
            brk = (len(cur) >= max_words or chars > max_chars or w["start"] - prev["end"] > gap
                   or (len(cur) >= 2 and re.search(r"[.!?,;:]$", prev["text"])))
            if re.search(r"[.!?]$", prev["text"]):
                brk = True
            if brk:
                chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    # avoid dangling 1-word chunks by merging into previous when it fits
    out = []
    for c in chunks:
        if out and len(c) == 1 and len(out[-1]) < max_words and c[0]["start"] - out[-1][-1]["end"] < 0.3 \
                and not re.search(r"[.!?]$", out[-1][-1]["text"]):
            out[-1].extend(c)
        else:
            out.append(c)
    return out


def ass_time(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(s):
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def clean_word(t, upper):
    t = t.strip()
    t = re.sub(r"^[\"'“”‘’]+|[\"“”]+$", "", t)
    return t.upper() if upper else t


def caption_events(words, total, mode, keywords, upper):
    """Return [(start,end,[(text,highlight_bool)])]"""
    kw = [k.strip().lower() for k in keywords if k.strip()]
    def is_kw(t):
        tl = re.sub(r"[^\w$%.]", "", t.lower())
        if kw:
            return any(tl == k or tl.strip(".") == k or (" " not in k and tl.startswith(k)) for k in kw)
        return bool(re.search(r"\d|\$", t))  # auto: numbers / money
    events = []
    chunks = chunk_words(words)
    for ci, c in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        cend = min(c[-1]["end"] + 0.35, nxt, total)
        toks = [clean_word(w["text"], upper) for w in c]
        if mode == "keyword":
            events.append((c[0]["start"], cend, [(t, is_kw(w["text"])) for t, w in zip(toks, c)]))
        else:
            for wi, w in enumerate(c):
                s = c[0]["start"] if wi == 0 else w["start"]
                e = c[wi + 1]["start"] if wi + 1 < len(c) else cend
                if e - s < 0.02:
                    continue
                events.append((s, e, [(t, j == wi) for j, t in enumerate(toks)]))
    return events, chunks


def write_ass(path, events, tw, th, aspect, font="Anton"):
    size, margin = CAP[aspect]
    # one accent word per caption ; ink #212121 outline
    white, ink, em = "&H00FFFFFF", fu.hex_to_ass(fu.INK), fu.hex_to_ass(fu.ACCENT)
    em_inline = "&H" + fu.ACCENT.lstrip("#")[4:6] + fu.ACCENT.lstrip("#")[2:4] + fu.ACCENT.lstrip("#")[0:2] + "&"
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {tw}", f"PlayResY: {th}", "WrapStyle: 0",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
             "MarginR, MarginV, Encoding",
             f"Style: Clean,{font},{size},{white},{white},{ink},&H96212121,0,0,0,0,100,100,1,0,1,7,3,2,70,70,{margin},1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    last_chunk_start = None
    for s, e, toks in events:
        parts = []
        for t, hl in toks:
            t = ass_escape(t)
            parts.append(f"{{\\c{em_inline}}}{t}{{\\c&HFFFFFF&}}" if hl else t)
        text = " ".join(parts)
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Clean,,0,0,0,,{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def drawtext_filters(events, tw, th, aspect, tmpdir):
    """Fallback when libass (ass filter) is missing: per-word drawtext with measured x offsets."""
    size, margin = CAP[aspect]
    font = os.path.join(fu.FONTS_DIR, "Anton-Regular.ttf")
    try:
        from PIL import ImageFont
        pf = ImageFont.truetype(font, size)
        width = lambda s: pf.getlength(s)
    except Exception:
        # Anton metrics: ~0.40 em per uppercase glyph, 0.234 em per space
        width = lambda s: sum(size * (0.234 if c == ' ' else 0.405) for c in s)
    space = width(" ") + size * 0.12  # outline eats part of the gap
    y = th - margin - size
    filt, n = [], 0
    fe = fu.ff_escape_path(font)
    for s, e, toks in events:
        total = sum(width(t) for t, _ in toks) + space * (len(toks) - 1)
        x = (tw - total) / 2
        for t, hl in toks:
            n += 1
            tf = os.path.join(tmpdir, f"w{n}.txt")
            with open(tf, "w", encoding="utf-8") as f:
                f.write(t)
            col = fu.ACCENT.replace("#", "0x") if hl else "white"
            filt.append(f"drawtext=fontfile='{fe}':textfile='{fu.ff_escape_path(tf)}':fontsize={size}:"
                        f"fontcolor={col}:borderw=7:bordercolor=0x212121:shadowx=0:shadowy=3:shadowcolor=0x212121@0.6:"
                        f"x={x:.1f}:y={y:.1f}:enable='between(t,{s:.3f},{e - 0.001:.3f})'")
            x += width(t) + space
    return filt


# ------------------------------------------------------------------ audio
def loudnorm_measure(ff, path, I, TP, LRA=11):
    r = fu.run([ff, "-hide_banner", "-nostats", "-i", path, "-af",
                f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"])
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("loudnorm measurement failed")
    return json.loads(m[-1])


def measure_loudness(ff, path):
    """Integrated LUFS + true peak (dBTP) via ebur128 (true-peak mode)."""
    r = fu.run([ff, "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true",
                "-f", "null", "-"], check=False)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    I = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", s)
    P = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    return {"integrated_lufs": float(I[1]) if I else None, "true_peak_dbtp": float(P[1]) if P else None}


def build_audio(ff, a, src, off, pieces, total, music, sfx, wav):
    inputs = ["-ss", f"{off:.3f}", "-i", src]
    parts, labels = [], []
    n = len(pieces)
    parts.append(f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit={n}" + "".join(f"[as{i}]" for i in range(n)))
    for i, p in enumerate(pieces):
        at = fx.atempo_chain(p["speed"])
        vol = ",volume=0" if p.get("mute") else ""
        d = min(0.012, (p["end"] - p["start"]) / 4)  # micro-fades kill clicks at cuts
        parts.append(f"[as{i}]atrim={p['start'] - off:.4f}:{p['end'] - off:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={d:.3f},afade=t=out:st={p['end'] - p['start'] - d:.4f}:d={d:.3f}"
                     f"{',' + at if at else ''}{vol}[a{i}]")
        labels.append(f"[a{i}]")
    parts.append("".join(labels) + f"concat=n={n}:v=0:a=1,apad,atrim=0:{total:.4f}[voice]")
    mix = ["[voice]"]
    idx = 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", music["file"]]
        mdb = float(music.get("db", -20))
        parts.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.4f},"
                     f"volume={mdb}dB,afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.2):.3f}:d=1.2[mus]")
        if music.get("duck", True):
            parts.append("[voice]asplit=2[voice][vkey]")
            mix = ["[voice]"]
            parts.append("[mus][vkey]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[mduck]")
            mix.append("[mduck]")
        else:
            mix.append("[mus]")
        idx += 1
    for j, s in enumerate(sfx or []):
        inputs += ["-i", s["file"]]
        at = src_to_out(pieces, float(s["at"]))
        ms = int(at * 1000)
        parts.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={float(s.get('db', -10))}dB,"
                     f"adelay={ms}|{ms}[sfx{j}]")
        mix.append(f"[sfx{j}]"); idx += 1
    if len(mix) > 1:
        parts.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,atrim=0:{total:.4f}[aout]")
    else:
        parts.append("[voice]anull[aout]")
    fu.run([ff, "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(parts), "-map", "[aout]",
                                                  "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", wav])


def normalize_audio(ff, wav, out, I, TP):
    tgt_tp = TP - 0.5  # headroom for AAC encoding overshoot
    m = loudnorm_measure(ff, wav, I, tgt_tp)
    af = (f"loudnorm=I={I}:TP={tgt_tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          f"linear=true:print_format=json")
    r = fu.run([ff, "-y", "-hide_banner", "-nostats", "-i", wav, "-af", af + ",aresample=48000", "-c:a", "pcm_s24le", out])
    j = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    p2 = json.loads(j[-1]) if j else {}
    rep = {"pass1": {k: m[k] for k in ("input_i", "input_tp", "input_lra")},
           "pass2_type": p2.get("normalization_type"), "pass2_output_i": p2.get("output_i"),
           "pass2_output_tp": p2.get("output_tp")}
    chk = measure_loudness(ff, out)
    if chk["true_peak_dbtp"] is not None and chk["true_peak_dbtp"] > tgt_tp:
        # linear mode fell back or peaks slipped: limit, then re-measure
        lim = 10 ** (tgt_tp / 20)
        tmp = out + ".lim.wav"
        fu.run([ff, "-y", "-v", "error", "-i", out, "-af",
                f"aresample=192000,alimiter=limit={lim:.4f}:attack=1:release=50:level=false,aresample=48000",
                "-c:a", "pcm_s24le", tmp])
        os.replace(tmp, out)
        rep["limiter_applied"] = True
        chk = measure_loudness(ff, out)
    rep["wav_check"] = chk
    return rep


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--cutlist"); ap.add_argument("--pick", default=None, help="pick id in cutlist (default first)")
    ap.add_argument("--start", type=float); ap.add_argument("--end", type=float)
    ap.add_argument("--transcript", help="word JSON (used with --start/--end for captions)")
    ap.add_argument("--out-dir", default="out"); ap.add_argument("--name", default=None)
    ap.add_argument("--aspects", default="9x16,4x5")
    ap.add_argument("--effects"); ap.add_argument("--crop-x", default="auto"); ap.add_argument("--crop-y", default="auto")
    ap.add_argument("--speaker-track", action="store_true",
                    help="opt-in per-speaker 9:16 reframing (OpenCV + transcript speaker labels)")
    ap.add_argument("--no-captions", action="store_true"); ap.add_argument("--no-upper", action="store_true")
    ap.add_argument("--caption-mode", choices=["active", "keyword"], default="active")
    ap.add_argument("--keywords", default="")
    ap.add_argument("--caption-engine", choices=["auto", "ass", "drawtext"], default="auto")
    ap.add_argument("--bitrate", default="10M"); ap.add_argument("--maxrate", default="12M")
    ap.add_argument("--preset", default="medium"); ap.add_argument("--max-mb", type=float, default=30.0)
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--tp", type=float, default=-1.0)
    a = ap.parse_args()

    ff = fu.find_ffmpeg()
    info = pr.probe(a.input)
    W, H = info["display_width"], info["display_height"]
    fps = info.get("fps") or 30.0
    fps = 30.0 if fps <= 0 or fps > 120 else round(fps, 3)
    name = a.name or os.path.splitext(os.path.basename(a.input))[0]
    os.makedirs(a.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="cve_")

    # --- segments + words (source time)
    if a.cutlist:
        cut = fu.load_json(a.cutlist)
        picks = cut["picks"]
        pk = next((p for p in picks if str(p.get("id")) == str(a.pick)), picks[0]) if a.pick else picks[0]
        segments, words = pk["segments"], pk.get("words", [])
    else:
        if a.start is None or a.end is None:
            raise SystemExit("give --cutlist or --start/--end")
        segments = [{"start": a.start, "end": a.end}]
        words = []
        if a.transcript:
            words = [w for w in cl.normalize_words(fu.load_json(a.transcript))
                     if w["start"] >= a.start - 0.05 and w["end"] <= a.end + 0.05]
    pieces = build_pieces(segments, fps)
    fxcfg = fu.load_json(a.effects) if a.effects else {}
    effs = fxcfg.get("effects", [])
    ramps = [e for e in effs if e["type"] == "speed_ramp"]
    if ramps:
        pieces = fx.speed_pieces(pieces, ramps, fps)
    total = round(sum(out_len(p) for p in pieces), 4)
    off = max(0.0, pieces[0]["start"] - 1.0)  # input seek offset (fast on long podcasts)

    # --- timeline words for captions (drop words in muted/sped pieces)
    tl_words = []
    for w in words:
        p = piece_at(pieces, (w["start"] + w["end"]) / 2)
        if not p or p.get("mute") or p["speed"] != 1.0:
            continue
        tl_words.append({"text": w["text"], "start": round(src_to_out(pieces, w["start"]), 3),
                         "end": round(src_to_out(pieces, w["end"]), 3)})
    log(f"[render] {len(pieces)} pieces, output {total:.2f}s, {len(tl_words)} caption words")

    # --- audio: build, two-pass loudnorm, verify
    raw = os.path.join(tmp, "edit.wav"); norm = os.path.join(tmp, "norm.wav")
    has_audio = info.get("audio")
    loud = None
    if has_audio:
        build_audio(ff, a, a.input, off, pieces, total, fxcfg.get("music"), fxcfg.get("sfx"), raw)
        loud = normalize_audio(ff, raw, norm, a.lufs, a.tp)
        log(f"[loudnorm] pass1 I={loud['pass1']['input_i']} TP={loud['pass1']['input_tp']} -> "
            f"I={loud['wav_check']['integrated_lufs']} LUFS, TP={loud['wav_check']['true_peak_dbtp']} dBTP")

    # --- face / crop center
    cx = cy = None
    face = None
    if a.crop_x == "auto" or a.crop_y == "auto":
        face = detect_face_center(a.input, pieces[0]["start"], pieces[-1]["end"])
    cx = float(a.crop_x) if a.crop_x != "auto" else (face[0] if face else 0.5)
    cy = float(a.crop_y) if a.crop_y != "auto" else (face[1] if face else 0.5)
    log(f"[crop] center=({cx:.2f},{cy:.2f}) face={'yes' if face else 'no (center)'}")

    speaker_plan = None
    if a.speaker_track:
        if st is None:
            raise SystemExit("--speaker-track requires helpers/speaker_track.py")
        plan_tw, plan_th = ASPECTS.get("9x16", (1080, 1920))
        speaker_plan = st.plan(a.input, pieces[0]["start"], pieces[-1]["end"], words, plan_tw, plan_th)
        log(f"[speaker-track] clusters={len(speaker_plan['clusters'])} turns={len(speaker_plan['turns'])} "
            f"notes={speaker_plan['notes'] or 'none'}")
        for sp, face in speaker_plan.get("match", {}).items():
            log(f"[speaker-track] {sp} -> {face.get('id')} cx={face.get('cx'):.3f} "
                f"conf={face.get('confidence')} score={face.get('match_score')}")
        split = []
        for pce in pieces:
            for c in speaker_plan["crops"]:
                s = max(pce["start"], c["start"])
                e = min(pce["end"], c["end"])
                if e - s < 1.0 / fps:
                    continue
                q = dict(pce)
                q["start"], q["end"] = s, e
                q["speaker"] = c["speaker"]
                q["cx"], q["cy"] = c["cx"], c["cy"]
                q["st_conf"] = c["confidence"]
                split.append(q)
        if not split:
            raise SystemExit("speaker-track produced no crop segments")
        pieces = split
        total = round(sum(out_len(pce) for pce in pieces), 4)
        cx, cy = pieces[0]["cx"], pieces[0]["cy"]
        log(f"[speaker-track] {len(pieces)} crop segments, output {total:.2f}s")

    engine = a.caption_engine
    if engine == "auto":
        engine = "ass" if fu.has_filter("ass") else "drawtext"
    kws = [k for k in a.keywords.split(",") if k.strip()]
    events, chunks = caption_events(tl_words, total, a.caption_mode, kws, not a.no_upper) if (tl_words and not a.no_captions) else ([], [])

    sidecar = {"input": os.path.abspath(a.input), "probe": info, "fps": fps, "duration": total, "pieces": pieces,
               "cut_points": [], "effects": [], "captions": [{"start": s, "end": e, "text": " ".join(t for t, _ in tk),
                                                              "highlight": [t for t, h in tk if h]} for s, e, tk in events],
               "caption_text": " ".join(" ".join(clean_word(w["text"], False) for w in c) for c in chunks),
               "caption_engine": engine, "crop_center": [cx, cy], "face_detected": bool(face),
               "speaker_track": speaker_plan, "loudness_wav": loud, "outputs": {}}
    acc = 0.0
    for p, q in zip(pieces, pieces[1:]):
        acc += out_len(p)
        if abs(q["start"] - p["end"]) > 1e-3:  # real cut (not a speed-ramp step)
            sidecar["cut_points"].append(round(acc, 3))
        elif a.speaker_track and p.get("speaker") != q.get("speaker"):
            sidecar["cut_points"].append(round(acc, 3))
    for e in effs:
        sidecar["effects"].append({"type": e["type"], "out_start": round(src_to_out(pieces, e["start"]), 3),
                                   "out_end": round(src_to_out(pieces, e["end"]), 3)})

    for asp in [x.strip() for x in a.aspects.split(",") if x.strip()]:
        tw, th = ASPECTS[asp]
        box = crop_box(W, H, tw, th, cx, cy)
        n = len(pieces)
        g = [f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n))] if n > 1 else ["[0:v]null[vs0]"]
        per_piece_crop = bool(a.speaker_track and all("cx" in p for p in pieces) and st is not None)
        if per_piece_crop:
            for i, p in enumerate(pieces):
                x, y, cw, ch = st.crop_box_chin_safe(W, H, tw, th, p["cx"], p["cy"])
                p["_box_" + asp] = [x, y, cw, ch]
                g.append(f"[vs{i}]trim={p['start'] - off:.4f}:{p['end'] - off:.4f},setpts=(PTS-STARTPTS)/{p['speed']},"
                         f"fps={fps:g},crop={cw}:{ch}:{x}:{y},scale={tw}:{th}:flags=lanczos,setsar=1,format=yuv420p[v{i}]")
            g.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[rf]")
            box = tuple(pieces[0]["_box_" + asp])
        else:
            for i, p in enumerate(pieces):
                g.append(f"[vs{i}]trim={p['start'] - off:.4f}:{p['end'] - off:.4f},setpts=(PTS-STARTPTS)/{p['speed']},"
                         f"fps={fps:g}[v{i}]")
            g.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
            x, y, cw, ch = box
            g.append(f"[cat]crop={cw}:{ch}:{x}:{y},scale={tw}:{th}:flags=lanczos,setsar=1,format=yuv420p[rf]")
        cur = "rf"
        zooms = []
        for e in effs:
            if e["type"] == "zoom":
                px, py = map_point(box, tw, th, e["x"], e["y"], W, H)
                zooms.append({"start": src_to_out(pieces, e["start"]), "end": src_to_out(pieces, e["end"]),
                              "x": min(max(px, 0), tw), "y": min(max(py, 0), th),
                              "zoom": e.get("zoom", 1.8), "ease": e.get("ease", 0.3)})
        zf = fx.zoom_filter(zooms, tw, th, fps)
        if zf:
            g.append(f"[{cur}]{zf},format=yuv420p[zm]"); cur = "zm"
        extra_inputs = []
        spots = [e for e in effs if e["type"] == "spotlight"]
        for k, e in enumerate(spots):
            px, py = map_point(box, tw, th, e["x"], e["y"], W, H)
            spot = {"start": src_to_out(pieces, e["start"]), "end": src_to_out(pieces, e["end"]), "x": px, "y": py,
                    "w": e.get("w", 0.3) * W / box[2] * tw, "h": e.get("h", 0.2) * H / box[3] * th,
                    "dim": e.get("dim", 0.38), "feather": e.get("feather", 0.35)}
            mask = fx.make_spotlight_mask(os.path.join(tmp, f"mask_{asp}_{k}.png"), tw, th, spot)
            idx = 2 + len(extra_inputs) // 8
            extra_inputs += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{total + 1:.3f}", "-i", mask]
            g.append(f"[{idx}:v]format=gray[mk{k}]")
            g.append(fx.spotlight_chain(cur, f"mk{k}", f"sp{k}o", spot, tag=f"s{k}")); cur = f"sp{k}o"
        if events:
            if engine == "ass":
                ass = write_ass(os.path.join(tmp, f"cap_{asp}.ass"), events, tw, th, asp)
                g.append(f"[{cur}]ass='{fu.ff_escape_path(ass)}':fontsdir='{fu.ff_escape_path(fu.FONTS_DIR)}'[cap]")
            else:
                dts = drawtext_filters(events, tw, th, asp, tmp)
                g.append(f"[{cur}]" + ",".join(dts) + "[cap]")
            cur = "cap"
        g.append(f"[{cur}]format=yuv420p,trim=0:{total:.4f}[vout]")
        script = os.path.join(tmp, f"graph_{asp}.txt")
        with open(script, "w") as f:
            f.write(";\n".join(g))
        out = os.path.join(a.out_dir, f"{name}_{asp}.mp4")
        cmd = [ff, "-y", "-v", "error", "-ss", f"{off:.3f}", "-i", a.input]
        cmd += (["-i", norm] if has_audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
        cmd += extra_inputs
        cmd += ["-/filter_complex", script, "-map", "[vout]", "-map", "1:a",
                "-c:v", "libx264", "-preset", a.preset, "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-b:v", a.bitrate, "-maxrate", a.maxrate, "-bufsize", "16M", "-r", f"{fps:g}", "-g", str(int(fps * 2)),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{total:.4f}",
                "-movflags", "+faststart", out]
        log(f"[render] {asp} -> {out}")
        r = fu.run(cmd, check=False)
        if r.returncode != 0 and re.search(r"Option not found|Unrecognized option|-/filter_complex", r.stderr):
            # ffmpeg < 7 has no "-/opt file" syntax: use the legacy script option
            cmd[cmd.index("-/filter_complex")] = "-filter_complex_script"
            r = fu.run(cmd, check=False)
        if r.returncode != 0:
            raise RuntimeError("render failed:\n" + "\n".join(r.stderr.strip().splitlines()[-25:]))
        rec = {"path": os.path.abspath(out), "size_mb": round(os.path.getsize(out) / 1e6, 2), "crop": box}
        if has_audio:
            rec["loudness"] = measure_loudness(ff, out)
            tp = rec["loudness"]["true_peak_dbtp"]
            rec["true_peak_ok"] = tp is not None and tp <= a.tp
            log(f"[loudness] {asp}: I={rec['loudness']['integrated_lufs']} LUFS TP={tp} dBTP "
                f"({'OK' if rec['true_peak_ok'] else 'OVER -1 dBTP'})")
        if rec["size_mb"] > a.max_mb:
            kbps = int((a.max_mb * 0.92 * 8000) / total - 192)
            small = out.replace(".mp4", "_small.mp4")
            fu.run([ff, "-y", "-v", "error", "-i", out, "-c:v", "libx264", "-preset", a.preset, "-b:v", f"{kbps}k",
                    "-maxrate", f"{int(kbps * 1.2)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", small])
            rec["small"] = {"path": os.path.abspath(small), "size_mb": round(os.path.getsize(small) / 1e6, 2),
                            "video_kbps": kbps}
            log(f"[size] {rec['size_mb']} MB > {a.max_mb} MB: wrote {small} ({rec['small']['size_mb']} MB)")
        sidecar["outputs"][asp] = rec
    sc = os.path.join(a.out_dir, f"{name}.edit.json")
    fu.save_json(sidecar, sc)
    print(json.dumps({"edit_json": os.path.abspath(sc), "duration": total, "outputs": sidecar["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
