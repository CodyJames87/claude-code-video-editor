#!/usr/bin/env python3
"""Transcript JSON + your picks -> clean segment list (sentence-snapped, silences/filler trimmed).

Usage:
  python scripts/cutlist.py --transcript words.json --pick 93.2-130.0 [--pick ...] -o cut.json
  python scripts/cutlist.py --transcript words.json --picks picks.json -o cut.json

Transcript formats accepted (auto-detected):
  - normalized: {"words":[{"text":"Hello","start":0.1,"end":0.4,"speaker":"S1"}]}
  - ElevenLabs STT: {"words":[{"text":..,"start":..,"end":..,"type":"word"|"spacing"|"audio_event","speaker_id":..}]}
  - Whisper / faster-whisper: {"segments":[{"words":[{"word":..,"start":..,"end":..}]}]}
  - Descript-like / generic list: [{"word"|"text":..,"start"|"start_time":..,"end"|"end_time":..}]  (ms auto-detected)
picks.json: [{"id":1,"start":93.2,"end":130.0,"title":"..."}] (times in SOURCE seconds)

Output (times in SOURCE seconds for segments; captions_words in OUTPUT/timeline seconds):
  {"source_duration":..,"picks":[{"id":..,"segments":[{"start":..,"end":..}],"duration":..,
    "text":"...","words":[{"text","start","end"}  (source time)]}]}
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffutil as fu

FILLERS = {"um", "uh", "uhm", "umm", "erm", "er", "ah", "hmm", "mm", "mhm"}
SENT_END = re.compile(r"[.!?]['\")\]]*$")


def normalize_words(data):
    raw = []
    if isinstance(data, dict) and "segments" in data and not data.get("words"):
        for s in data["segments"]:
            raw.extend(s.get("words") or [])
    elif isinstance(data, dict) and "words" in data:
        raw = data["words"]
    elif isinstance(data, dict) and "transcript" in data:
        return normalize_words(data["transcript"])
    elif isinstance(data, list):
        raw = data
    words = []
    for w in raw:
        if w.get("type") and w["type"] != "word":
            continue
        t = (w.get("text") or w.get("word") or w.get("punctuated_word") or "").strip()
        if not t:
            continue
        s = w.get("start", w.get("start_time", w.get("startTime")))
        e = w.get("end", w.get("end_time", w.get("endTime")))
        if s is None or e is None:
            continue
        words.append({"text": t, "start": float(s), "end": float(e),
                      "speaker": w.get("speaker") or w.get("speaker_id")})
    if words and max(w["end"] for w in words) > 20000:  # milliseconds
        for w in words:
            w["start"] /= 1000.0; w["end"] /= 1000.0
    words.sort(key=lambda w: w["start"])
    return words


def is_filler(t):
    return re.sub(r"[^a-z]", "", t.lower()) in FILLERS


def snap(words, start, end, tol):
    """Snap start to a sentence start and end to a sentence end, within +/- tol seconds."""
    idx = [i for i, w in enumerate(words) if w["end"] > start - tol and w["start"] < end + tol]
    if not idx:
        raise SystemExit(f"no words between {start} and {end}")
    # sentence starts: first word or word after a sentence-ending word
    starts = [i for i in idx if i == 0 or SENT_END.search(words[i - 1]["text"])]
    cand = [i for i in starts if abs(words[i]["start"] - start) <= tol]
    si = min(cand, key=lambda i: abs(words[i]["start"] - start)) if cand else \
        min(idx, key=lambda i: abs(words[i]["start"] - start))
    ends = [i for i in idx if SENT_END.search(words[i]["text"]) and i >= si]
    cand = [i for i in ends if abs(words[i]["end"] - end) <= tol]
    ei = min(cand, key=lambda i: abs(words[i]["end"] - end)) if cand else \
        max([i for i in idx if words[i]["end"] <= end + 0.05] or [idx[-1]])
    return si, max(si, ei), bool(starts and cand)


def build_segments(words, si, ei, max_gap, pad, drop_fillers, min_seg):
    keep = [w for w in words[si:ei + 1] if not (drop_fillers and is_filler(w["text"]))]
    if not keep:
        return [], []
    segs = []
    cur = {"start": keep[0]["start"] - pad, "end": keep[0]["end"] + pad}
    for prev, w in zip(keep, keep[1:]):
        gap = w["start"] - prev["end"]
        removed_filler = any(is_filler(x["text"]) for x in words if prev["end"] <= x["start"] < w["start"])
        if gap > max_gap or (drop_fillers and removed_filler and gap > 0.12):
            cur["end"] = prev["end"] + pad
            segs.append(cur)
            cur = {"start": w["start"] - pad, "end": w["end"] + pad}
        else:
            cur["end"] = w["end"] + pad
    segs.append(cur)
    # merge overlaps / tiny segments
    out = []
    for s in segs:
        s["start"] = max(0.0, s["start"])
        if out and s["start"] <= out[-1]["end"] + 0.02:
            out[-1]["end"] = max(out[-1]["end"], s["end"])
        elif out and s["end"] - s["start"] < min_seg:
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    for s in out:
        s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
    return out, keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--pick", action="append", default=[], help="START-END in seconds or mm:ss")
    ap.add_argument("--picks", help="picks JSON file")
    ap.add_argument("--snap-tol", type=float, default=2.0, help="sentence snap window (s)")
    ap.add_argument("--max-gap", type=float, default=0.45, help="cut silences longer than this (s)")
    ap.add_argument("--pad", type=float, default=0.08, help="breathing room around words (s)")
    ap.add_argument("--keep-fillers", action="store_true")
    ap.add_argument("--min-seg", type=float, default=0.35)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    words = normalize_words(fu.load_json(a.transcript))
    if not words:
        raise SystemExit("transcript has no timed words")

    def ts(x):
        x = x.strip()
        if ":" in x:
            p = [float(v) for v in x.split(":")]
            return sum(v * 60 ** i for i, v in enumerate(reversed(p)))
        return float(x)

    picks = []
    if a.picks:
        picks = fu.load_json(a.picks)
    for i, p in enumerate(a.pick):
        s, e = re.split(r"(?<=\d)-(?=\d)", p)
        picks.append({"id": len(picks) + 1, "start": ts(s), "end": ts(e)})
    if not picks:
        raise SystemExit("give --pick or --picks")

    res = {"transcript": os.path.abspath(a.transcript), "source_duration": words[-1]["end"], "picks": []}
    for p in picks:
        si, ei, snapped = snap(words, float(p["start"]), float(p["end"]), a.snap_tol)
        segs, kept = build_segments(words, si, ei, a.max_gap, a.pad, not a.keep_fillers, a.min_seg)
        dur = round(sum(s["end"] - s["start"] for s in segs), 3)
        res["picks"].append({
            "id": p.get("id"), "title": p.get("title"),
            "requested": [p["start"], p["end"]],
            "snapped": [round(words[si]["start"], 3), round(words[ei]["end"], 3)],
            "sentence_snapped": snapped,
            "segments": segs, "duration": dur,
            "removed_seconds": round(words[ei]["end"] - words[si]["start"] - dur, 3),
            "text": " ".join(w["text"] for w in kept),
            "words": [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in kept],
        })
    fu.save_json(res, a.out)
    for p in res["picks"]:
        print(f"pick {p['id']}: {p['snapped'][0]:.2f}-{p['snapped'][1]:.2f}s -> {len(p['segments'])} segments, "
              f"{p['duration']:.2f}s (trimmed {p['removed_seconds']:.2f}s), sentence_snapped={p['sentence_snapped']}")
        print("  " + p["text"][:200])
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
