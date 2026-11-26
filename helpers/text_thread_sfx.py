#!/usr/bin/env python3
"""Text Thread SFX pass: synthesize subtle UI pops + typing ticks (numpy only, original sounds, no Apple audio),
mix them to the exact bubble frames of a threads/<name>.json spec, and mux the mix onto the existing picture.

Usage: python helpers/text_thread_sfx.py threads/<name>.json
  - Sounds -> assets/textthread/{pop_out,pop_in,tick}.wav (48 kHz mono, peak -3 dBFS, synthesized here).
  - Mix    -> <output.dir>/sfx/<stem>-sfx-mix.wav (stereo 48 kHz, spec duration).
  - Picture: <stem>-shorts_silent.mp4 (the Remotion render, kept untouched; created from <stem>-shorts.mp4 on first run)
    + the mix -> <stem>-shorts.mp4 (video stream copied, AAC 192k). Then run finish.mjs WITH loudnorm.
Timing mirrors src/textthread/timeline.ts: appearFrame = round(at*fps), typingFrame = round((at - typing)*fps);
typing ticks follow the three dots' pulse (sin(2*pi*1.6*t - k*0.9) peaks), only inside "them" typing windows.
"""
import json, math, os, shutil, subprocess, sys, wave
import numpy as np

SR, FPS = 48000, 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "textthread")
jsround = lambda x: int(math.floor(x + 0.5))  # JS Math.round


def write_wav(path, x, ch=1):
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def peak_norm(x, db=-3.0):
    return x / np.max(np.abs(x)) * 10 ** (db / 20)


def lowpass(x, fc):  # one-pole, numpy only
    a = math.exp(-2 * math.pi * fc / SR); y = np.empty_like(x); s = 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s; y[i] = s
    return y


def pop(f0, f1, sweep, tau, length, attack, click):
    """Soft bubble 'blip': a short downward pitch glide into a decaying sine, a tiny filtered click at the onset."""
    n = int(length * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / sweep)                 # glide f0 -> f1
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) + 0.18 * np.sin(2 * ph)                # a little 2nd harmonic = rounder, less beepy
    env = np.minimum(1, t / attack) * np.exp(-t / tau)
    fade = np.ones(n); k = int(0.012 * SR); fade[-k:] = np.linspace(1, 0, k)
    rng = np.random.default_rng(7)
    c = lowpass(rng.standard_normal(n), 3500) * np.exp(-t / 0.004) * click
    return peak_norm((body * env + c) * fade)


def tick():
    """Quiet typing tick: 10 ms band-limited noise blip."""
    n = int(0.03 * SR); t = np.arange(n) / SR
    rng = np.random.default_rng(3)
    x = lowpass(rng.standard_normal(n), 4500); x = x - lowpass(x, 1200)   # ~1.2-4.5 kHz band
    x *= np.minimum(1, t / 0.0008) * np.exp(-t / 0.006)
    return peak_norm(x)


def main():
    spec_path = sys.argv[1]
    spec = json.load(open(spec_path, encoding="utf-8"))
    dur = float(spec["duration"])
    out_dir = os.path.join(ROOT, spec.get("output", {}).get("dir", f"out/{spec['name']}"))
    stem = os.path.join(out_dir, spec.get("output", {}).get("name", spec["name"]))
    os.makedirs(ASSETS, exist_ok=True); os.makedirs(os.path.join(out_dir, "sfx"), exist_ok=True)

    # --- synthesize (outgoing: higher + tighter; incoming: lower + softer) ---
    snd = {
        "pop_out": pop(f0=1500, f1=980, sweep=0.012, tau=0.12, length=0.50, attack=0.0025, click=0.2),
        "pop_in": pop(f0=1000, f1=640, sweep=0.016, tau=0.15, length=0.55, attack=0.005, click=0.1),
        "tick": tick(),
    }
    for k, v in snd.items():
        write_wav(os.path.join(ASSETS, f"{k}.wav"), v)

    # --- event list from the spec (same rounding as timeline.ts) ---
    GAIN = {"pop_out": 10 ** (-6 / 20), "pop_in": 10 ** (-8 / 20), "tick": 10 ** (-24 / 20)}
    events, log = [], []
    for m in spec["messages"]:
        af = jsround(m["at"] * FPS)
        if m["from"] == "them":
            tf = jsround((m["at"] - m.get("typing", 0.5)) * FPS)
            t0, t1 = tf / FPS, af / FPS
            ticks = []
            for k in range(3):  # each dot pulses at 1.6 Hz, offset 0.9 rad
                nmax = int((t1 - t0) * 1.6) + 2
                for n in range(nmax):
                    lt = (math.pi / 2 + k * 0.9 + 2 * math.pi * n) / (2 * math.pi * 1.6)
                    if 0.06 <= lt <= (t1 - t0) - 0.08:   # stay clear of the dots growing in / the landing pop
                        ticks.append(t0 + lt)
            ticks.sort()
            for i, tt in enumerate(ticks):  # tiny level variation so it doesn't sound mechanical
                events.append((tt, "tick", GAIN["tick"] * (0.85 + 0.3 * ((i * 37) % 10) / 10)))
            log.append(f"  typing {t0:5.2f}-{t1:5.2f}  {len(ticks)} ticks")
        events.append((af / FPS, "pop_out" if m["from"] == "me" else "pop_in", GAIN["pop_out" if m["from"] == "me" else "pop_in"]))
        log.append(f"  land   {af / FPS:5.2f} (f{af})  {'pop_out' if m['from'] == 'me' else 'pop_in'}  {m['text']!r}")

    mix = np.zeros(int(round(dur * SR)) + SR)
    for tt, k, g in events:
        s = int(round(tt * SR)); x = snd[k] * g
        mix[s:s + len(x)] += x[: len(mix) - s]
    mix = mix[: int(round(dur * SR))]
    last_land = max(e[0] for e in events if e[1] != "tick")
    tail = mix[int((last_land + 0.4) * SR):]
    stereo = np.repeat(mix[:, None], 2, axis=1).reshape(-1)
    mix_path = os.path.join(out_dir, "sfx", os.path.basename(stem) + "-sfx-mix.wav")
    write_wav(mix_path, stereo, ch=2)
    print("SFX events:\n" + "\n".join(log))
    print(f"mix: {mix_path}  peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS, "
          f"after last land+0.4 s max {20 * np.log10(np.max(np.abs(tail)) + 1e-12):.0f} dBFS")

    # --- mux onto the untouched picture ---
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
