#!/usr/bin/env python3
"""Private local review page for a finished cut: frame-accurate scrubber, timestamped notes with frame grabs,
versions (v1, v2 ... as separate files) with side-by-side / wipe compare, notes export to JSON + Markdown.

  python helpers/review_page.py build out/<name>-shorts_final.mp4 [--name <name>] [--label "first cut"] [--out review-pages/<name>]
  python helpers/review_page.py add-version review-pages/<name> out/<name>-v2-shorts_final.mp4 [--label "tighter hook"]
  python helpers/review_page.py approve review-pages/<name> v2        # marks it approved + read-only (locked)
  python helpers/review_page.py open review-pages/<name>              # starts the 127.0.0.1 server + opens the browser
  python helpers/review_page.py export review-pages/<name>            # notes -> notes/notes-export.json + notes/notes.md
  python helpers/review_page.py zip review-pages/<name> [--to <dir>]  # one zip (+ HOW TO OPEN.txt next to it)

The folder is SELF-CONTAINED: index.html, review_server.py (stdlib Python only), "Open Review.cmd" (double-click),
"HOW TO OPEN.txt", manifest.json, versions/ (copies of the finals; the originals in out/ are never touched),
notes/, frames/. Server binds to 127.0.0.1 only: no public host, no tunnel, nothing uploaded.
A version file is never overwritten: each add-version copies into a new vN-<file>; an approved version is locked.
"""
import argparse, datetime, json, os, shutil, stat, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CMD = r"""@echo off
rem Private review page: starts a server on THIS PC only (127.0.0.1) and opens your browser.
cd /d "%~dp0"
where python >nul 2>nul && (python review_server.py & goto :eof)
where py >nul 2>nul && (py -3 review_server.py & goto :eof)
echo Python was not found. Open index.html directly instead (notes then stay in the browser only).
start "" "%~dp0index.html"
pause
"""

HOWTO = """HOW TO OPEN THE REVIEW PAGE ({name})
==========================================

1. If this came as a .zip from Google Drive: download it, right-click > Extract All. (Drive's in-browser preview
   can't run it; it has to be opened on your PC.) If it's already a folder on your PC, skip this step.
2. Open the folder and DOUBLE-CLICK  "Open Review.cmd".
   A small black window opens (leave it open) and your browser shows the review page.
   It runs only on this PC (address 127.0.0.1). Nothing is uploaded or posted anywhere.
3. Scrub with the slider or the arrow keys (one frame per tap, Shift = one second). Space = play/pause.
4. Type a note and click "Add note at ..." : it saves the time code, the text and a picture of that exact frame
   into this folder (notes\\ and frames\\).
5. Versions on the left: click one to watch it; Shift+click another to compare it (side by side or wipe).
6. When you're done, click "Export Markdown" (or JSON). The file lands in notes\\ and in your Downloads;
   paste it into the next Claude brief.
7. Close the black window to stop it.

Command-line alternative (same thing):  python review_server.py   (run inside this folder)
From the editor repo:                    python helpers\\review_page.py open "{folder}"
"""


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    s = (j.get("streams") or [{}])[0]
    n, d = (s.get("r_frame_rate") or "30/1").split("/")
    return {"width": s.get("width"), "height": s.get("height"), "fps": round(float(n) / float(d or 1), 3),
            "duration": float(j.get("format", {}).get("duration") or 0)}


def load_man(folder):
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def write_page(folder, man):
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2)
    with open(os.path.join(HERE, "review_page_template.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*__MANIFEST__*/null", json.dumps(man))
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copy2(os.path.join(HERE, "review_server_template.py"), os.path.join(folder, "review_server.py"))
    with open(os.path.join(folder, "Open Review.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(CMD)
    with open(os.path.join(folder, "HOW TO OPEN.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(HOWTO.format(name=man["name"], folder=os.path.abspath(folder)))


def add_version(folder, man, src, label, status="in review"):
    src = os.path.abspath(src)
    if not os.path.exists(src):
        raise SystemExit(f"missing {src}")
    n = len(man["versions"]) + 1
    vid = f"v{n}"
    rel = f"versions/{vid}-{os.path.basename(src)}"
    dst = os.path.join(folder, rel)
    if os.path.exists(dst):
        raise SystemExit(f"{dst} already exists: versions are never overwritten")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)  # read-only copy of the final; the original stays where it is
    os.chmod(dst, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    v = {"id": vid, "label": label or os.path.basename(src), "file": rel, "source": src, "status": status,
         "added": datetime.datetime.now().isoformat(timespec="seconds"), **probe(src)}
    stem = os.path.splitext(src)[0]
    prev = (stem[:-6] if stem.endswith("_final") else stem) + "-preview.mp4"
    if os.path.exists(prev):
        prel = f"versions/{vid}-{os.path.basename(prev)}"
        shutil.copy2(prev, os.path.join(folder, prel))
        v["preview"] = prel
    man["versions"].append(v)
    return v


def main():
    ap = argparse.ArgumentParser(description="Private local review page (see docstring).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("final"); b.add_argument("--name"); b.add_argument("--label", default="")
    b.add_argument("--out"); b.add_argument("--status", default="in review")
    v = sub.add_parser("add-version"); v.add_argument("folder"); v.add_argument("final"); v.add_argument("--label", default="")
    v.add_argument("--status", default="in review")
    p = sub.add_parser("approve"); p.add_argument("folder"); p.add_argument("version")
    o = sub.add_parser("open"); o.add_argument("folder"); o.add_argument("--no-browser", action="store_true"); o.add_argument("--port")
    e = sub.add_parser("export"); e.add_argument("folder")
    z = sub.add_parser("zip"); z.add_argument("folder"); z.add_argument("--to")
    a = ap.parse_args()

    if a.cmd == "build":
        name = a.name or os.path.splitext(os.path.basename(a.final))[0].replace("_final", "").replace("-shorts", "")
        folder = os.path.abspath(a.out or os.path.join(ROOT, "review-pages", name))
        if os.path.exists(os.path.join(folder, "manifest.json")):
            raise SystemExit(f"{folder} already has a review page: use add-version (versions are never overwritten)")
        os.makedirs(os.path.join(folder, "notes"), exist_ok=True)
        os.makedirs(os.path.join(folder, "frames"), exist_ok=True)
        man = {"name": name, "created": datetime.datetime.now().isoformat(timespec="seconds"), "versions": []}
        add_version(folder, man, a.final, a.label, a.status)
        with open(os.path.join(folder, "notes", "notes.json"), "w") as f:
            f.write("[]")
        write_page(folder, man)
        print(f"review page: {folder}\nopen it: double-click \"{os.path.join(folder, 'Open Review.cmd')}\"  "
              f"or  python helpers\\review_page.py open \"{folder}\"")
    elif a.cmd == "add-version":
        man = load_man(a.folder)
        vv = add_version(a.folder, man, a.final, a.label, a.status)
        write_page(a.folder, man)
        print(f"added {vv['id']}: {vv['file']}")
    elif a.cmd == "approve":
        man = load_man(a.folder)
        for vv in man["versions"]:
            if vv["id"] == a.version:
                vv["status"] = "approved"
                vv["approved"] = datetime.datetime.now().isoformat(timespec="seconds")
                os.chmod(os.path.join(a.folder, vv["file"]), stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        write_page(a.folder, man)
        print(f"{a.version} marked approved (read-only)")
    elif a.cmd == "open":
        args = [sys.executable, os.path.join(a.folder, "review_server.py")] + (["--no-browser"] if a.no_browser else []) + \
               (["--port", a.port] if a.port else [])
        subprocess.call(args, cwd=a.folder)
    elif a.cmd == "export":
        sys.path.insert(0, os.path.abspath(a.folder))
        import importlib.util
        spec = importlib.util.spec_from_file_location("rs", os.path.join(a.folder, "review_server.py"))
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        print("wrote", rs.export(rs.load(rs.NOTES, []), rs.load(rs.MANIFEST, {})))
    elif a.cmd == "zip":
        folder = os.path.abspath(a.folder)
        man = load_man(folder)
        to = os.path.abspath(a.to or os.path.dirname(folder))
        os.makedirs(to, exist_ok=True)
        zp = os.path.join(to, f"Review Page - {man['name']}.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:  # mp4s don't compress: store
            for dp, _, fs in os.walk(folder):
                for f in fs:
                    full = os.path.join(dp, f)
                    z.write(full, os.path.join(f"Review Page - {man['name']}", os.path.relpath(full, folder)))
        with open(os.path.join(to, f"HOW TO OPEN - Review Page - {man['name']}.txt"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(HOWTO.format(name=man["name"], folder=f"Review Page - {man['name']}"))
        print(f"zip: {zp} ({os.path.getsize(zp) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
