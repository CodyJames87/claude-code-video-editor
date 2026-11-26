#!/usr/bin/env python3
"""(Re)generate the two royalty-free SFX the editor uses: public/sfx/whoosh.wav and public/sfx/pop.wav.

Both are synthesized here with numpy (filtered noise sweep / a short decaying sine), so they are original and
free to use. Peak-normalized to -3 dBFS; the edit plays them at sfx.whooshDb / sfx.popDb.
Swap in your own files with the same names to change the sound (only use sounds you are licensed to use).
Usage: python helpers/make_sfx.py
"""
import os, wave
import numpy as np

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "sfx")


def save(name, x):
    x = x / (np.max(np.abs(x)) + 1e-9) * 10 ** (-3 / 20)
    with wave.open(os.path.join(OUT, name), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def whoosh(dur=0.9):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = np.random.default_rng(3).standard_normal(n)
    # sweep a one-pole low-pass cutoff up then down -> "air moving past"
    fc = 300 + 3200 * np.sin(np.pi * t / dur) ** 2
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros(n); prev = 0.0
    for i in range(n):
        prev = (1 - a[i]) * noise[i] + a[i] * prev
        y[i] = prev
    env = np.sin(np.pi * t / dur) ** 1.5
    return y * env


def pop(dur=0.18):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 900 * np.exp(-t * 18) + 220
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 28) * np.minimum(1, t / 0.002)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    save("whoosh.wav", whoosh()); save("pop.wav", pop())
    print(f"wrote {OUT}/whoosh.wav and pop.wav")
