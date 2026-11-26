# Editor Tools

Tools are **helpers around the edit**: they check, preview, re-time and organise. They are not effects and never
add anything to the picture. Effects live in `style/effects-library.md`; this file is the tool catalog in the same
format. All original code on the Python + Remotion stack in this repo (no third-party packs, no public hosting). Names are stable: don't rename them.

| Tool | When | Gate? |
|---|---|---|
| QA Gate | every finished MP4, after `finish.mjs`, before `deliver.py` | **yes, mandatory** (deliver blocks on FAIL) |
| Review Page | every delivered cut you should review frame by frame; each new version | no |
| Style Breakdown | you supply a reference reel file and asks "what does this do / can we do this?" | no (stops and waits) |
| EDL Remap | pacing or cuts change after props were written | exit 3 = a money word / the hook was cut |
| Footage Catalog | finding clips ("where did I talk about pricing?") | no |
| Crop Previews | before a render, to let you pick loose vs tight framing per moment | no (proposals only) |

---

### QA Gate
- **Looks like:** one report (`qa_report.md` / `.json`) with PASS / FAIL / WARN / SKIP per check and an overall
  PASS or FAIL, plus the usual stills + `contact_sheet.jpg` (from `qc_frames.py`) and an annotated
  `face_safe_sheet.jpg` (blue = head incl. cap/chin margins, accent = text boxes, magenta = conflict).
- **Use:** every final, after `node helpers/finish.mjs` and before `deliver.py`. `deliver.py` runs it automatically when
  there is no current report. FAIL blocks delivery. WARN never blocks. It does **not** replace looking at the frames.
- **CLI:** `python helpers/qa_gate.py out/<name>-shorts_final.mp4 --props props/<name>.json [--edl cut.json]
  [--times 1.2,4.5] [--allow-still 30.1-33.0] [--accept-unsure "reason"]` -> `out/.../qa_<stem>/`. Exit 0 PASS, 1 FAIL.
  Deliver: `python helpers/deliver.py <final> [--props ...]`; override only with a reason:
  `--qa-override "reason"` (the FAIL report stays, the reason goes into `review/review-log.json`). `--dry-run` = show only.
- **Checks + thresholds:** black >= 0.20 s; freeze >= 1.0 s outside Takeover / full-screen cards / `tailHoldSec` /
  `--allow-still`; flash = 1-2 frame spike out and back (mean diff >= 40/255); loudness -14 +/-1 LUFS, TP <= -1 dBTP
  (reads `finish.mjs`'s own `<final>.finish.json` verdict when it matches the file, else the same ebur128 measure);
  clipping = flat tops (>= 3 samples at full scale) or TP over the cap; cut seams = clipped word / doubled word /
  splice click at EDL splices, trim in/out (FAIL) and picture-detected jump cuts (WARN); face-safe = `face_safe.py`'s
  detector on the final at every 0.5 s + every punch/push peak + card mids: text box on the padded head = FAIL,
  cap/chin outside the video panel = FAIL, detector UNSURE = FAIL unless `--accept-unsure "reason"` (logged).
- **Built by:** `helpers/qa_gate.py` (+ `helpers/props_util.py`, `helpers/face_safe.py` `detect_at`, `helpers/qc_frames.py`,
  `helpers/finish.mjs` sidecar, `helpers/deliver.py` block/override).
- **QC / limits:** text boxes come from props (approximate, 9:16 only; on 4:5 / 16:9 only cap/chin framing is checked).
  Haar misses faces on profile / gestures (that is why UNSURE fails). Cut seams need a word-timed transcript; without
  `--edl` only the trim + picture jumps are checked. A natural "very, very" shows as a WARN repeat: check by ear.

### Review Page
- **Looks like:** a private local web page: versions list (v1, v2 ...; approved = locked), a frame-accurate scrubber
  (arrow keys = 1 frame, Shift = 1 s, HH:MM:SS:FF + frame number), notes at the current frame with an exact still,
  side-by-side or wipe compare, Export JSON / Markdown.
- **Use:** after delivering a cut you will review closely, and for each new version of it. Notes export straight into
  the next Claude brief.
- **CLI:** `python helpers/review_page.py build out/<name>-shorts_final.mp4 --label "..."` (-> `review-pages/<name>/`),
  `add-version <folder> <new_final.mp4> --label "..."`, `approve <folder> v2`, `open <folder>`, `export <folder>`,
  `zip <folder> --to "<your review folder>"` (+ `HOW TO OPEN - Review Page - <name>.txt`).
  To open it: double-click **`Open Review.cmd`** (Windows) in the folder (or `python review_server.py` inside it).
- **Built by:** `helpers/review_page.py`, `helpers/review_page_template.html`, `helpers/review_server_template.py`
  (copied into each folder as `review_server.py`: stdlib Python only, binds 127.0.0.1 only, HTTP Range for seeking).
- **QC / rules:** never public: no tunnel, no hosting. Versions are COPIES in `versions/` (read-only);
  the finals in `out/` are never touched; nothing is overwritten. Opening `index.html` without the launcher still plays,
  but notes then stay in that browser only (no frame files).

### Style Breakdown
- See `style/style-breakdown.md` (the skill doc Claude follows). `python helpers/style_breakdown.py <reel.mp4>
  [--captions sidecar.captions.json] --out out/style-breakdown/<name>` -> cuts, contact sheet, pacing, caption
  placement, a style guide in our vocabulary and a CONFLICTS list, ending "Waiting for you to pick what to apply."
- Files you supply only (no yt-dlp, no URLs). It never applies anything; new ideas are proposals for this library.

### EDL Remap
- **Looks like:** a new props file + new captions JSON (+ optional re-cut media) and a remap report table:
  item, old time, new time, status (OK / MOVED / RE-ANCHORED occurrence / duration changed / UNMAPPED).
- **Use:** after a pacing change (dead air trimmed, a sentence removed, a new in-point, an inserted hold) when the
  props were already written. Never hand-shift numbers.
- **CLI:** `python helpers/remap_edl.py --props props/<name>.json --edl changes.json --out props/<name>.v2.json
  [--captions-out public/media/<name>.v2.captions.json] [--recut-media public/media/<name>.v2.mp4] [--report ...]`.
  EDL ops in SOURCE seconds (captions clock): `delete {from,to}`, `insert {at,duration,fill: freeze|black}`,
  `trim {start,end}`; or a keep list / `cutlist.py` output. Then `check-highlights.mjs`, Studio, render, finish, QA Gate.
- **Built by:** `helpers/remap_edl.py` (+ `helpers/props_util.py`, a Python port of `src/types.ts` anchor resolution).
- **QC / limits:** refuses to overwrite its input. Exit 3 if a money word or the Hook Caption (first 2 s) is cut.
  It cannot invent a word: an anchor whose word was cut is UNMAPPED for a human. A word partly cut by a splice is
  dropped from captions and flagged. Re-cut media keeps the clean-audio tag (cleanup won't run twice) and puts 4 ms
  fades at every splice. Remotion plays one source + trim, so any non-trim change needs the re-cut media.

### Footage Catalog
- **Looks like:** `catalog/index.json` + `catalog/thumbs/`: per clip duration, resolution, fps, thumbnail, transcript
  text + word times (from existing `*.captions.json`), speakers if known, tags; search hits with times + context.
- **Use:** finding footage by what was said or by topic, before pitching moments or building B-roll.
- **CLI:** `python helpers/footage_catalog.py index [--paths ...] [--no-drive] [--force]`,
  `python helpers/footage_catalog.py search pricing [--md out.md --html out.html --json out.json]`, `... stats`.
  Default roots: `public/media/` + an optional raw-footage inbox folder (set `FOOTAGE_INBOX` or `"footage_inbox"` in
  `editor.config.json`, e.g. a synced Drive/Dropbox folder). Finished renders in "Video Editor Output" / `review/` are not indexed.
- **Built by:** `helpers/footage_catalog.py`.
- **QC / limits:** never moves/renames/writes source media; no batch transcription (clips without a sidecar say "no
  transcript yet"; run `npm run transcribe` on them first). Search = exact words (+ plurals), no fuzzy match for misheard words.

### Crop Previews
- **Looks like:** `strip.jpg`: one row per key moment, LOOSE (wide base 1.00) | TIGHT (largest legal scale, standard
  1.16 first, labelled with the scale and the PunchIn x/y), plus full-res PNGs and `crop_previews.json` with the
  proposed PunchIn props. An illegal tight is never drawn: "TIGHT UNSAFE: not offered" + why.
- **Use:** before a render, when the framing per punch / hook / end is a judgment call. you pick; the pick is
  copied into props by hand.
- **CLI:** `python helpers/crop_previews.py public/media/<src>.mp4 --times 0.5,2.9,9.0,17.6 [--focus 0.52,0.5]
  [--props props/<name>.json] [--panel x,y,w,h] [--scales 1.16,1.12,1.10,1.08] --out out/crop-previews/<name>`.
- **Built by:** `helpers/crop_previews.py` (face_safe.py detector, `CAP_UP` / `CHIN_DOWN` / `SIDE` margins, mapper).
- **QC / limits:** cap + chin must sit inside the visible panel in BOTH crops; already-tight bases (head > 45 % of the
  panel) cap at 1.12 (CLAUDE.md Zoom & punch). face_safe margins are conservative, so it can under-offer a tight crop
  (safe side). No face found = UNSURE, nothing proposed. Ear/headphone margin touching a side edge is a note only.
