#!/usr/bin/env python3
"""Footage catalog: index your clips (public/media + an optional raw-footage inbox folder) and search them by word/phrase.

Usage:
  python helpers/footage_catalog.py index  [--paths P1 P2 ...] [--catalog catalog] [--include-drive|--no-drive] [--force]
  python helpers/footage_catalog.py search ERV [--catalog catalog] [--md out.md] [--html out.html] [--json out.json] [--limit N]
  python helpers/footage_catalog.py search "price book"
  python helpers/footage_catalog.py stats  [--catalog catalog]

Read-only on source media: never moves, renames or writes anything next to a video or in the inbox folder.
Writes only <catalog>/index.json, <catalog>/thumbs/<id>.jpg and the --md/--html/--json outputs
(+ a thumbs/ folder next to the md/html so the image links resolve).
Transcripts come from existing `<stem>.captions.json` sidecars only (no transcription here).
Every ffprobe/ffmpeg call has a timeout (Drive files stream on demand).
"""
import argparse
import datetime as _dt
import hashlib
import html as _html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCHEMA_VERSION = 1
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
DEFAULT_LOCAL = os.path.join(REPO, "public", "media")
# Optional second folder to index (e.g. a synced Google Drive / Dropbox "raw footage" folder).
# Set FOOTAGE_INBOX, or "footage_inbox" in editor.config.json. Unset = only public/media is indexed.
def _inbox_root():
    if os.environ.get("FOOTAGE_INBOX"):
        return os.environ["FOOTAGE_INBOX"]
    try:
        with open(os.path.join(REPO, "editor.config.json"), encoding="utf-8") as f:
            return json.load(f).get("footage_inbox") or ""
    except Exception:
        return ""


DRIVE_ROOT = _inbox_root() or os.path.join(REPO, "__no_inbox__")
LARGE_MB = 150
TIMEOUT = 60
INK, ACCENT = "#1A1A1A", "#2F6FED"

FLAG_ORIG = "orig (pre-audio-cleanup copy)"
FLAG_BACKUP = "backup"
FLAG_LARGE = "large/scratch"
FLAG_DRIVE_TO = "drive: not cached / timed out"

STOPWORDS = set("""
a about above after again against all also am an and any are aren't as at be because been before being below
between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few
for from further get got gonna gotta had hadn't has hasn't have haven't having he he'd he'll he's her here here's
hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself just know let
let's like me more most mustn't my myself no nor not now of off oh ok okay on once one only or other ought our ours
ourselves out over own really right same say said see she she'd she'll she's should shouldn't so some something
such than that that's the their theirs them themselves then there there's these they they'd they'll they're
they've thing things think this those through to too um uh under until up us very want was wasn't way we we'd
we'll we're we've well were weren't what what's when when's where where's which while who who's whom why why's
will with won't would wouldn't yeah yes you you'd you'll you're you've your yours yourself yourselves going go
kind lot back even still mean actually stuff because cause gonna wanna anything everything
""".split())
NAME_DROP = {"podcast", "final", "shorts", "src", "mp4", "mov", "img", "video", "singular", "display",
             "orig", "preflashfix", "raw", "the", "a", "an", "of", "to", "and", "in", "on", "for", "it"}

# tag -> regex (case-insensitive, whole word). Add your own topic words here (or in editor.config.json "glossary").
GLOSSARY = {
    "hiring": r"\b(hir(e|es|ed|ing)|recruit\w*)\b", "sales": r"\b(sales?|sell(s|ing)?|sold)\b",
    "systems": r"\bsystems?\b", "family": r"\bfamil(y|ies)\b", "failure": r"\b(fail(ure|ures|ed|ing)?)\b",
    "growth": r"\b(grow(th|ing|n)?|scal(e|ing))\b", "pricing": r"\b(pric(e|es|ing)|quotes?)\b",
    "customer": r"\b(customers?|clients?)\b", "leadership": r"\b(leaders?|leadership|culture)\b",
    "team": r"\b(team|teams|employees?)\b", "money": r"\b(money|profit\w*|revenue|cash)\b",
    "fear": r"\b(fear|scared|afraid)\b", "AI": r"\b(AI|Claude|Grok|ChatGPT)\b",
}
try:
    with open(os.path.join(REPO, "editor.config.json"), encoding="utf-8") as _f:
        GLOSSARY.update(json.load(_f).get("glossary") or {})
except Exception:
    pass
GLOSSARY_RX = {k: re.compile(v, re.I) for k, v in GLOSSARY.items()}


# ---------------------------------------------------------------- small utils
def slug(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "clip"


def norm_word(w):
    return re.sub(r"[^a-z0-9']+", "", w.lower().replace("\u2019", "'")).strip("'")


def fmt_t(ms):
    s = ms / 1000.0
    return f"{int(s // 60)}:{s % 60:04.1f}"


def fmt_dur(sec):
    if sec is None:
        return "?"
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def display_path(p):
    ap = os.path.abspath(p)
    try:
        rel = os.path.relpath(ap, REPO)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except ValueError:
        pass
    return ap


def abs_from_display(p):
    return p if os.path.isabs(p) else os.path.join(REPO, p)


def run(cmd, timeout=TIMEOUT):
    """Returns CompletedProcess or None on timeout."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return None


def frac(s):
    try:
        if "/" in str(s):
            n, d = str(s).split("/")
            return float(n) / float(d) if float(d) else 0.0
        return float(s)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- discovery
def find_drive_inbox():
    """The inbox root itself plus its immediate sub-folders (walked 2 levels deep later)."""
    if not os.path.isdir(DRIVE_ROOT):
        return None, []
    dirs = [DRIVE_ROOT]
    return DRIVE_ROOT, dirs


def walk_videos(root, max_depth=None, skip_names=()):
    out = []
    root = os.path.abspath(root)
    base_depth = root.rstrip("\\/").count(os.sep)
    for dp, dns, fns in os.walk(root):
        depth = dp.rstrip("\\/").count(os.sep) - base_depth
        dns[:] = [d for d in dns if d not in skip_names and not d.startswith(".")]
        if max_depth is not None and depth >= max_depth:
            dns[:] = []
        for f in fns:
            if os.path.splitext(f)[1].lower() in VIDEO_EXT:
                out.append(os.path.join(dp, f))
    return sorted(out)


# ---------------------------------------------------------------- transcripts
def load_caption_words(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    if isinstance(d, dict):
        d = d.get("captions") or d.get("words") or d.get("segments") or []
    words = []
    for c in d if isinstance(d, list) else []:
        if not isinstance(c, dict) or "text" not in c:
            continue
        t = str(c.get("text", "")).strip()
        if not t:
            continue
        s = c.get("startMs", c.get("start_ms"))
        e = c.get("endMs", c.get("end_ms"))
        if s is None and "start" in c:
            s = float(c["start"]) * 1000
        if e is None and "end" in c:
            e = float(c["end"]) * 1000
        w = {"t": t, "s": int(s or 0), "e": int(e or s or 0)}
        spk = c.get("speaker", c.get("speaker_id"))
        if spk not in (None, ""):
            w["spk"] = str(spk)
        if c.get("hook"):
            w["hook"] = True
        words.append(w)
    return words


def find_sidecar(video):
    d, f = os.path.split(video)
    stem = os.path.splitext(f)[0]
    cands = [os.path.join(d, stem + ".captions.json"), os.path.join(d, stem + ".captions.orig.json")]
    base = stem.split(".")[0]
    if base != stem:  # e.g. x.preflashfix.mp4 -> x.captions.json
        cands.append(os.path.join(d, base + ".captions.json"))
    parent = os.path.dirname(d)
    if os.path.basename(d).lower() == "orig":  # orig copies borrow the main sidecar
        cands += [os.path.join(parent, stem + ".captions.json"), os.path.join(parent, base + ".captions.json")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def find_speakers(video, words):
    spk = sorted({w["spk"] for w in words or [] if "spk" in w})
    if spk:
        return spk, "words"
    d, f = os.path.split(video)
    stem = os.path.splitext(f)[0]
    dirs = [d]
    if os.path.basename(d).lower() == "orig":
        dirs.append(os.path.dirname(d))
    for dd in dirs:
        for side in (stem + ".speakers.json", stem + ".render.json", stem.replace("-src", "") + "-9x16.render.json"):
            p = os.path.join(dd, side)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    txt = fh.read()
            except Exception:
                continue
            names = set(re.findall(r'"(?:who|speaker|speaker_id|name)"\s*:\s*"([^"]+)"', txt))
            names = {n for n in names if n.lower() not in ("composite", "none", "")}
            if names:
                return sorted(names), os.path.basename(p)
    return ["unknown"], None


# ---------------------------------------------------------------- tags
def name_tokens(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    toks = re.split(r"[-_\s.]+", stem.lower())
    return [t for t in toks if t and t not in NAME_DROP and t not in STOPWORDS and not t.isdigit() and len(t) > 1]


def transcript_tags(text, words):
    tags = [k for k, rx in GLOSSARY_RX.items() if rx.search(text or "")]
    cnt = Counter()
    for w in words or []:
        n = norm_word(w["t"])
        if len(n) >= 4 and n not in STOPWORDS and not n.isdigit() and "'" not in n:
            cnt[n] += 1
    top = [w for w, c in cnt.most_common(12) if c >= 2][:6]
    return tags, top


# ---------------------------------------------------------------- probing / thumbs
def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    if r is None:
        return None, "timeout"
    if r.returncode != 0:
        return None, (r.stderr.decode("utf-8", "replace").strip()[:200] or "ffprobe failed")
    d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info = {"duration": round(float(d.get("format", {}).get("duration", 0) or 0), 3), "has_audio": bool(a),
            "has_video": bool(v)}
    if v:
        rot = 0
        if "rotate" in (v.get("tags") or {}):
            rot = int(float(v["tags"]["rotate"]))
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        dw, dh = (h, w) if abs(rot) % 180 == 90 else (w, h)
        info.update(width=w, height=h, rotation=rot, display=f"{dw}x{dh}",
                    fps=round(frac(v.get("avg_frame_rate")) or frac(v.get("r_frame_rate")), 3),
                    codec=v.get("codec_name"), color_transfer=v.get("color_transfer"))
        if not info["duration"]:
            info["duration"] = round(float(v.get("duration", 0) or 0), 3)
    return info, None


def _mean_luma(jpg):
    try:
        from PIL import Image, ImageStat
        with Image.open(jpg) as im:
            return ImageStat.Stat(im.convert("L")).mean[0]
    except Exception:
        return None


def make_thumb(path, out_jpg, duration, large=False, hdr=False):
    """320 px wide JPEG from ~10 % in (fast input seek). Retries later if the frame is near-black."""
    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    tmp = out_jpg + ".tmp.jpg"
    dur = duration or 0
    times = [dur * 0.10, dur * 0.30, dur * 0.50] if dur > 0 else [0.0]
    vf_plain = "scale=320:-2:flags=bicubic"
    vf_hdr = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
              "zscale=t=bt709:m=bt709:r=tv,format=yuv420p," + vf_plain)
    best = None
    for i, t in enumerate(times):
        for vf in ([vf_hdr, vf_plain] if hdr else [vf_plain]):
            cmd = ["ffmpeg", "-v", "error", "-y"]
            if large:
                cmd += ["-noaccurate_seek"]
            cmd += ["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-an", "-vf", vf, "-q:v", "4", tmp]
            r = run(cmd)
            if r is None:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return "timeout"
            if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                break
        else:
            continue
        luma = _mean_luma(tmp)
        os.replace(tmp, out_jpg)
        best = "ok"
        if luma is None or luma >= 18 or i == len(times) - 1 or large:
            return best
    if os.path.exists(tmp):
        os.remove(tmp)
    return best or "failed"


# ---------------------------------------------------------------- index
def classify(path, source):
    flags = []
    name = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path)).lower()
    if source == "local" and parent == "orig":
        flags.append(FLAG_ORIG)
    stem_parts = name.split(".")
    if len(stem_parts) > 2 and re.search(r"(pre|bak|backup|old)", stem_parts[-2], re.I):
        flags.append(FLAG_BACKUP)
    elif re.search(r"\.bak|backup", name, re.I):
        flags.append(FLAG_BACKUP)
    size_mb = os.path.getsize(path) / 1e6
    if size_mb > LARGE_MB:
        flags.append(FLAG_LARGE)
    return flags


def clip_id(path, source):
    ap = os.path.abspath(path)
    if source == "local":
        try:
            rel = os.path.relpath(ap, DEFAULT_LOCAL)
            if not rel.startswith(".."):
                return slug(rel)
        except ValueError:
            pass
    if source == "drive-inbox":
        rel = os.path.relpath(ap, DRIVE_ROOT)
        top = rel.split(os.sep)[0]
        top = slug(top[:12])
        return "drive-" + top + "-" + slug(os.path.basename(ap))
    return slug(display_path(ap))[-60:] + "-" + hashlib.sha1(ap.encode()).hexdigest()[:6]


def attach_transcript(entry, abspath):
    side = find_sidecar(abspath)
    words = load_caption_words(side) if side else None
    if words:
        text = " ".join(w["t"] for w in words)
        text = re.sub(r"\s+", " ", text).strip()
        entry["transcript"] = {"status": "sidecar", "sidecar": display_path(side), "words_count": len(words),
                               "snippet": " ".join(text.split()[:30]) + (" ..." if len(text.split()) > 30 else ""),
                               "text": text,
                               "words": [[w["s"], w["e"], w["t"]] + ([w["spk"]] if "spk" in w else []) for w in words]}
    else:
        entry["transcript"] = {"status": "no transcript yet", "sidecar": None, "words_count": 0, "snippet": "",
                               "text": "", "words": []}
        text, words = "", []
    spk, spk_src = find_speakers(abspath, words)
    entry["speakers"] = spk
    entry["speakers_source"] = spk_src
    gl, top = transcript_tags(text, words)
    tags = []
    for t in name_tokens(abspath) + gl + top:
        if t not in tags:
            tags.append(t)
    entry["tags"] = tags


def index_one(path, source, catalog, prev, force):
    st = os.stat(path)
    size_mb = round(st.st_size / 1e6, 2)
    mtime = _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    cid = clip_id(path, source)
    flags = classify(path, source)
    thumb_rel = f"thumbs/{cid}.jpg"
    thumb_abs = os.path.join(catalog, "thumbs", cid + ".jpg")
    reused = (not force and prev and prev.get("size_mb") == size_mb and prev.get("mtime") == mtime
              and prev.get("probe_status") == "ok" and os.path.isfile(thumb_abs))
    if reused:
        e = dict(prev)
        e["flags"] = flags
        attach_transcript(e, path)
        return e, "skipped"
    e = {"id": cid, "path": display_path(path), "source": source, "size_mb": size_mb, "mtime": mtime,
         "flags": flags, "duration": None, "width": None, "height": None, "resolution": None, "fps": None,
         "rotation": None, "has_audio": None, "thumbnail": None, "probe_status": None}
    info, err = probe(path)
    if info is None:
        e["probe_status"] = FLAG_DRIVE_TO if (err == "timeout") else "error: " + err
        if err == "timeout" and FLAG_DRIVE_TO not in e["flags"]:
            e["flags"].append(FLAG_DRIVE_TO)
        attach_transcript(e, path)
        return e, "timeout" if err == "timeout" else "error"
    if not info.get("has_video"):
        return None, "audio-only"
    e.update(duration=info["duration"], width=info["width"], height=info["height"], resolution=info["display"],
             fps=info["fps"], rotation=info["rotation"] or None, has_audio=info["has_audio"], codec=info.get("codec"))
    hdr = (info.get("color_transfer") or "") in ("arib-std-b67", "smpte2084")
    if hdr:
        e["hdr"] = info["color_transfer"]
    ts = make_thumb(path, thumb_abs, info["duration"], large=FLAG_LARGE in flags, hdr=hdr)
    if ts == "ok":
        e["thumbnail"] = thumb_rel
        e["probe_status"] = "ok"
    elif ts == "timeout":
        e["probe_status"] = "thumb " + FLAG_DRIVE_TO
        e["flags"].append(FLAG_DRIVE_TO)
    else:
        e["probe_status"] = "ok (thumbnail failed)"
    attach_transcript(e, path)
    return e, "indexed"


def load_index(catalog):
    p = os.path.join(catalog, "index.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return None


def cmd_index(a):
    catalog = os.path.abspath(a.catalog if os.path.isabs(a.catalog) else os.path.join(REPO, a.catalog))
    os.makedirs(os.path.join(catalog, "thumbs"), exist_ok=True)
    old = load_index(catalog) or {}
    prev_by_path = {c["path"]: c for c in old.get("clips", [])}

    jobs = []  # (path, source)
    roots = []
    local_paths = a.paths or [DEFAULT_LOCAL]
    for p in local_paths:
        p = os.path.abspath(p)
        roots.append(display_path(p))
        if os.path.isfile(p):
            jobs.append((p, "local"))
        elif os.path.isdir(p):
            jobs += [(f, "local") for f in walk_videos(p)]
        else:
            print(f"  ! path not found: {p}")
    drive_status = "not scanned (--no-drive)"
    drive_dirs = []
    include_drive = a.include_drive if a.include_drive is not None else os.path.isdir(DRIVE_ROOT)
    if include_drive:
        root, drive_dirs = find_drive_inbox()
        if root is None:
            drive_status = "not found"
        else:
            drive_status = "found: " + root
            for d in drive_dirs:
                roots.append(d)
                jobs += [(f, "drive-inbox") for f in walk_videos(d, max_depth=2, skip_names=("Video Editor Output", "review"))]

    counts = Counter()
    clips = []
    print(f"Indexing {len(jobs)} video file(s) -> {display_path(catalog)}")

    def work(job):
        path, source = job
        try:
            return index_one(path, source, catalog, prev_by_path.get(display_path(path)), a.force)
        except Exception as ex:  # never let one clip kill the run
            return {"id": clip_id(path, source), "path": display_path(path), "source": source,
                    "probe_status": f"error: {ex}", "flags": [], "tags": [], "speakers": ["unknown"],
                    "transcript": {"status": "no transcript yet", "words": [], "text": "", "snippet": ""}}, "error"

    local_jobs = [j for j in jobs if j[1] == "local"]
    drive_jobs = [j for j in jobs if j[1] != "local"]
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        results += list(ex.map(work, local_jobs))
    with ThreadPoolExecutor(max_workers=2) as ex:
        results += list(ex.map(work, drive_jobs))
    for (path, source), (e, status) in zip(local_jobs + drive_jobs, results):
        counts[status] += 1
        if e is None:
            continue
        clips.append(e)
        mark = {"indexed": "+", "skipped": "=", "timeout": "T", "error": "!"}.get(status, "?")
        print(f"  {mark} {e['path']}  [{fmt_dur(e.get('duration'))}, {e.get('resolution') or '?'}"
              f"{', ' + ', '.join(e['flags']) if e.get('flags') else ''}]"
              f"{'  transcript' if e['transcript']['status'] == 'sidecar' else ''}")

    scanned = set(os.path.abspath(abs_from_display(r)) for r in roots)

    def under_scanned(p):
        ap = os.path.abspath(abs_from_display(p))
        return any(ap == r or ap.startswith(r.rstrip("\\/") + os.sep) for r in scanned)

    keep = [c for c in old.get("clips", []) if not under_scanned(c["path"]) and os.path.exists(abs_from_display(c["path"]))]
    clips = keep + clips
    # stale thumbs are left alone (cheap); ids are stable
    idx = {"schema_version": SCHEMA_VERSION, "built_at": _dt.datetime.now().isoformat(timespec="seconds"),
           "repo": REPO, "roots_scanned": roots, "drive_inbox": drive_status,
           "drive_inbox_dirs": drive_dirs, "clips": clips}
    tmp = os.path.join(catalog, "index.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(catalog, "index.json"))

    local = [c for c in clips if c["source"] == "local"]
    drive = [c for c in clips if c["source"] == "drive-inbox"]
    wt = sum(1 for c in clips if c["transcript"]["status"] == "sidecar")
    print("\nSUMMARY")
    print(f"  clips in catalog: {len(clips)} (local {len(local)}, drive-inbox {len(drive)})")
    print(f"  with transcript: {wt}   without (no transcript yet): {len(clips) - wt}")
    print(f"  this run: indexed {counts['indexed']}, skipped unchanged {counts['skipped']}, "
          f"timeouts {counts['timeout']}, errors {counts['error']}, audio-only skipped {counts['audio-only']}")
    print(f"  drive inbox: {drive_status}")
    for d in drive_dirs:
        print(f"    - {d}")
    print(f"  index: {display_path(os.path.join(catalog, 'index.json'))}")
    return 0


# ---------------------------------------------------------------- search
def parse_query(q):
    q = q.strip().strip('"').strip("'")
    return [t for t in (norm_word(x) for x in re.split(r"[\s\-_]+", q)) if t]


def tok_match(word, q):
    return word == q or word == q + "s" or word == q + "es" or word == q + "'s"


def search_clip(c, qt):
    words = c.get("transcript", {}).get("words", [])
    normed = [norm_word(w[2]) for w in words]
    # whisper sometimes glues/splits; also allow single words containing a hyphenated phrase
    hits = []
    n = len(qt)
    i = 0
    while i <= len(normed) - n:
        if all(tok_match(normed[i + k], qt[k]) for k in range(n)):
            hits.append(i)
            i += n
        else:
            i += 1
    name_norm = " ".join(name_tokens(c["path"]) + [norm_word(x) for x in re.split(r"[-_\s.]+", os.path.basename(c["path"]))])
    tag_norm = " | ".join(" ".join(parse_query(t)) for t in c.get("tags", []))
    phrase = " ".join(qt)
    rx = re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(s|es)?(?![a-z0-9])")
    name_hit = bool(rx.search(name_norm))
    tag_hit = bool(rx.search(tag_norm))
    return hits, name_hit, tag_hit, words


def context(words, i, n, mark):
    lo, hi = max(0, i - 5), min(len(words), i + n + 6)
    parts = []
    for k in range(lo, hi):
        t = words[k][2].strip()
        parts.append(mark(t) if i <= k < i + n else t)
    return ("... " if lo > 0 else "") + " ".join(parts) + (" ..." if hi < len(words) else "")


def cmd_search(a):
    catalog = os.path.abspath(a.catalog if os.path.isabs(a.catalog) else os.path.join(REPO, a.catalog))
    idx = load_index(catalog)
    if not idx:
        print("No catalog yet. Run: python helpers/footage_catalog.py index")
        return 2
    query = " ".join(a.query).strip().strip('"').strip("'")
    qt = parse_query(query)
    if not qt:
        print("Empty query.")
        return 2
    results = []
    for c in idx["clips"]:
        hits, name_hit, tag_hit, words = search_clip(c, qt)
        if not (hits or name_hit or tag_hit):
            continue
        score = len(hits) + (3 if name_hit else 0) + (2 if tag_hit else 0)
        results.append({"clip": c, "hits": hits, "name_hit": name_hit, "tag_hit": tag_hit, "score": score,
                        "words": words})
    # ties: prefer working copies over orig/backup/scratch duplicates
    results.sort(key=lambda r: (-r["score"], len(r["clip"].get("flags", [])), r["clip"]["path"]))
    total = len(results)
    if a.limit:
        results = results[:a.limit]

    print(f'Search "{query}": {total} clip(s) matched' + (f" (showing {len(results)})" if total > len(results) else ""))
    out_rows = []
    for r in results:
        c, n = r["clip"], len(qt)
        times = [fmt_t(r["words"][i][0]) for i in r["hits"][:5]]
        snip = context(r["words"], r["hits"][0], n, lambda t: f"[[{t}]]") if r["hits"] else ""
        why = [x for x, y in (("name", r["name_hit"]), ("tag", r["tag_hit"])) if y]
        print(f"\n  {c['path']}")
        print(f"    {fmt_dur(c.get('duration'))}  {c.get('resolution') or '?'}  source={c['source']}"
              f"{'  flags=' + '; '.join(c['flags']) if c.get('flags') else ''}")
        print(f"    transcript hits: {len(r['hits'])}" + (f" at {', '.join(times)}" if times else "")
              + (f"   (+{'/'.join(why)} match)" if why else "")
              + ("" if c["transcript"]["status"] == "sidecar" else "   [no transcript yet]"))
        if snip:
            print(f"    \"{snip}\"")
        out_rows.append({"id": c["id"], "path": c["path"], "source": c["source"], "duration": c.get("duration"),
                         "resolution": c.get("resolution"), "flags": c.get("flags", []), "score": r["score"],
                         "transcript_hits": len(r["hits"]), "name_hit": r["name_hit"], "tag_hit": r["tag_hit"],
                         "times": [{"t": fmt_t(r["words"][i][0]), "ms": r["words"][i][0]} for i in r["hits"]],
                         "snippets": [context(r["words"], i, n, lambda t: f"[[{t}]]") for i in r["hits"][:5]],
                         "thumbnail": c.get("thumbnail"), "tags": c.get("tags", []),
                         "speakers": c.get("speakers"), "transcript_status": c["transcript"]["status"]})
    if not results:
        print("  (no hits)")

    meta = {"query": query, "tokens": qt, "searched_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "catalog_built_at": idx.get("built_at"), "clips_searched": len(idx["clips"]), "matched": total}
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)) or ".", exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({**meta, "results": out_rows}, fh, ensure_ascii=False, indent=1)
        print(f"\n  json: {a.json}")
    for kind, path in (("md", a.md), ("html", a.html)):
        if not path:
            continue
        outdir = os.path.dirname(os.path.abspath(path))
        os.makedirs(outdir, exist_ok=True)
        thumbs = copy_thumbs(out_rows, catalog, outdir)
        writer = write_md if kind == "md" else write_html
        writer(path, meta, out_rows, thumbs, outdir)
        print(f"  {kind}: {path}")
    return 0 if results else 1


def copy_thumbs(rows, catalog, outdir):
    """Thumb links resolve as thumbs/<id>.jpg next to the page (copied unless the page lives in the catalog)."""
    got = {}
    same = os.path.normcase(os.path.abspath(outdir)) == os.path.normcase(os.path.abspath(catalog))
    for r in rows:
        if not r.get("thumbnail"):
            continue
        src = os.path.join(catalog, r["thumbnail"])
        if not os.path.isfile(src):
            continue
        if not same:
            dst = os.path.join(outdir, "thumbs", os.path.basename(src))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        got[r["id"]] = "thumbs/" + os.path.basename(src)
    return got


def clip_href(path, outdir):
    ap = os.path.abspath(abs_from_display(path))
    try:
        rel = os.path.relpath(ap, outdir).replace("\\", "/")
        if not os.path.isabs(rel) and not rel.startswith("../../../../.."):
            return rel
    except ValueError:
        pass
    return "file:///" + ap.replace("\\", "/")


def write_md(path, meta, rows, thumbs, outdir):
    L = [f"# Footage search: \"{meta['query']}\"", "",
         f"{meta['matched']} clip(s) matched out of {meta['clips_searched']} (catalog built {meta['catalog_built_at']}).", ""]
    for r in rows:
        L.append(f"## {os.path.basename(r['path'])}")
        L.append("")
        if r["id"] in thumbs:
            L.append(f"![{r['id']}]({thumbs[r['id']]})")
            L.append("")
        L.append(f"- Path: [`{r['path']}`](<{clip_href(r['path'], outdir)}>)")
        L.append(f"- Duration {fmt_dur(r['duration'])}, {r['resolution'] or '?'}, source {r['source']}"
                 + (f", flags: {'; '.join(r['flags'])}" if r["flags"] else ""))
        why = [x for x, y in (("file name", r["name_hit"]), ("tags", r["tag_hit"])) if y]
        L.append(f"- Transcript hits: {r['transcript_hits']}"
                 + (f" at {', '.join(t['t'] for t in r['times'][:5])}" if r["times"] else "")
                 + (f" (also matches {', '.join(why)})" if why else ""))
        for s in r["snippets"][:3]:
            L.append(f"  - \"{s.replace('[[', '**').replace(']]', '**')}\"")
        L.append("")
    if not rows:
        L.append("_No hits._")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def write_html(path, meta, rows, thumbs, outdir):
    def snip_html(s):
        out = _html.escape(s)
        return re.sub(r"\[\[(.+?)\]\]", lambda m: f'<b style="color:{ACCENT}">{m.group(1)}</b>', out)
    cards = []
    for r in rows:
        img = (f'<img src="{_html.escape(thumbs[r["id"]])}" alt="">' if r["id"] in thumbs
               else '<div class="noimg">no thumbnail</div>')
        times = ", ".join(t["t"] for t in r["times"][:5])
        snips = "".join(f"<p class='snip'>&ldquo;{snip_html(s)}&rdquo;</p>" for s in r["snippets"][:2])
        why = [x for x, y in (("name", r["name_hit"]), ("tag", r["tag_hit"])) if y]
        cards.append(
            f"<div class='card'>{img}<div class='meta'>"
            f"<a href=\"{_html.escape(clip_href(r['path'], outdir))}\">{_html.escape(os.path.basename(r['path']))}</a>"
            f"<p class='sub'>{fmt_dur(r['duration'])} &middot; {_html.escape(r['resolution'] or '?')} &middot; {r['source']}"
            f"{' &middot; ' + _html.escape('; '.join(r['flags'])) if r['flags'] else ''}</p>"
            f"<p class='sub'>{r['transcript_hits']} hit(s){' at ' + times if times else ''}"
            f"{' (+' + '/'.join(why) + ')' if why else ''}</p>{snips}</div></div>")
    body = "".join(cards) or "<p>No hits.</p>"
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Footage search: {_html.escape(meta['query'])}</title>
<style>
body{{background:#FFFFFF;color:{INK};font-family:Segoe UI,Arial,sans-serif;margin:32px}}
h1{{font-size:22px;margin:0 0 4px}} .top{{color:#595959;font-size:13px;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}}
.card{{border:1px solid #E5E5E5;border-radius:6px;overflow:hidden}}
.card img{{width:100%;display:block;background:#E5E5E5;max-height:420px;object-fit:contain}}
.noimg{{height:120px;display:flex;align-items:center;justify-content:center;color:#595959;background:#E5E5E5}}
.meta{{padding:10px 12px}} .meta a{{color:{INK};font-weight:700;text-decoration:none;word-break:break-all}}
.sub{{color:#595959;font-size:12px;margin:4px 0}} .snip{{font-size:13px;margin:6px 0}}
</style></head><body>
<h1>Footage search: &ldquo;{_html.escape(meta['query'])}&rdquo;</h1>
<div class="top">{meta['matched']} clip(s) matched out of {meta['clips_searched']} &middot; catalog built {meta['catalog_built_at']}</div>
<div class="grid">{body}</div></body></html>
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


# ---------------------------------------------------------------- stats
def cmd_stats(a):
    catalog = os.path.abspath(a.catalog if os.path.isabs(a.catalog) else os.path.join(REPO, a.catalog))
    idx = load_index(catalog)
    if not idx:
        print("No catalog yet. Run: python helpers/footage_catalog.py index")
        return 2
    clips = idx["clips"]
    by_src = Counter(c["source"] for c in clips)
    wt = [c for c in clips if c["transcript"]["status"] == "sidecar"]
    flags = Counter(f for c in clips for f in c.get("flags", []))
    tags = Counter(t for c in clips for t in c.get("tags", []))
    dur = sum(c.get("duration") or 0 for c in clips)
    print(f"Catalog: {display_path(os.path.join(catalog, 'index.json'))}  (schema {idx['schema_version']}, built {idx['built_at']})")
    print(f"Clips: {len(clips)}  ({', '.join(f'{k} {v}' for k, v in by_src.items())})")
    print(f"Total duration: {dur / 60:.1f} min   Total size: {sum(c.get('size_mb') or 0 for c in clips) / 1000:.2f} GB")
    print(f"With transcript: {len(wt)} ({sum(c['transcript']['words_count'] for c in wt)} words)   "
          f"Without: {len(clips) - len(wt)}")
    print(f"Drive inbox: {idx.get('drive_inbox')}")
    for d in idx.get("drive_inbox_dirs", []):
        print(f"  - {d}")
    print("Roots scanned: " + "; ".join(idx.get("roots_scanned", [])))
    if flags:
        print("Flags: " + ", ".join(f"{k} x{v}" for k, v in flags.most_common()))
    print("Top tags: " + ", ".join(f"{k} ({v})" for k, v in tags.most_common(25)))
    no_t = [c["path"] for c in clips if c["transcript"]["status"] != "sidecar"]
    if no_t:
        print(f"No transcript yet ({len(no_t)}):")
        for p in no_t[:60]:
            print("  - " + p)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Index and search your footage (public/media + optional inbox folder).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index", help="scan footage, probe, thumbnail, read caption sidecars")
    pi.add_argument("--paths", nargs="+", help="files/folders to scan (default public/media)")
    pi.add_argument("--catalog", default="catalog")
    g = pi.add_mutually_exclusive_group()
    g.add_argument("--include-drive", dest="include_drive", action="store_true", default=None)
    g.add_argument("--no-drive", dest="include_drive", action="store_false")
    pi.add_argument("--force", action="store_true", help="re-probe and re-thumbnail everything")
    ps = sub.add_parser("search", help='search names, tags and transcripts: word or "quoted phrase"')
    ps.add_argument("query", nargs="+")
    ps.add_argument("--catalog", default="catalog")
    ps.add_argument("--md")
    ps.add_argument("--html")
    ps.add_argument("--json")
    ps.add_argument("--limit", type=int, default=0)
    pt = sub.add_parser("stats", help="catalog counts")
    pt.add_argument("--catalog", default="catalog")
    a = ap.parse_args()
    return {"index": cmd_index, "search": cmd_search, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
