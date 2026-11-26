#!/usr/bin/env python3
"""EDL remap: when pacing / cuts change, re-time captions, SFX, highlights and motion overlays so they stay on the
same spoken words. Writes a NEW props file (and a new captions file); never overwrites the input.

  python helpers/remap_edl.py --props props/<name>.json --edl <changes.json> --out props/<name>.<tag>.json
         [--captions-out public/media/<name>.<tag>.captions.json] [--recut-media [public/media/<name>.<tag>.mp4]]
         [--report out/.../remap_report.md]

EDL (all times in SOURCE seconds = the media file / captions JSON clock, i.e. props timeline + trim.start):
  {"ops": [
     {"op": "delete", "from": 3.03, "to": 3.43, "note": "dead air after 'years.'"},
     {"op": "insert", "at": 20.0, "duration": 0.5, "fill": "freeze" | "black", "note": "..."},
     {"op": "trim",   "start": 1.0, "end": 35.0}          # new in/out ("changed this start")
  ]}
  or a keep list: {"keep": [{"start", "end"}, ...]} / helpers/cutlist.py output (picks[0].segments).

What moves:
  overlays[].at  word anchors keep {word, offset}; the word is followed through the cut and `occurrence` is rewritten
                 if an earlier copy of the word was deleted. Numeric `at` is mapped (snapped forward if it fell in a
                 deleted range). `duration` = mapped end - mapped start (shrinks when a deletion lands inside).
  captions       words in deleted ranges are dropped, the rest re-timed (new captions JSON on the NEW clock).
                 bottomRanges / oneLineRanges from/to mapped; moneyWords must still be spoken (else exit 3).
  sfx.events     same as overlay anchors.  SpeedRamp sourceStart/sourceEnd mapped.
  hook           the Hook Caption (first 2.0 s of words) or hook card must survive intact (else exit 3).
  trim           a pure trim (deletes only at the head/tail) keeps the media and moves props.trim; anything else
                 needs re-cut media: --recut-media writes it with ffmpeg (4 ms audio fades at every splice) and the
                 new props point at it with trim = null. Without --recut-media the report says which media to make.
Exit: 0 = mapped (read the warnings), 3 = a money word or the hook could not be mapped, 2 = bad input.
The tool cannot invent a missing word: an anchor whose word was cut is reported UNMAPPED for a human to fix.
"""
import argparse, copy, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import props_util as pu  # noqa: E402

HOOK_SEC = 2.0
FADE = 0.004


def media_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def subtract(segs, a, b):
    out = []
    for s, e in segs:
        if b <= s or a >= e:
            out.append((s, e))
            continue
        if s < a:
            out.append((s, a))
        if b < e:
            out.append((b, e))
    return out


def build_pieces(edl, src0, src1):
    """-> ordered pieces: ("keep", a, b) in source s or ("insert", at, dur, fill)."""
    if isinstance(edl, dict) and edl.get("picks"):
        keeps = [(s["start"], s["end"]) for s in edl["picks"][0]["segments"]]
        inserts = []
    elif isinstance(edl, dict) and edl.get("keep"):
        keeps = [(s["start"], s["end"]) for s in edl["keep"]]
        inserts = []
    else:
        ops = edl.get("ops", []) if isinstance(edl, dict) else edl
        keeps = [(src0, src1)]
        inserts = []
        for op in ops:
            k = op.get("op")
            if k == "delete":
                keeps = subtract(keeps, float(op["from"]), float(op["to"]))
            elif k == "trim":
                a = float(op.get("start", src0))
                b = float(op.get("end", src1) or src1)
                keeps = [(max(s, a), min(e, b)) for s, e in keeps if min(e, b) > max(s, a)]
            elif k == "insert":
                inserts.append((float(op["at"]), float(op["duration"]), op.get("fill", "freeze")))
            else:
                raise SystemExit(f"unknown op {op}")
    keeps = [(s, e) for s, e in sorted(keeps) if e - s > 1e-3]
    pieces = []
    for s, e in keeps:
        cur = s
        for at, d, fill in sorted(inserts):
            if cur < at < e:
                pieces.append(("keep", cur, at))
                pieces.append(("insert", at, d, fill))
                cur = at
        pieces.append(("keep", cur, e))
    for at, d, fill in sorted(inserts):  # inserts at a piece boundary / the very start or end
        if not any(p[0] == "insert" and p[1] == at for p in pieces):
            idx = next((i for i, p in enumerate(pieces) if p[0] == "keep" and p[1] >= at), len(pieces))
            pieces.insert(idx, ("insert", at, d, fill))
    return pieces


class Mapper:
    def __init__(self, pieces):
        self.spans = []  # (src_a, src_b, new_a)
        n = 0.0
        for p in pieces:
            if p[0] == "keep":
                self.spans.append((p[1], p[2], n))
                n += p[2] - p[1]
            else:
                n += p[2]
        self.total = n

    def map(self, s, snap="forward"):
        """source s -> new s. Returns (new, how): how = 'ok' | 'snapped-forward' | 'snapped-back' | 'past-end'."""
        for a, b, n in self.spans:
            if a - 1e-6 <= s <= b + 1e-6:
                return n + (s - a), "ok"
        if not self.spans:
            return None, "empty"
        if s > self.spans[-1][1]:
            a, b, n = self.spans[-1]
            return n + (b - a) + (s - b), "past-end"
        if s < self.spans[0][0]:
            return self.spans[0][2], "snapped-forward"
        if snap == "forward":
            nxt = min((sp for sp in self.spans if sp[0] > s), key=lambda sp: sp[0])
            return nxt[2], "snapped-forward"
        prv = max((sp for sp in self.spans if sp[1] < s), key=lambda sp: sp[1])
        return prv[2] + (prv[1] - prv[0]), "snapped-back"

    def kept(self, s0, s1, edge=0.02):
        """is the source span [s0, s1] (a word) wholly inside ONE kept span?"""
        return any(a - edge <= s0 and s1 <= b + edge for a, b, _ in self.spans)


def main():
    ap = argparse.ArgumentParser(description="Remap props + captions through an edit change (see docstring).")
    ap.add_argument("--props", required=True)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--out", required=True, help="NEW props file (must differ from --props)")
    ap.add_argument("--captions-out")
    ap.add_argument("--recut-media", nargs="?", const="auto", default=None)
    ap.add_argument("--report")
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.props):
        print("refusing to overwrite the input props: pick a new --out", file=sys.stderr)
        sys.exit(2)
    props = pu.load_props(a.props)
    caps = pu.load_captions(props.get("transcriptJson"))
    edl = pu.load_json(a.edl)
    trim0 = pu.trim_start(props)
    src_media = pu.public_path(props["videoSrc"])
    mdur = media_duration(src_media) or (caps[-1]["endMs"] / 1000 if caps else 0)
    tr = props.get("trim") or {}
    src0, src1 = trim0, float(tr.get("end") or mdur)
    pieces = build_pieces(edl, src0, src1)
    M = Mapper(pieces)
    keeps = [p for p in pieces if p[0] == "keep"]
    pure_trim = len(keeps) == 1 and not any(p[0] == "insert" for p in pieces)
    rows, errors, warns = [], [], []
    new = copy.deepcopy({k: v for k, v in props.items() if not k.startswith("_")})
    stem = os.path.splitext(os.path.basename(a.out))[0]

    # ---- captions: follow every word
    old_to_new_idx, new_caps = {}, []
    for i, c in enumerate(caps):
        s0, s1 = c["startMs"] / 1000, c["endMs"] / 1000
        if s1 <= src0 + 1e-3 or s0 >= src1 - 1e-3:
            continue
        if not M.kept(s0, s1):
            cut = any(a_ < s1 and s0 < b_ for a_, b_, _ in M.spans)
            (warns if cut else rows).append(
                f'caption word "{c["text"].strip()}" at {s0:.2f}s ' + ("is CLIPPED by a cut (partly kept): dropped from captions, check the audio" if cut else "deleted with its range"))
            if not cut:
                rows.pop()
            continue
        n0, _ = M.map(s0)
        n1, _ = M.map(s1)
        nc = dict(c)
        if pure_trim:
            nc["startMs"], nc["endMs"] = c["startMs"], c["endMs"]   # source clock kept, props.trim moves instead
        else:
            nc["startMs"], nc["endMs"] = round(n0 * 1000), round(n1 * 1000)
            if c.get("timestampMs") is not None:
                nc["timestampMs"] = round((M.map(c["timestampMs"] / 1000)[0] or n0) * 1000)
        old_to_new_idx[i] = len(new_caps)
        new_caps.append(nc)
    dropped = len([c for c in caps if src0 - 1e-3 <= c["startMs"] / 1000 < src1]) - len(new_caps)
    new_t0 = keeps[0][1] if pure_trim else 0.0     # new trim.start (pure trim) or 0 on re-cut media

    def new_time(s_src, snap="forward"):
        n, how = M.map(s_src, snap)
        return (n + new_t0 if pure_trim else n) - new_t0, how   # timeline seconds in the NEW props

    words_new = [pu.norm(c["text"]) for c in new_caps]

    def remap_anchor(at, label):
        """-> (new_at, new_start_tl, status)"""
        if isinstance(at, (int, float)):
            s_src = float(at) + trim0
            nt, how = new_time(s_src)
            return round(nt, 3), nt, ("OK" if how == "ok" else f"MOVED ({how}: its time was cut)")
        t_old, wi = pu.resolve_anchor(at, caps, trim0)
        if wi is None:
            return at, None, "UNMAPPED (anchor word not found even in the OLD captions)"
        target = [pu.norm(t) for t in str(at["word"]).split() if pu.norm(t)]
        idxs = [old_to_new_idx.get(wi + k) for k in range(len(target))]
        if any(x is None for x in idxs) or any(idxs[k + 1] != idxs[k] + 1 for k in range(len(idxs) - 1)):
            return at, None, f'UNMAPPED: "{at["word"]}" was cut (fix by hand; the tool will not invent a word)'
        ni = idxs[0]
        occ = sum(1 for j in range(ni + 1) if all(j + k < len(words_new) and words_new[j + k] == t for k, t in enumerate(target)))
        na = dict(at)
        status = "OK"
        if occ != (at.get("occurrence", 1) or 1):
            status = f"RE-ANCHORED occurrence {at.get('occurrence', 1)} -> {occ}"
        if occ == 1:
            na.pop("occurrence", None)
        else:
            na["occurrence"] = occ
        st = new_caps[ni]["startMs"] / 1000 - (new_t0 if pure_trim else 0) + float(at.get("offset", 0) or 0)
        return na, st, status

    # ---- overlays
    ovs_old = pu.resolved_overlays(props, caps)
    for o_new, o_old in zip(new.get("overlays", []), ovs_old):
        label = f'{o_old["type"]}#{o_old["_i"]}' + (f' "{o_old["at"]["word"]}"' if isinstance(o_old["at"], dict) else "")
        na, nst, status = remap_anchor(o_old["at"], label)
        o_new["at"] = na
        if nst is None:
            errors.append(f"{label}: {status}") if False else warns.append(f"{label}: {status}")
            rows.append({"item": label, "old": o_old["start"], "new": None, "status": status})
            continue
        if o_old["start"] is not None:
            end_src = o_old["start"] + float(o_old.get("duration", 0)) + trim0
            nend, how = new_time(end_src, snap="back")
            nd = round(max(1 / 30, nend - nst), 3)
            if abs(nd - float(o_old.get("duration", 0))) > 0.005:
                status += f"; duration {o_old['duration']} -> {nd}" + (" (a cut lands inside the window)" if how == "ok" else f" ({how})")
                o_new["duration"] = nd
            p = o_new.get("props", {})
            if o_old["type"] == "SpeedRamp" and "sourceStart" in p and not p.get("src"):
                p["sourceStart"] = round(new_time(p["sourceStart"])[0] + new_t0, 3)
                p["sourceEnd"] = round(new_time(p["sourceEnd"], "back")[0] + new_t0, 3)
            if o_old["type"] == "CountUpCard":
                land = o_old["start"] + float(p.get("landSec", 0.4)) + trim0
                if not M.kept(o_old["start"] + trim0, land):
                    warns.append(f"{label}: a cut lands between the card start and its landing (landSec): check the count lands on the word")
        rows.append({"item": label, "old": round(o_old["start"], 3), "new": round(nst, 3), "status": status})

    # ---- sfx events
    for ev in ((new.get("sfx") or {}).get("events") or []):
        na, nst, status = remap_anchor(ev["at"], f"sfx {ev.get('kind')}")
        old_t, _ = pu.resolve_anchor(ev["at"], caps, trim0)
        ev["at"] = na
        rows.append({"item": f"sfx {ev.get('kind')}", "old": old_t, "new": nst, "status": status})
        if nst is None:
            warns.append(f"sfx {ev.get('kind')}: {status}")

    # ---- captions ranges + money words
    cc = new.get("captions") or {}
    for key in ("bottomRanges", "oneLineRanges"):
        for r in cc.get(key) or []:
            of, ot = r["from"], r["to"]
            r["from"] = round(new_time(of + trim0, "forward")[0], 3)
            r["to"] = round(new_time(ot + trim0, "back")[0], 3)
            rows.append({"item": f"captions.{key}", "old": f"{of}-{ot}", "new": f'{r["from"]}-{r["to"]}', "status": "OK"})
    old_words = set(pu.norm(c["text"]) for c in caps if src0 - 1e-3 <= c["startMs"] / 1000 < src1)
    for mw in cc.get("moneyWords") or []:
        n = pu.norm(mw)
        if n in old_words and n not in words_new:
            errors.append(f'money word "{mw}" is no longer spoken after the change (all its occurrences were cut)')
            rows.append({"item": f'moneyWord "{mw}"', "old": "spoken", "new": None, "status": "UNMAPPED"})
        else:
            cnt_o = sum(1 for c in caps if pu.norm(c["text"]) == n and src0 - 1e-3 <= c["startMs"] / 1000 < src1)
            cnt_n = words_new.count(n)
            rows.append({"item": f'moneyWord "{mw}"', "old": f"{cnt_o}x", "new": f"{cnt_n}x",
                         "status": "OK" if cnt_o == cnt_n else f"OK ({cnt_o - cnt_n} occurrence(s) cut)"})

    # ---- hook
    if props.get("hook"):
        rows.append({"item": "hook card", "old": 0, "new": 0, "status": "OK (card at 0 s; text is not tied to words)"})
        hw = [pu.norm(w) for w in props["hook"]["text"].split()]
        if not all(w in words_new for w in hw if w):
            warns.append("hook card text words are not all spoken any more: the hook must stay verbatim, check it")
    else:
        hook_idx = [i for i, c in enumerate(caps) if src0 <= c["startMs"] / 1000 < src0 + HOOK_SEC]
        lost = [caps[i]["text"].strip() for i in hook_idx if i not in old_to_new_idx]
        moved = [i for i in hook_idx if i in old_to_new_idx and abs(
            (new_caps[old_to_new_idx[i]]["startMs"] / 1000 - (new_t0 if pure_trim else 0)) - (caps[i]["startMs"] / 1000 - trim0)) > 0.02]
        if lost:
            errors.append(f"Hook Caption words cut: {' '.join(lost)} (the first {HOOK_SEC:.0f} s must survive verbatim)")
            rows.append({"item": "Hook Caption (0-2 s)", "old": "0.0", "new": None, "status": "UNMAPPED"})
        else:
            rows.append({"item": "Hook Caption (0-2 s)", "old": "0.0", "new": "0.0",
                         "status": "OK" if not moved else f"OK but {len(moved)} hook word(s) re-timed: re-check the hook block"})

    # ---- media / captions / trim
    cap_out = a.captions_out or os.path.join(pu.PUBLIC, "media", stem + ".captions.json")
    media_note = None
    if pure_trim:
        new["trim"] = {"start": round(keeps[0][1], 3)} | ({"end": round(keeps[0][2], 3)} if keeps[0][2] < mdur - 0.01 else {})
        cap_out = None  # same captions JSON (source clock)
        media_note = f"pure trim: same media + captions, props.trim = {new['trim']}"
    else:
        pu.save_json(new_caps, cap_out)
        new["transcriptJson"] = os.path.relpath(cap_out, pu.PUBLIC).replace("\\", "/")
        new["trim"] = None
        med = None if a.recut_media is None else (os.path.join(pu.PUBLIC, "media", stem + ".mp4") if a.recut_media == "auto" else a.recut_media)
        if med:
            recut(src_media, pieces, med)
            new["videoSrc"] = os.path.relpath(med, pu.PUBLIC).replace("\\", "/")
            media_note = f"re-cut media written: {med}"
        else:
            new["videoSrc"] = "media/" + stem + ".mp4"
            media_note = (f"NEEDS MEDIA: props now point at public/media/{stem}.mp4; make it with --recut-media "
                          f"(ffmpeg, from the EDL) or re-cut the same ranges in Descript")
    new["_remap"] = {"from_props": os.path.relpath(props["_path"], pu.ROOT), "edl": os.path.relpath(os.path.abspath(a.edl), pu.ROOT),
                     "new_duration_s": round(M.total, 3), "old_duration_s": round(src1 - src0, 3)}
    pu.save_json(new, a.out)

    # ---- spot check: 2 words old -> new
    spots = []
    for i in list(old_to_new_idx)[len(old_to_new_idx) // 3:: max(1, len(old_to_new_idx) // 3)][:2]:
        c, nc = caps[i], new_caps[old_to_new_idx[i]]
        spots.append(f'"{c["text"].strip()}": old {c["startMs"] / 1000 - trim0:.3f}s -> new {nc["startMs"] / 1000 - (new_t0 if pure_trim else 0):.3f}s')
    lines = [f"# Remap report: {os.path.basename(a.props)} -> {os.path.basename(a.out)}", "",
             f"- EDL: `{a.edl}`  pieces: " + ", ".join(f"keep {p[1]:.2f}-{p[2]:.2f}" if p[0] == "keep" else f"insert {p[2]}s {p[3]} @ {p[1]:.2f}" for p in pieces),
             f"- Timeline: {src1 - src0:.3f}s -> {M.total:.3f}s ({M.total - (src1 - src0):+.3f}s); caption words dropped: {dropped}",
             f"- Media: {media_note}",
             f"- New captions: `{cap_out}`" if cap_out else "- Captions: unchanged (source clock)",
             f"- Spot check: " + "; ".join(spots), "",
             "| Item | Old (s) | New (s) | Status |", "|---|---|---|---|"]
    lines += [f"| {r['item']} | {r['old']} | {r['new'] if r['new'] is not None else '-'} | {r['status']} |" for r in rows if isinstance(r, dict)]
    if warns:
        lines += ["", "## Needs a human", ""] + [f"- {w}" for w in warns]
    if errors:
        lines += ["", "## ERRORS (exit 3)", ""] + [f"- {e}" for e in errors]
    lines += ["", f"Result: {'FAIL (money word / hook not mappable)' if errors else 'MAPPED'}. Input props untouched: `{a.props}`.",
              "Next: `node helpers/check-highlights.mjs " + a.out.replace("\\", "/") + "`, preview in Studio, render, finish, qa_gate."]
    rep = a.report or os.path.splitext(a.out)[0] + ".remap_report.md"
    os.makedirs(os.path.dirname(os.path.abspath(rep)), exist_ok=True)
    with open(rep, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {a.out}\nreport {rep}")
    sys.exit(3 if errors else 0)


def recut(src, pieces, out):
    """Concat the kept ranges (+ inserted holds) with 4 ms audio fades at each splice so cuts don't click."""
    fc, labels, n = [], [], 0
    last = None
    for p in pieces:
        if p[0] == "keep":
            a, b = p[1], p[2]
            d = b - a
            fc.append(f"[0:v]trim={a:.4f}:{b:.4f},setpts=PTS-STARTPTS[v{n}]")
            fc.append(f"[0:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,afade=t=in:d={FADE},afade=t=out:st={max(0, d - FADE):.4f}:d={FADE}[a{n}]")
            last = b
        else:
            at, d, fill = p[1], p[2], p[3]
            if fill == "black":
                fc.append(f"[0:v]trim={at:.4f}:{at + 0.04:.4f},setpts=PTS-STARTPTS,drawbox=c=black:t=fill,tpad=stop_mode=clone:stop_duration={d:.4f},trim=0:{d:.4f}[v{n}]")
            else:
                fc.append(f"[0:v]trim={max(0, at - 0.034):.4f}:{at:.4f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={d:.4f},trim=0:{d:.4f},setpts=PTS-STARTPTS[v{n}]")
            fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.4f}[a{n}]")
        labels.append(f"[v{n}][a{n}]")
        n += 1
    fc.append("".join(labels) + f"concat=n={n}:v=1:a=1[v][a]")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map_metadata", "0", "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("re-cut failed: " + r.stderr[-800:])


if __name__ == "__main__":
    main()
