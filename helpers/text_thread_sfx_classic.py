#!/usr/bin/env python3
"""Text Thread SFX pass. DEFAULT = "soft" (original sounds synthesized on your machine with numpy; royalty-free).
helpers/render_text_thread.mjs runs this automatically after the picture render (unless the spec sets "sfx": false / "none").

Preset selection ("sfxPreset" in the spec):
  - omitted / "soft" -> warmer synthesized sounds (DEFAULT).   - "classic" -> brighter synthesized sounds.
  - "custom" -> your own three files, nothing synthesized: assets/textthread/custom/sent.mp3 (me / blue land),
    received.mp3 (them / grey land), typing.mp3 (under typing dots + my pre-gaps). Make them yourself, e.g. with
    ElevenLabs Sound Effects ("soft short message sent swoosh, UI sound, 0.3 s") or any royalty-free source you
    are licensed to use. No sound files ship with this repo.
Auto-timed specs (no per-message "at") are supported: timing is taken from a mirror of src/textthread/timeline.ts.

Older notes (classic / soft history):

Synthesizes ORIGINAL sounds on this machine (numpy only; NOT Apple audio: no iOS/macOS system sounds, no extracted
iMessage/SMS files, no downloaded packs):
  - send_swoosh  : short airy send swish for  (blue, "me") bubbles
  - tri_ding     : three quick rising bell notes (tri-tone-STYLE lookalike) for incoming (grey, "them") bubbles
  - key_tap_1..6 : soft keyboard taps (6 variants) under the typing dots and in the pre-gap before each outgoing bubble
Mixes them to the exact bubble frames of a threads/<name>.json spec and muxes the mix onto the silent picture.

Usage: python helpers/text_thread_sfx_classic.py threads/<name>.json
  - Spec "sfxPreset": "soft" -> warmer v2 sounds (LP ~4 kHz, rounded attacks, short round ding, sparse dull taps),
    wavs in assets/textthread/classic-soft/. Without it: the v1 classic sounds below.
  - Spec "sfxPreset": "custom" -> no synthesis: your MP3s (assets/textthread/custom/
    sent / received / typing) decoded to 48 kHz stereo and placed on the same frames .
  - Sounds -> assets/textthread/classic/*.wav (48 kHz mono, peak -3 dBFS)
  - Mix    -> <output.dir>/sfx/<stem>-sfx-mix.wav (stereo 48 kHz, spec duration)
  - Picture: <stem>-shorts_silent.mp4 (Remotion render, kept untouched; created from <stem>-shorts.mp4 on first run)
    + mix -> <stem>-shorts.mp4 (video stream copied). Then: node helpers/finish.mjs <stem>-shorts.mp4 (WITH loudnorm).
Timing mirrors src/textthread/timeline.ts (explicit "at" per message required): appearFrame = round(at*fps),
typingFrame = round((at - typing)*fps).
"""
import json, math, os, shutil, subprocess, sys, wave
import numpy as np

SR, FPS = 48000, 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "textthread", "classic")
jsround = lambda x: int(math.floor(x + 0.5))  # JS Math.round
db = lambda d: 10 ** (d / 20)


def write_wav(path, x, ch=1):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def peak_norm(x, d=-3.0):
    return x / np.max(np.abs(x)) * db(d)


def biquad_bp(x, fc, q):
    """Band-pass (RBJ, constant 0 dB peak). fc may be an array (time-varying), evaluated per sample."""
    fc = np.broadcast_to(np.asarray(fc, float), x.shape)
    y = np.zeros_like(x); x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        w0 = 2 * math.pi * fc[i] / SR; al = math.sin(w0) / (2 * q); c = math.cos(w0); a0 = 1 + al
        b0, b2, a1, a2 = al / a0, -al / a0, -2 * c / a0, (1 - al) / a0
        v = b0 * x[i] + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x[i], y1, v
        y[i] = v
    return y


def swoosh():
    """Airy send swish: noise through a band-pass sweeping up 700 -> 4200 Hz, bell-shaped envelope, ~0.32 s."""
    n = int(0.34 * SR); t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    fc = 700 * (4200 / 700) ** np.clip(t / 0.22, 0, 1)
    x = biquad_bp(rng.standard_normal(n), fc, 1.4)
    env = np.exp(-((t - 0.075) / 0.055) ** 2)                       # quick swell
    env = np.where(t > 0.075, np.exp(-(t - 0.075) / 0.07), env)     # airy decay
    tone = np.sin(2 * np.pi * np.cumsum(500 + 900 * np.clip(t / 0.15, 0, 1)) / SR) * np.exp(-t / 0.06) * 0.12
    fade = np.ones(n); k = int(0.02 * SR); fade[-k:] = np.linspace(1, 0, k)
    return peak_norm((x * env + tone * np.minimum(1, t / 0.01)) * fade)


def bell(f, length, tau):
    n = int(length * SR); t = np.arange(n) / SR
    parts = [(1.0, 1.0, 1.0), (2.0, 0.28, 0.55), (3.01, 0.10, 0.35), (4.17, 0.05, 0.22)]  # ratio, amp, decay mult
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / (tau * d)) for r, a, d in parts)
    return x * np.minimum(1, t / 0.003)


def tri_ding():
    """Three quick rising bell notes (G5 - C6 - E6 style major arpeggio), 95 ms apart, soft sustain ~0.7 s."""
    notes = [784.0, 1046.5, 1318.5]
    step = 0.095; L = 0.85
    out = np.zeros(int((L + step * 2) * SR))
    for i, f in enumerate(notes):
        b = bell(f, L, 0.20 + 0.06 * i) * (0.85 + 0.075 * i)
        s = int(i * step * SR); out[s:s + len(b)] += b
    fade = np.ones(len(out)); k = int(0.03 * SR); fade[-k:] = np.linspace(1, 0, k)
    return peak_norm(out * fade)


def key_tap(seed):
    """Soft keyboard tap: tiny band-limited click + a short low body thump (each variant slightly different)."""
    rng = np.random.default_rng(100 + seed)
    n = int(0.045 * SR); t = np.arange(n) / SR
    fc = 2600 + 900 * rng.random()
    click = biquad_bp(rng.standard_normal(n), fc, 1.1) * np.exp(-t / (0.0035 + 0.0015 * rng.random()))
    f0 = 170 + 70 * rng.random()
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.012) * (0.35 + 0.15 * rng.random())
    x = click + body
    x *= np.minimum(1, t / 0.0005)
    return peak_norm(x)


def tap_times(rng, t0, t1, density):
    """Natural typing burst inside [t0, t1]: jittered 75-170 ms intervals with occasional short pauses."""
    out, t = [], t0 + rng.uniform(0.0, 0.06)
    while t <= t1:
        out.append(t)
        gap = rng.uniform(0.075, 0.17) / density
        if rng.random() < 0.14:
            gap += rng.uniform(0.12, 0.26)  # little think pause
        t += gap
    return out


# ---------------------------------------------------------------------------------------------------------------
# "soft" preset (the default; warmer than classic). Selected by "sfxPreset": "soft" in
# the spec. Same three sound roles, but warmer: 4th-order low-pass ~4 kHz on every sound, raised-cosine attacks (no
# clicks), pure-ish bell partials (no inharmonic metal), shorter ding decay, duller/lighter/sparser taps.
# Wavs -> assets/textthread/classic-soft/. The v1 classic sounds/behaviour above stay as they were.
# ---------------------------------------------------------------------------------------------------------------
ASSETS_SOFT = os.path.join(ROOT, "assets", "textthread", "classic-soft")


def biquad_lp(x, fc, q=0.707):
    """RBJ low-pass (static fc)."""
    w0 = 2 * math.pi * fc / SR; al = math.sin(w0) / (2 * q); c = math.cos(w0); a0 = 1 + al
    b0 = (1 - c) / 2 / a0; b1 = (1 - c) / a0; b2 = b0; a1 = -2 * c / a0; a2 = (1 - al) / a0
    y = np.zeros_like(x); x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        v = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x[i], y1, v
        y[i] = v
    return y


def lp4(x, fc):
    """4th-order (24 dB/oct) Butterworth-style low-pass: two cascaded biquads."""
    return biquad_lp(biquad_lp(x, fc, 0.541), fc, 1.307)


def soft_attack(t, a):
    """Raised-cosine fade-in over a seconds (no step / click)."""
    return np.where(t < a, 0.5 - 0.5 * np.cos(np.pi * np.clip(t / a, 0, 1)), 1.0)


def swoosh_soft():
    """Gentle send whoosh: noise through a wide band-pass sweeping 380 -> 2000 Hz (v1: 700 -> 4200, Q 1.4),
    25 ms raised-cosine swell (v1: ~instant gaussian edge), shorter airy tail, no chirp tone, LP 4 kHz. ~0.28 s."""
    n = int(0.28 * SR); t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    fc = 380 * (2000 / 380) ** np.clip(t / 0.2, 0, 1)
    x = biquad_bp(rng.standard_normal(n), fc, 0.9)
    env = soft_attack(t, 0.045) * np.where(t > 0.06, np.exp(-(t - 0.06) / 0.055), 1.0)
    fade = np.ones(n); k = int(0.04 * SR); fade[-k:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k))
    return peak_norm(lp4(x * env * fade, 4000))


def bell_soft(f, length, tau):
    n = int(length * SR); t = np.arange(n) / SR
    parts = [(1.0, 1.0, 1.0), (2.0, 0.10, 0.45)]  # fundamental + faint octave; v1 also had 3.01x / 4.17x (metallic)
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / (tau * d)) for r, a, d in parts)
    return x * soft_attack(t, 0.009)  # 9 ms rounded strike (v1: 3 ms linear)


def tri_ding_soft():
    """Three rising notes (same G5-C6-E6 arpeggio, 90 ms apart) but round and short: decay tau 0.10-0.13 s
    (v1 0.20-0.32 s), total ~0.55 s (v1 ~1.04 s), later notes not louder than the first, LP 4.5 kHz."""
    notes = [784.0, 1046.5, 1318.5]
    step = 0.09; L = 0.45
    out = np.zeros(int((L + step * 2) * SR))
    for i, f in enumerate(notes):
        b = bell_soft(f, L, 0.10 + 0.015 * i) * (0.95 - 0.08 * i)
        s = int(i * step * SR); out[s:s + len(b)] += b
    fade = np.ones(len(out)); k = int(0.06 * SR); fade[-k:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k))
    return peak_norm(lp4(out * fade, 4500))


def key_tap_soft(seed):
    """Dull, light tap: lower band-limited click (1.2-1.7 kHz, v1 2.6-3.5 kHz) with a 1.5 ms rounded attack
    (v1 0.5 ms), click mixed lower than the soft body thump, LP 3.2 kHz."""
    rng = np.random.default_rng(100 + seed)
    n = int(0.05 * SR); t = np.arange(n) / SR
    fc = 1200 + 500 * rng.random()
    click = biquad_bp(rng.standard_normal(n), fc, 0.9) * np.exp(-t / (0.004 + 0.0015 * rng.random())) * 0.55
    f0 = 150 + 60 * rng.random()
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.014) * (0.5 + 0.15 * rng.random())
    x = (click + body) * soft_attack(t, 0.0015)
    return peak_norm(lp4(x, 3200))


def tap_times_soft(rng, t0, t1, max_taps):
    """Sparse, relaxed typing: 130-260 ms gaps with occasional pauses, capped per burst."""
    out, t = [], t0 + rng.uniform(0.02, 0.1)
    while t <= t1 and len(out) < max_taps:
        out.append(t)
        t += rng.uniform(0.13, 0.26) + (rng.uniform(0.12, 0.3) if rng.random() < 0.2 else 0.0)
    return out


# ---------------------------------------------------------------------------------------------------------------
# "custom" preset: your own sent / received / typing MP3s in assets/textthread/custom/ (decoded with ffmpeg to
# 48 kHz stereo, silence trimmed, short fades); nothing synthesized.
# ---------------------------------------------------------------------------------------------------------------
PICKED = os.path.join(ROOT, "assets", "textthread", "custom")


def decode_mp3(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)


def trim_fade(x, thr_db=-50.0, fade_in=0.003, fade_out=0.06):
    """Trim leading/trailing material below thr_db re: peak, then raised-cosine fade-in/out (no clicks, clean end)."""
    m = np.abs(x).max(1); nz = np.where(m > m.max() * db(thr_db))[0]
    x = x[max(0, nz[0] - int(0.002 * SR)): nz[-1] + 1].copy()
    for k, sl in ((int(fade_in * SR), slice(None)), (int(fade_out * SR), slice(None, None, -1))):
        if k > 1:
            r = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k)))[:, None]
            if sl.step == -1:
                x[-k:] *= r[::-1]
            else:
                x[:k] *= r
    return x


def run_picked(spec, dur):
    """Returns (stereo mix [n,2], event log lines, last land time, end of last tone, sent-A hit offset)."""
    sent = trim_fade(decode_mp3(os.path.join(PICKED, "sent.mp3")), fade_out=0.04)
    recv = trim_fade(decode_mp3(os.path.join(PICKED, "received.mp3")), thr_db=-60, fade_out=0.08)  # ~0.45 s ding
    typ = decode_mp3(os.path.join(PICKED, "typing.mp3"))  # 1.9 s, 6 sparse key clicks; loop it for long windows
    onsets = [0.0, 0.215, 0.765, 0.925, 1.65, 1.82]          # tap onsets assumed inside typing.mp3 (s); tune for your file
    # sent-A is a quiet ~0.12 s rise into a 20 ms hit: pre-roll it so the HIT lands 1 frame after the bubble's
    # appearFrame (the pop), instead of ~4 frames late. received-C's strike is at its start: it starts on appearFrame.
    hit = int(np.argmax(np.abs(sent).max(1))) / SR
    # Design gains (relative; the mix is pre-leveled to -14 LUFS afterwards): sent-A and received-C at the same gain (the
    # sustained ding reads ~4-5 dB fuller at 100 ms; lowering it only squashes sent-A harder); typing well under both.
    G_SENT, G_RECV, G_TYPE = db(-15), db(-15), db(-28)
    n = int(round(dur * SR)); mix = np.zeros((n + 3 * SR, 2))
    tile = np.concatenate([typ] * 4)
    rng = np.random.default_rng(24)
    log, prev_end, last_land = [], 0.0, 0.0

    def add(x, t, g):
        s = int(round(t * SR)); mix[s:s + len(x)] += x * g

    for m in spec["messages"]:
        at = m["at"]; land = jsround(at * FPS) / FPS; L = len(m["text"])
        me = m["from"] == "me"
        start = land + 1 / FPS - hit if me else land          # when the land sound file starts
        t1 = min(land - 0.12, start - 0.01)                   # typing ends before the land tone
        if not me:
            t0 = jsround((at - m.get("typing", 0.5)) * FPS) / FPS + 0.05   # under the typing dots
        else:
            lead = min(1.5, 0.3 + 0.008 * L)                  # short lines: brief burst; msgs 11/13: ~1.0 / 1.5 s
            t0 = land - lead
        t0 = max(t0, prev_end + 0.08)                         # never over the previous land tone
        W = t1 - t0
        if W > 0.08:
            o = onsets[rng.integers(0, len(onsets))]          # start each window on a click, varied per window
            s = int(o * SR); seg = tile[s:s + int(W * SR)].copy()
            k = min(int(0.03 * SR), len(seg) // 3)
            seg[-k:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k)))[:, None]
            add(seg, t0, G_TYPE)
            tw = f"typing {t0:5.2f}-{t1:5.2f} ({W:4.2f} s from {o:.3f})"
        else:
            tw = "typing none (gap too short)"
        snd, g, kind = (sent, G_SENT, "sent-A") if me else (recv, G_RECV, "received-C")
        add(snd, start, g)
        prev_end = start + len(snd) / SR; last_land = land
        log.append(f"  {'BLUE' if me else 'GREY'} land {land:6.3f} {kind:10s} file@{start:6.3f} {tw}  {m['text'][:36]!r}")
    return mix[:n], log, last_land, prev_end, hit


def default_hold(text):
    """Mirror of timeline.ts defaultHold (auto timing only): ~25 % more read time than the pre-Nov-24 formula
    clamp(0.5 + 0.045 * len, 0.9, 3.0) -> clamp(0.62 + 0.056 * len, 1.1, 3.7)."""
    return min(3.7, max(1.1, 0.62 + 0.056 * len(text)))


def default_typing(text):
    return min(0.7, max(0.4, 0.4 + 0.01 * len(text)))


def normalize_timing(spec):
    """Fill in "at" / "typing" for auto-timed messages and "duration" (mirror of timeline.ts buildTimeline), so every
    preset can place sounds on the exact frames the picture uses. Explicit "at" / "duration" are left untouched."""
    pace = spec.get("pace", 1); sv = spec.get("startVisible", 0)
    f = lambda s: jsround(s * pace * FPS)
    t = 0; last = 0
    for i, m in enumerate(spec["messages"]):
        if i < sv:
            if i == sv - 1:
                t = f(m.get("hold", default_hold(m["text"])))
            m.setdefault("at", 0.0); continue
        if "at" in m:
            af = jsround(m["at"] * FPS); t = af + f(m.get("hold", default_hold(m["text"]))); last = af; continue
        if m["from"] == "them":
            ty = f(m.get("typing", default_typing(m["text"])))
            t += ty; m["typing"] = ty / FPS
        else:
            t += f(m.get("typing", 0.3))
        m["at"] = t / FPS; last = t
        t += f(m.get("hold", default_hold(m["text"])))
    if not spec.get("duration"):
        spec["duration"] = max(1, last + jsround(spec.get("endHold", 4) * FPS)) / FPS
    return spec


def ebur(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    L = [l.strip() for l in r.stderr.splitlines()]
    return (float([l for l in L if l.startswith("I:")][-1].split()[1]),
            float([l for l in L if l.startswith("Peak:")][-1].split()[1]))


def main_picked(spec, dur, out_dir, stem):
    mix, log, last_land, last_end, hit = run_picked(spec, dur)
    mix_path = os.path.join(out_dir, "sfx", os.path.basename(stem) + "-sfx-mix.wav")
    # Pre-level so finish.mjs's two-pass loudnorm stays LINEAR. A sparse SFX-only mix needs ~+20 dB to reach -14 LUFS;
    # sent-A's 20 ms hit has ~19 dB peak-to-loudness, so without this the true peak overshoots -1.5 and loudnorm falls
    # back to DYNAMIC mode (uneven gain, lifts the quiet typing toward the lands). Here: gain + a fast peak limiter at
    # -2.3 dBFS (only sent-A's hit reaches it), iterated until the mix itself is -14.0 LUFS, so finish.mjs adds ~0 dB.
    raw_path = mix_path[:-4] + "-raw.wav"
    write_wav(raw_path, mix.reshape(-1), ch=2)
    I0, _ = ebur(raw_path); gain = -14.0 - I0
    for _ in range(6):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw_path, "-af",
                        f"volume={gain:.3f}dB,alimiter=limit={db(-2.3):.4f}:attack=1:release=30:level=false",
                        "-c:a", "pcm_s16le", "-ar", str(SR), mix_path], check=True)
        I, TP = ebur(mix_path)
        if abs(I + 14.0) < 0.1:
            break
        gain += -14.0 - I
    os.remove(raw_path)
    pre_pk = 20 * np.log10(np.max(np.abs(mix))) + gain
    print(f"pre-level: raw mix {I0:.1f} LUFS -> gain {gain:+.1f} dB + limiter -2.3 dBFS -> {I:.1f} LUFS, TP {TP:.1f} dBTP "
          f"(sent-A hit peak reduced {max(0.0, pre_pk + 2.3):.1f} dB; everything else under the limit)")
    lv = subprocess.run(["ffmpeg", "-v", "error", "-i", mix_path, "-f", "f32le", "-"], capture_output=True).stdout
    mix = np.frombuffer(lv, np.float32).reshape(-1, 2)
    tail = mix[int(math.ceil(last_end * SR)):]
    print(f"CUSTOM SFX events (sent-A hit at +{hit:.3f} s in the file, aligned to land + 1 frame):\n"
          + "\n".join(log))
    print(f"mix: {mix_path}  peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS; last land {last_land:.3f} s, "
          f"tone ends {last_end:.3f} s, after that max {20 * np.log10(np.max(np.abs(tail)) + 1e-30):.0f} dBFS")
    return mix_path


def main():
    spec_path = sys.argv[1]
    spec = normalize_timing(json.load(open(spec_path, encoding="utf-8")))
    preset = spec.get("sfxPreset") or "soft"
    spec["sfxPreset"] = preset
    if preset not in ("custom", "classic", "soft"):
        sys.exit(f"unknown sfxPreset {preset!r} (use soft (default), classic, custom)")
    print(f"SFX preset: {preset}" + ("  (your files in assets/textthread/custom/)" if preset == "custom" else "  (synthesized, royalty-free)"))
    if preset == "custom":
        missing = [n for n in ("sent.mp3", "received.mp3", "typing.mp3") if not os.path.exists(os.path.join(PICKED, n))]
        if missing:
            sys.exit(f"sfxPreset custom: missing {', '.join(missing)} in {PICKED} (see the docstring at the top of this file)")
        dur = float(spec["duration"])
        out_dir = os.path.join(ROOT, spec.get("output", {}).get("dir", f"out/{spec['name']}"))
        stem = os.path.join(out_dir, spec.get("output", {}).get("name", spec["name"]))
        os.makedirs(os.path.join(out_dir, "sfx"), exist_ok=True)
        mux(stem, main_picked(spec, dur, out_dir, stem), dur)
        return
    dur = float(spec["duration"])
    out_dir = os.path.join(ROOT, spec.get("output", {}).get("dir", f"out/{spec['name']}"))
    stem = os.path.join(out_dir, spec.get("output", {}).get("name", spec["name"]))
    os.makedirs(ASSETS, exist_ok=True); os.makedirs(os.path.join(out_dir, "sfx"), exist_ok=True)

    soft = spec.get("sfxPreset") == "soft"
    if soft:
        os.makedirs(ASSETS_SOFT, exist_ok=True)
        snd = {"send_swoosh": swoosh_soft(), "tri_ding": tri_ding_soft()}
        for i in range(6):
            snd[f"key_tap_{i + 1}"] = key_tap_soft(i)
        for k, v in snd.items():
            write_wav(os.path.join(ASSETS_SOFT, f"{k}.wav"), v)
        # v1 classic: swoosh -7, ding -8, tap -21 dB. Soft: 8 / 8 / 10 dB lower (pre-loudnorm design level).
        G = {"send_swoosh": db(-15), "tri_ding": db(-16), "tap": db(-31)}
    else:
        snd = {"send_swoosh": swoosh(), "tri_ding": tri_ding()}
        for i in range(6):
            snd[f"key_tap_{i + 1}"] = key_tap(i)
        for k, v in snd.items():
            write_wav(os.path.join(ASSETS, f"{k}.wav"), v)
        G = {"send_swoosh": db(-7), "tri_ding": db(-8), "tap": db(-21)}
    rng = np.random.default_rng(24)
    events, log = [], []
    prev_land = None
    for m in spec["messages"]:
        at = m["at"]; af = jsround(at * FPS); land = af / FPS
        L = len(m["text"])
        if m["from"] == "them":
            tf = jsround((at - m.get("typing", 0.5)) * FPS)
            t0, t1 = tf / FPS + 0.08, land - 0.12       # under the dots, clear of the ding
        else:
            lead = min(1.0, 0.25 + 0.006 * L)            # short lines: a couple of taps; long: a busier burst
            t0 = max(land - lead, (prev_land + 0.45) if prev_land is not None else 0.0)
            t1 = land - 0.12                              # end before the swoosh
        if soft:
            if m["from"] == "me":  # shorter pre-gap burst: 1-2 taps on short lines, max 4 on long ones
                t0 = max(land - min(0.8, 0.3 + 0.004 * L), t0)
                cap = 1 if L <= 12 else 2 if L <= 30 else 3 if L <= 60 else 4
            else:
                cap = 3 if (t1 - t0) < 0.6 else 4
            taps = tap_times_soft(rng, t0, t1, cap) if t1 > t0 else []
            if m["from"] == "me" and not taps and t1 - t0 > 0.02:
                taps = [t0]
        else:
            dens = 1.0 + min(0.35, L / 400)
            taps = tap_times(rng, t0, t1, dens) if t1 > t0 else []
            if m["from"] == "me" and len(taps) < 2 and t1 - t0 > 0.05:
                taps = [t0, min(t1, t0 + 0.11)]
        for tt in taps:
            events.append((tt, f"key_tap_{rng.integers(1, 7)}", G["tap"] * rng.uniform(0.6 if soft else 0.7, 1.0)))
        kind = "send_swoosh" if m["from"] == "me" else "tri_ding"
        events.append((land, kind, G[kind]))
        log.append(f"  {'BLUE' if m['from'] == 'me' else 'GREY'} land {land:6.2f} {kind:11s} taps {len(taps):2d} "
                   f"({t0:5.2f}-{t1:5.2f})  {m['text'][:44]!r}")
        prev_land = land

    mix = np.zeros(int(round(dur * SR)) + 2 * SR)
    for tt, k, g in events:
        s = int(round(tt * SR)); x = snd[k] * g
        mix[s:s + len(x)] += x
    mix = mix[: int(round(dur * SR))]
    last_land = max(e[0] for e in events if not e[1].startswith("key_tap"))
    tail = mix[int((last_land + 1.1) * SR):]
    stereo = np.repeat(mix[:, None], 2, axis=1).reshape(-1)
    mix_path = os.path.join(out_dir, "sfx", os.path.basename(stem) + "-sfx-mix.wav")
    write_wav(mix_path, stereo, ch=2)
    print("CLASSIC SFX events:\n" + "\n".join(log))
    print(f"taps: {sum(1 for e in events if e[1].startswith('key_tap'))}  mix: {mix_path}  "
          f"peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS, after last land+1.1 s max "
          f"{20 * np.log10(np.max(np.abs(tail)) + 1e-12):.0f} dBFS")

    mux(stem, mix_path, dur)


def mux(stem, mix_path, dur):
    silent = stem + "-shorts_silent.mp4"; shorts = stem + "-shorts.mp4"
    if not os.path.exists(silent):
        shutil.copy2(shorts, silent)
    tmp = stem + "-shorts.tmp_mux.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", mix_path, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{dur}", tmp], check=True)
    os.replace(tmp, shorts)
    print(f"muxed: {shorts} (picture stream-copied from {os.path.basename(silent)})")


if __name__ == "__main__":
    main()
