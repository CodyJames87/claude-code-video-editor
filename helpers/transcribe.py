#!/usr/bin/env python3
"""Local word-level transcript fallback (faster-whisper). Prefer Descript or ElevenLabs STT connectors.

Usage: python scripts/transcribe.py INPUT -o words.json [--model base.en] [--install]
Writes normalized {"words":[{"text","start","end"}], "text": "..."} that cutlist.py/render.py read.
Model weights download from huggingface.co; if the sandbox blocks it, use a connector instead.
"""
import argparse, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--install", action="store_true", help="pip install faster-whisper if missing")
    a = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        if not (a.install and fu._pip_install("faster-whisper")):
            raise SystemExit("faster-whisper not available. Use --install, or the Descript / ElevenLabs "
                             "speech-to-text connector and save its word timings as JSON.")
        from faster_whisper import WhisperModel
    wav = os.path.join(tempfile.mkdtemp(), "a.wav")
    fu.run([fu.find_ffmpeg(), "-y", "-v", "error", "-i", a.input, "-vn", "-ac", "1", "-ar", "16000", wav])
    # decode ourselves (avoids PyAV version issues): 16 kHz mono s16 -> float32
    import wave, numpy as np
    with wave.open(wav) as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, info = model.transcribe(audio, word_timestamps=True, vad_filter=False)
    words = []
    for s in segs:
        for w in s.words or []:
            words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                          "prob": round(w.probability, 3)})
    out = {"source": os.path.abspath(a.input), "engine": f"faster-whisper:{a.model}",
           "language": info.language, "words": words, "text": " ".join(w["text"] for w in words)}
    fu.save_json(out, a.out)
    print(f"{len(words)} words -> {a.out}")
    print(out["text"][:600])


if __name__ == "__main__":
    main()
