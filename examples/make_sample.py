#!/usr/bin/env python3
"""Make a tiny SAMPLE clip so you can test the whole pipeline before using your own footage.

Writes (all generated here, nothing downloaded):
  public/media/sample.mp4            1080x1920, 30 fps, ~13 s: a plain backdrop + a thin frame guide (no fake face), and a
                                     synthetic "voice" (soft tone bursts, one per word) so loudness / QA checks have audio
  public/media/sample.captions.json  word-level captions that line up with those bursts (what a transcript would give you)

Then:  npx remotion render ShortsVideo out/sample-shorts.mp4 --props=examples/sample.props.json
Usage (from the repo root): python examples/make_sample.py   (or: npm run sample)
"""
import json, math, os, subprocess, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "public", "media")
SR, FPS, W, H = 48000, 30, 1080, 1920

SCRIPT = ("I don't edit my videos anymore. Claude Code does the edit and I just review it. "
          "This clip was 100% edited by AI. Comment EDIT and I'll send you the free guide.")


def words_with_times(text, start=0.35):
    out, t = [], start
    for i, w in enumerate(text.split()):
        dur = 0.16 + 0.045 * len(w.strip(".,'%"))
        out.append({"text": (" " if i else "") + w, "startMs": round(t * 1000), "endMs": round((t + dur) * 1000)})
        t += dur + (0.42 if w.endswith(".") else 0.07)
    return out, t + 0.6


def synth_voice(words, total):
    n = int(total * SR)
    x = np.zeros(n)
    rng = np.random.default_rng(7)
    for i, w in enumerate(words):
        a, b = int(w["startMs"] / 1000 * SR), int(w["endMs"] / 1000 * SR)
        t = np.arange(b - a) / SR
        f0 = 140 + 25 * math.sin(i * 0.9)
        tone = sum(np.sin(2 * math.pi * f0 * k * t) / k for k in range(1, 6))
        env = np.sin(np.pi * np.clip(t / max(t[-1], 1e-3), 0, 1)) ** 0.6
        x[a:b] += 0.25 * tone * env + 0.01 * rng.standard_normal(b - a) * env
    return x / (np.max(np.abs(x)) + 1e-9) * 0.5


def main():
    os.makedirs(MEDIA, exist_ok=True)
    words, total = words_with_times(SCRIPT)
    wav = os.path.join(MEDIA, "sample.voice.wav")
    pcm = (synth_voice(words, total) * 32767).astype("<i2")
    with wave.open(wav, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm.tobytes())
    mp4 = os.path.join(MEDIA, "sample.mp4")
    # backdrop + a simple "person" silhouette (head + shoulders) so framing / crops are easy to see
    vf = ("drawbox=x=0:y=0:w=iw:h=ih:color=0x2B3A4A@1:t=fill,"
          # a gradient-ish lower half + a thin frame guide where a speaker's head would sit (no fake face:
          # the face detector should honestly report "no face" on this clip)
          "drawbox=x=0:y=1100:w=iw:h=820:color=0x34475A@1:t=fill,"
          "drawbox=x=360:y=420:w=360:h=560:color=0x8FA3B8@0.6:t=3,"
          "noise=alls=7:allf=t")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={total:.2f}",
           "-i", wav, "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", mp4]
    subprocess.run(cmd, check=True)
    os.remove(wav)
    with open(os.path.join(MEDIA, "sample.captions.json"), "w", encoding="utf-8") as f:
        json.dump([dict(w, timestampMs=w["startMs"], confidence=1) for w in words], f, indent=1)
    print(f"sample: {mp4} ({total:.2f} s), captions: public/media/sample.captions.json ({len(words)} words)")
    print("next: npx remotion render ShortsVideo out/sample-shorts.mp4 --props=examples/sample.props.json")


if __name__ == "__main__":
    sys.exit(main())
