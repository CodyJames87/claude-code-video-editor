"""Shared helpers: locate ffmpeg/ffprobe (system first, imageio-ffmpeg fallback), run commands."""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
FONTS_DIR = os.path.join(SKILL_DIR, "assets", "fonts")
if not os.path.isdir(FONTS_DIR):
    FONTS_DIR = os.path.join(SKILL_DIR, "public", "fonts")


def _brand():
    try:
        with open(os.path.join(SKILL_DIR, "brand.config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# Colors come from brand.config.json (repo root). ACCENT is the ONLY caption highlight / lead accent.
_B = _brand()
ACCENT = _B.get("accent", "#2F6FED")    # one highlight word
SUPPORT = _B.get("support", "#8AA4C8")  # supporting only, NEVER a caption highlight
INK = _B.get("ink", "#1A1A1A")          # caption outlines, headlines
NEUTRAL = _B.get("neutral", "#5F6368")  # sublines, footers
EMERALD = ACCENT     # deprecated alias
BG_DARK = "#111418"  # functional dark canvas for stacked/composite layouts (layout color, not typography ink)


def _pip_install(pkg):
    for extra in ([], ["--user"], ["--break-system-packages"]):
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg] + extra,
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return False


def find_ffmpeg(install=True):
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.exists(env):
        return env
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg  # noqa
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    if install and _pip_install("imageio-ffmpeg"):
        import importlib, site
        importlib.invalidate_caches()
        try:
            sys.path.append(site.getusersitepackages())
        except Exception:
            pass
        try:
            import imageio_ffmpeg  # noqa
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    raise SystemExit("ffmpeg not found and imageio-ffmpeg could not be installed. "
                     "Try: pip install imageio-ffmpeg  (or apt-get install -y ffmpeg)")


def find_ffprobe():
    """Return ffprobe path or None (imageio-ffmpeg ships ffmpeg only)."""
    env = os.environ.get("FFPROBE_BIN")
    if env and os.path.exists(env):
        return env
    p = shutil.which("ffprobe")
    if p:
        return p
    ff = find_ffmpeg()
    cand = os.path.join(os.path.dirname(ff), "ffprobe" + (".exe" if ff.endswith(".exe") else ""))
    return cand if os.path.exists(cand) else None


def run(cmd, check=True, quiet=True):
    """Run a command list; return CompletedProcess. Raises with stderr tail on failure."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"Command failed ({r.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    if not quiet:
        sys.stderr.write(r.stderr)
    return r


def has_filter(name):
    r = run([find_ffmpeg(), "-hide_banner", "-filters"], check=False)
    return re.search(r"^\s*\S+\s+%s\s" % re.escape(name), r.stdout, re.M) is not None


def has_encoder(name):
    r = run([find_ffmpeg(), "-hide_banner", "-encoders"], check=False)
    return re.search(r"^\s*\S+\s+%s\s" % re.escape(name), r.stdout, re.M) is not None


def hex_to_ass(hex_color, alpha=0):
    """#RRGGBB -> ASS &HAABBGGRR"""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper().replace("&H", "&H")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def ff_escape_path(p):
    """Escape a path for use inside an ffmpeg filter argument (ass=, movie=)."""
    p = os.path.abspath(p)
    return p.replace("\\", "/").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")
