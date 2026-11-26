#!/usr/bin/env python3
"""Deliver a finished render for review (run after finish.py + QC, every time).

1. Makes <name>-preview.mp4 next to the final: H.264 ~540x960, under 1 MB (for a quick look on the phone).
2. Copies the final + preview into the folder set in deliver.config.json (drive_local_path, e.g. a synced Drive folder)
   (or, with "auto_find_drive": true, a Google Drive for desktop "My Drive\\Video Editor Output" folder).
3. If Drive for desktop isn't there, copies them to review\\ in this project instead and SAYS SO.
4. Appends an entry to review\\review-log.json with status "awaiting review".
Nothing is posted anywhere. Posting is always a separate, human-approved step.

QA GATE (mandatory): before anything is copied, every final must have a current helpers/qa_gate.py
report (out/.../qa_<stem>/qa_report.json matching the file's size + mtime). If there is none, deliver runs the gate
itself (with --props, default props/<name>.json when it exists). A FAIL BLOCKS delivery (exit 4) unless
--qa-override "reason" is given: the FAIL report stays, delivery proceeds, and the reason is written to
review/review-log.json. There is no silent bypass. --dry-run shows what would happen without copying or logging.

Usage: python helpers/deliver.py out/<name>-shorts_final.mp4 [more finals...] [--name <name>] [--note "..."]
         [--props props/<name>.json] [--captions ...] [--edl ...] [--accept-unsure "reason"]
         [--qa-override "reason"] [--dry-run]
"""
import argparse, datetime, json, os, re, shutil, string, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = {
    "drive_folder_name": "Video Editor Output",
    "drive_folder_url": "",
    "drive_local_path": "",
    "drive_subpath": "My Drive\\Video Editor Output",
    "fallback_dir": "review",
    "preview_max_mb": 1.0,
    "preview_size": "540x960",
}


def load_config():
    cfg = dict(DEFAULTS)
    p = os.path.join(ROOT, "deliver.config.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def find_drive_folder(cfg):
    """Return the local Drive for desktop output folder, or None."""
    if cfg.get("drive_local_path"):
        p = os.path.expandvars(os.path.expanduser(cfg["drive_local_path"]))
        if os.path.isdir(p):
            return p
        if os.path.isdir(os.path.dirname(p.rstrip("\\/"))):
            os.makedirs(p, exist_ok=True)
            return p
        return None
    if not cfg.get("auto_find_drive"):
        return None  # no folder configured: deliver to review/ (set drive_local_path or "auto_find_drive": true)
    sub = cfg["drive_subpath"].replace("\\", os.sep)
    my_drive = sub.split(os.sep)[0]  # "My Drive"
    cands = []
    if os.name == "nt":
        letters = ["G"] + [c for c in string.ascii_uppercase if c not in "ABG"]
        cands = [f"{c}:\\" for c in letters]
    else:  # macOS / Linux Drive for desktop mounts
        home = os.path.expanduser("~")
        cands = [os.path.join(home, "Google Drive"), "/Volumes/GoogleDrive"]
        cs = os.path.join(home, "Library", "CloudStorage")
        if os.path.isdir(cs):
            cands += [os.path.join(cs, d) for d in os.listdir(cs) if d.startswith("GoogleDrive")]
    for base in cands:
        full = os.path.join(base, sub)
        if os.path.isdir(full):
            return full
    for base in cands:  # Drive is mounted but the subfolder hasn't synced yet: create it under My Drive
        if os.path.isdir(os.path.join(base, my_drive)):
            full = os.path.join(base, sub)
            os.makedirs(full, exist_ok=True)
            return full
    return None


def duration(path):
    fp = fu.find_ffprobe()
    if fp:
        out = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.strip()
        if out:
            return float(out)
    err = subprocess.run([fu.find_ffmpeg(), "-i", path], capture_output=True, text=True).stderr  # imageio-ffmpeg has no ffprobe
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 60.0


def make_preview(src, dst, max_mb=1.0, size="540x960"):
    """H.264 preview under max_mb: bitrate from the size budget, retried lower until it fits."""
    dur = duration(src)
    w, h = (int(v) for v in size.split("x"))
    ab = 48_000
    vb = int(max_mb * 8_000_000 * 0.9 / dur) - ab
    for _ in range(6):
        sw, sh = (w, h) if vb >= 90_000 else (360, 640)  # very long clips: drop to 360x640 so it stays watchable
        fu.run([fu.find_ffmpeg(), "-y", "-v", "error", "-i", src,
                "-vf", f"scale={sw}:{sh}:force_original_aspect_ratio=decrease,pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2,fps=24",
                "-c:v", "libx264", "-preset", "medium", "-b:v", str(max(vb, 30_000)), "-maxrate", str(int(max(vb, 30_000) * 1.3)),
                "-bufsize", str(int(max(vb, 30_000) * 2)), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", str(ab), "-ac", "1", "-movflags", "+faststart", dst])
        mb = os.path.getsize(dst) / 1e6
        if mb < max_mb:
            return mb
        vb = int(vb * 0.8)
    raise SystemExit(f"Could not get {dst} under {max_mb} MB ({mb:.2f} MB)")


def qa_report_path(final):
    stem = os.path.splitext(os.path.basename(final))[0]
    return os.path.join(os.path.dirname(os.path.abspath(final)), "qa_" + stem, "qa_report.json")


def qa_gate(final, a, name):
    """Return (verdict, report_path). Reuses a current report, else runs helpers/qa_gate.py."""
    rp = qa_report_path(final)
    st = os.stat(final)
    if os.path.exists(rp):
        try:
            with open(rp, encoding="utf-8") as fh:
                rep = json.load(fh)
            if rep.get("size") == st.st_size and abs(rep.get("mtime_ms", 0) - st.st_mtime * 1000) < 2000                     and not any(c["name"] == "encode" and c["status"] == "SKIP" for c in rep.get("checks", [])):
                print(f"QA gate: using current report {rp}: {rep['overall']}")
                return rep["overall"], rp
        except Exception:
            pass
    props = a.props
    if not props:
        guess = os.path.join(ROOT, "props", f"{name}.json")
        props = guess if os.path.exists(guess) else None
    cmd = [sys.executable, os.path.join(ROOT, "helpers", "qa_gate.py"), final]
    if props:
        cmd += ["--props", props]
    if a.captions:
        cmd += ["--captions", a.captions]
    if a.edl:
        cmd += ["--edl", a.edl]
    if a.accept_unsure:
        cmd += ["--accept-unsure", a.accept_unsure]
    print(f"QA gate: running {' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) else c for c in cmd[1:])}", flush=True)
    r = subprocess.run(cmd)
    if not os.path.exists(rp):
        return "FAIL", None
    with open(rp, encoding="utf-8") as fh:
        rep = json.load(fh)
    return ("FAIL" if r.returncode != 0 and rep.get("overall") != "FAIL" else rep["overall"]), rp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("finals", nargs="+", help="finished MP4(s), e.g. out/clip-shorts_final.mp4")
    ap.add_argument("--name", help="clip name for the log (default: first file name)")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--props", help="props for the QA gate (default props/<name>.json if it exists)")
    ap.add_argument("--captions", help="captions for the QA gate (default: props.transcriptJson)")
    ap.add_argument("--edl", help="cut list for the QA gate's cut-seam check")
    ap.add_argument("--accept-unsure", default="", help="passed to qa_gate.py: accept a face-detector UNSURE (reason)")
    ap.add_argument("--qa-override", default="", help='deliver despite a QA FAIL: a short reason, logged. Never silent.')
    ap.add_argument("--dry-run", action="store_true", help="run the QA gate and show what would be delivered; copy/log nothing")
    a = ap.parse_args()
    cfg = load_config()
    name0 = a.name or re.sub(r"-(shorts|feed|long)?_?final$", "", os.path.splitext(os.path.basename(a.finals[0]))[0])

    # ---- QA gate (mandatory): block on FAIL unless --qa-override "reason"
    qa = []
    for f in a.finals:
        if not os.path.exists(f):
            raise SystemExit(f"Missing {f}")
        verdict, rp = qa_gate(f, a, name0)
        qa.append({"file": os.path.abspath(f), "verdict": verdict, "report": rp})
    failed = [q for q in qa if q["verdict"] != "PASS"]
    if failed and not a.qa_override.strip():
        for q in failed:
            print(f"BLOCKED: QA gate FAIL for {q['file']}\n  report: {q['report']}", file=sys.stderr)
        print("Nothing was copied to Drive. Fix the issues and re-run, or (only with a real reason) add "
              '--qa-override "reason" (the reason is logged in review/review-log.json).', file=sys.stderr)
        sys.exit(4)
    if failed:
        print(f"QA OVERRIDE: delivering despite a FAIL. Reason: {a.qa_override.strip()} (FAIL report kept, reason logged)")
    else:
        print("QA gate: PASS for every final. (You still LOOK at the contact sheet before delivering.)")
    if a.dry_run:
        print(f"DRY RUN: would make a preview, copy {len(a.finals)} final(s) + preview to "
              f"{find_drive_folder(cfg) or os.path.join(ROOT, cfg['fallback_dir'])} and log status 'awaiting review' with "
              f"qa={json.dumps([{'verdict': q['verdict'], 'overridden': bool(failed), 'override_reason': a.qa_override.strip() or None} for q in qa])}. Nothing copied or logged.")
        return

    files = []
    for f in a.finals:
        if not os.path.exists(f):
            raise SystemExit(f"Missing {f}")
        files.append(os.path.abspath(f))
        if not a.no_preview and f == a.finals[0]:
            stem = os.path.splitext(f)[0]
            stem = stem[:-6] if stem.endswith("_final") else stem
            prev = stem + "-preview.mp4"
            mb = make_preview(f, prev, cfg["preview_max_mb"], cfg["preview_size"])
            print(f"preview: {prev} ({mb:.2f} MB)")
            files.append(os.path.abspath(prev))

    drive = find_drive_folder(cfg)
    if drive:
        dest, where = drive, "google-drive"
    else:
        dest, where = os.path.join(ROOT, cfg["fallback_dir"]), "local-review-folder"
        os.makedirs(dest, exist_ok=True)
        print("NOTE: Google Drive for desktop folder not found, so the files were copied to the local review folder "
              f"{dest} instead. Upload them to {cfg['drive_folder_url']} (or install Drive for desktop).")
    copied = []
    for f in files:
        to = os.path.join(dest, os.path.basename(f))
        shutil.copy2(f, to)
        copied.append(to)
        print(f"copied: {to}")

    log_dir = os.path.join(ROOT, cfg["fallback_dir"])
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "review-log.json")
    log = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as fh:
                log = json.load(fh)
        except Exception:
            log = []
    name = a.name or os.path.splitext(os.path.basename(a.finals[0]))[0]
    if failed:
        entry_note = f"QA OVERRIDE: {a.qa_override.strip()}"
        a.note = (a.note + " | " if a.note else "") + entry_note
    entry = {
        "name": name,
        "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_files": files,
        "delivered_to": where,
        "delivered_paths": copied,
        "drive_folder": cfg["drive_folder_name"],
        "drive_folder_url": cfg["drive_folder_url"],
        "status": "awaiting review",
        "note": a.note,
        "qa": [{"file": q["file"], "verdict": q["verdict"], "report": q["report"],
                "overridden": q["verdict"] != "PASS", "override_reason": a.qa_override.strip() if q["verdict"] != "PASS" else None}
               for q in qa],
    }
    log.append(entry)
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2)
    print(f"logged: {log_path}")
    print(f"STATUS: {name} is awaiting review. Folder: {cfg['drive_folder_url'] or 'see path above'}")
    print("Nothing was posted. Review the clip yourself before scheduling it anywhere.")


if __name__ == "__main__":
    main()
