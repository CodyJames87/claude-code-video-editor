#!/usr/bin/env python3
"""Private review page server (local only). Started by "Open Review.cmd" in this folder.

Binds to 127.0.0.1 ONLY (nothing on the network or the internet can reach it), serves this folder, and saves notes
+ frame grabs into notes/ and frames/. Needs only Python 3 (usually already installed). If ffmpeg is on the PATH, note
frames are exact stills pulled from the video file; otherwise the browser's own frame is saved.
Stop it with Ctrl+C or by closing the window.
"""
import datetime, json, os, re, shutil, socket, subprocess, sys, threading, base64, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(HERE, "notes", "notes.json")
FRAMES = os.path.join(HERE, "frames")
MANIFEST = os.path.join(HERE, "manifest.json")


def load(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, p)


def timecode(t, fps):
    fr = int(round(t * fps))
    s, f = divmod(fr, int(round(fps)))
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}", fr


def export(notes, man):
    by = {v["id"]: v for v in man.get("versions", [])}
    md = [f"# Review notes: {man.get('name', '')}", "", f"Exported {datetime.datetime.now():%Y-%m-%d %H:%M}. "
          "Paste this into the next Claude brief. Times are on the version's own timeline.", ""]
    for vid in [v["id"] for v in man.get("versions", [])]:
        vn = sorted([n for n in notes if n["version"] == vid], key=lambda n: n["t"])
        if not vn:
            continue
        v = by[vid]
        md += [f"## {vid}: {v.get('label', '')} (`{v['file']}`)", ""]
        for n in vn:
            md.append(f"- **{n['timecode']}** ({n['t']:.3f} s, frame {n['frame']}): {n['text']}  ")
            md.append(f"  frame: `{n['image']}`" if n.get("image") else "  frame: none")
        md.append("")
    save(os.path.join(HERE, "notes", "notes-export.json"), {"name": man.get("name"), "exported": datetime.datetime.now().isoformat(timespec="seconds"),
                                                           "versions": man.get("versions", []), "notes": notes})
    with open(os.path.join(HERE, "notes", "notes.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return ["notes/notes-export.json", "notes/notes.md"]


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.startswith("/api/manifest"):
            return self._json(load(MANIFEST, {}))
        if self.path.startswith("/api/notes"):
            return self._json(load(NOTES, []))
        rng = self.headers.get("Range")
        path = self.translate_path(self.path.split("?")[0])
        if rng and os.path.isfile(path):  # byte ranges so the video scrubs/seeks properly
            size = os.path.getsize(path)
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            a = int(m[1]) if m and m[1] else 0
            b = int(m[2]) if m and m[2] else size - 1
            b = min(b, size - 1)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            self.send_header("Content-Length", str(b - a + 1))
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(a)
                left = b - a + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (ConnectionError, OSError):
                        return
                    left -= len(chunk)
            return
        return super().do_GET()

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        man = load(MANIFEST, {})
        if self.path.startswith("/api/notes"):
            d = self._body()
            v = next((x for x in man.get("versions", []) if x["id"] == d.get("version")), None)
            if not v or not str(d.get("text", "")).strip():
                return self._json({"error": "need a version and some text"}, 400)
            fps = float(v.get("fps") or 30)
            t = max(0.0, float(d.get("t", 0)))
            tc, fr = timecode(t, fps)
            notes = load(NOTES, [])
            nid = max([n["id"] for n in notes] + [0]) + 1
            os.makedirs(FRAMES, exist_ok=True)
            img = f"frames/note-{nid:03d}_{v['id']}_{tc.replace(':', '-')}.png"
            ok = False
            ffm = shutil.which("ffmpeg")
            if ffm:  # exact still from the file at this frame
                r = subprocess.run([ffm, "-v", "error", "-y", "-ss", f"{fr / fps + 0.5 / fps:.4f}", "-i", os.path.join(HERE, v["file"]),
                                    "-frames:v", "1", "-vf", "scale=540:-2", os.path.join(HERE, img)], capture_output=True)
                ok = r.returncode == 0 and os.path.exists(os.path.join(HERE, img))
            if not ok and str(d.get("image", "")).startswith("data:image/png;base64,"):
                with open(os.path.join(HERE, img), "wb") as f:
                    f.write(base64.b64decode(d["image"].split(",", 1)[1]))
                ok = True
            note = {"id": nid, "version": v["id"], "file": v["file"], "t": round(t, 3), "timecode": tc, "frame": fr,
                    "text": str(d["text"]).strip(), "image": img if ok else None, "frame_source": "ffmpeg" if ffm and ok else "browser" if ok else None,
                    "created": datetime.datetime.now().isoformat(timespec="seconds")}
            notes.append(note)
            save(NOTES, notes)
            return self._json(note)
        if self.path.startswith("/api/export"):
            return self._json({"written": export(load(NOTES, []), man)})
        return self._json({"error": "unknown"}, 404)

    def do_DELETE(self):
        m = re.match(r"/api/notes/(\d+)", self.path)
        if not m:
            return self._json({"error": "unknown"}, 404)
        notes = [n for n in load(NOTES, []) if n["id"] != int(m[1])]
        save(NOTES, notes)  # the frame PNG stays in frames/ (nothing is ever deleted from disk)
        return self._json({"ok": True})


def free_port(start=8765):
    for p in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return 0


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{srv.server_port}/index.html"
    print(f"Review page running privately on this PC: {url}\nKeep this window open while you review. Ctrl+C or close it to stop.")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
