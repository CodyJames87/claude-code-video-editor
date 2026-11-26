# Effects Library

**Edit prompts name effects from this library BY NAME. Do not invent a one-off effect.** If an edit seems to need
something that isn't here, propose it first (what it looks like, where, why) and add it here only after the creator
approves it. Names are stable: don't rename them.

Brand rules apply to every effect: colors come from `brand.config.json`. `accent` is the only accent / highlight
(one word or idea); `ink` / `white` / `neutral` for everything else; `support` for small supporting touches only (thin
edge, bullet, quiet label), never a punch word or a second caption highlight. Type: Anton captions, Plus Jakarta Sans
ExtraBold cards, DM Sans body, never italic (all three fonts are bundled, OFL). Text never covers the speaker's face
(mouth, beard, chin), including at every zoom peak. Extras (Zoom To Detail, Spotlight, B-Roll Speed Ramp) = at most ONE
per reel. Full rules: `CLAUDE.md`. Scales are relative to the wide base frame (1.00).

| Group | Effects |
|---|---|
| Camera | Eased Push, Steady Crawl, Instant Punch, Hero Push, Zoom To Detail |
| Text | Lower-Third Captions, Hook Caption, Hook Card, Statement Card, Process Flow, Comparison Card, Full-Screen List, Pill List |
| Look / time | Spotlight, B-Roll Speed Ramp |
| Layout | Speaker-Tracking Cuts (opt-in) |
| Talking-head motion | **Long Slow Push**, **Short Slow Push**, **Quick Punch** (= Instant Punch, talking-head), Karaoke Captions, Progress Bar (off unless asked), Solo Frame, Title Banner, Count-Up Card, Callout Chip (+ **Logo Chip** and **Keyword Chip** variants), Browser-Frame B-Roll, Split Frame, Takeover Frame (+ **Takeover CTA**), Hook Variations |
| Text posts | Text Thread (animated iMessage-style reel, `style/profiles/text-thread.md`) |
| Audio | Audio Cleanup, Whoosh / Pop SFX |

**Editor tools** (QA Gate, Review Page, Style Breakdown, EDL Remap, Footage Catalog, Crop Previews) are NOT effects:
they check, preview and re-time edits. Their catalog lives in `style/tools.md`. The QA Gate is mandatory before every delivery.

---

## Camera

### Eased Push
- **Looks like:** a slow, smooth push in that eases in and out across a whole beat (1.00 -> 1.08).
- **Use:** cinematic, emotional or B-roll moments. **Not** for talking-head / punchy speech (use Steady Crawl).
- **Props:** `PushIn` with `style: "eased"` (also the default when `style` is omitted, so old props behave the same).
  `to` default 1.08 (softer 1.05, harder 1.10); `x`,`y` 0-1 focus (default 0.5, 0.35); `outFrames` snap-out (default 4).
  Optional `holdSec` (default 0): hold the peak after the window, then ease out over `outFrames` (e.g. 30-45 for a slow, no-pop return; e.g. a talking-head reel).
  `{ "type": "PushIn", "at": { "word": "remember" }, "duration": 9.4, "props": { "style": "eased", "to": 1.08, "x": 0.54, "y": 0.3 } }`
- **Built by:** `src/components/Camera.tsx` (`moveScale`, cubic ease-in-out).
- **Talking-head:** a shorter 4-5 s version is **Short Slow Push** under Talking-head motion below. Do not use this long cinematic Eased Push as the default talking-head move.
- **QC:** frame at the push end: cap + chin in frame, no text on the face.

### Steady Crawl
- **Looks like:** a constant, linear creep in (+0.048 scale/s, ≈ ×1.0016 per frame), no easing, over 2–3 s.
- **Use:** talking-head and punchy speech reels, under setup / anecdote / list stretches, usually right before an
  Instant Punch or a cut to B-roll. **Not** for cinematic / B-roll moments (use Eased Push). In only, never out.
- **Props:** `PushIn` with `style: "crawl"`. `to` = 1 + 0.048 × duration (2.5 s -> 1.12, 3.0 s -> 1.144); omit `to` and
  Camera.tsx computes it. End the crawl where the next punch starts. `outFrames` default 4; `1` = 1-frame snap.
  `{ "type": "PushIn", "at": { "word": "two people" }, "duration": 2.5, "props": { "style": "crawl", "to": 1.12, "x": 0.54, "y": 0.3 } }`
- **Built by:** `src/components/Camera.tsx` (`moveScale`, linear when `style === "crawl"`).
- **Talking-head:** a long 15-20 s version is **Long Slow Push** under Talking-head motion below. Do not fire a short 2-3 s crawl on every talking-head beat.
- **QC:** frame at the crawl end: cap + chin in frame, captions on the chest. Camera shows the LARGER of overlapping
  moves, so a punch on top wins; a crawl window must not outlast the punch or the punch-out lands mid-zoom.

### Instant Punch
- **Looks like:** a 1-frame scale jump (no ease) to 1.16, held 1.5–3 s, then a 1-frame snap back to 1.00.
- **Use:** the FIRST word of a new clause: question, new instruction, payoff word, closer. Max ~4 per reel, ≥ 8 s apart
  for whooshes. Palette: small 1.08, **standard 1.16**, stacked 1.22–1.23 (1.08 then 1.23, no punch-out between).
  **Not** past 1.10–1.12 on already-tight crops (webcam panes, speaker-tracking close-ups): loosen the base first.
  Not while a full screen share / slide is on, not across a composite.
- **Props:** `PunchIn`; every NEW punch MUST set `inFrames: 1, outFrames: 1` (Camera.tsx still defaults to 4 for old props).
  `sfx: false` to skip its whoosh.
  `{ "type": "PunchIn", "at": { "word": "how" }, "duration": 2.0, "props": { "to": 1.16, "inFrames": 1, "outFrames": 1, "x": 0.54, "y": 0.3 } }`
- **Built by:** `src/components/Camera.tsx`.
- **Talking-head:** do not use this 1-frame snap-back on `talking-head-motion` reels (it reads as a glitch on a talking head). Use **Quick Punch** under Talking-head motion below: ease out over >= 0.5 s or hold the peak to a cut.
- **QC:** full-res frame at every peak: whole cap (hat tip) and chin in frame, no text on mouth/beard/chin, snaps back to 1.00.

### Hero Push
- **Looks like:** a fast 12-frame (0.4 s) eased push to ~1.30, a ~0.2 s hold in the pause after the line, a 1-frame snap to 1.00.
- **Use:** ONCE per reel max, on the title / payoff line only, from a wide base. Never on a tight crop.
- **Props:** `{ "type": "PunchIn", "at": { "word": "is you" }, "duration": 0.6, "props": { "to": 1.30, "inFrames": 12, "outFrames": 1, "x": 0.54, "y": 0.3 } }`
  (`duration` = 0.4 s push + ~0.2 s hold).
- **Built by:** `src/components/Camera.tsx`. Eases in with cubic ease-out.
- **QC:** frame at the peak: cap + chin in frame, no text on the face (lower/shrink/drop captions for that window if needed).

### Zoom To Detail
- **Looks like:** the frame pushes toward a detail (a product, a part, a screen), holds, eases back out.
- **Use:** only when there is a real detail to show ("zoom in on the screen at 0:41"). Counts as the reel's one extra.
  Not on a face for emphasis (use Instant Punch).
- **Props:** `{ "type": "ZoomToDetail", "at": 41, "duration": 1.6, "props": { "x": 0.62, "y": 0.4, "zoom": 2.2, "ease": 0.3 } }`
  (`x`,`y` 0-1 of the frame, found on a QC frame; `zoom` default 2, use 2–2.5; `ease` s, default 0.3).
- **Built by:** `src/components/ZoomToDetail.tsx` (ffmpeg-only path: `helpers/effects.py` `zoom_filter`).
- **QC:** frame at the hold: the detail is centred and sharp enough to read; nothing important cropped.

---

## Text

### Lower-Third Captions
- **Looks like:** two short Anton uppercase lines (≤ 4 words / 18 chars each), white, ONE accent money word per on-screen block.
- **Use:** every talking reel (default). Montages: sparse, real speech only.
- **Props:** `"captions": { "mode": "lowerThird", "maxWords": 4, "maxLineChars": 18, "moneyWords": [...], "skipWords": ["mm-hmm"] }`.
  Block bottom y 1150 (IG safe zone). Face cams: `bottomRanges: [{ "from", "to", "bottom": ~1630, "byFrame"? }]` (chest);
  tight webcam panes: bottom 1690 (max 1760). `oneLineRanges: [{ "from", "to" }]` when the chin sits too low for two lines.
  Run `node helpers/check-highlights.mjs props/<name>.json` (must print `HIGHLIGHTS: PASS`).
- **Built by:** `src/components/Captions.tsx` + `src/captionLayout.js` (renderer throws on 2+ accent words per block).
- **QC:** two lines, ≤ 1 accent word per block, inside the safe zone, ≥ 60 px gap above the beard on tight webcam frames,
  no text on the face at any push/punch peak or layout cut (check frames n-1 / n at hard layout cuts).

### Hook Caption
- **Looks like:** the hook line as the FIRST normal lower-third caption block, 0–2.0 s, readable on frame 0.
- **Use:** the DEFAULT hook on every reel. The hook is a normal caption, NOT the white card.
- **Props:** `"hook": null`; add the hook words (verbatim, ≤ 7 words, ending with a period, one accent money word) to the
  captions JSON at 0–1950 ms and move the first spoken words to start at 2.0 s.
- **Built by:** `src/components/Captions.tsx` (same as Lower-Third Captions).
- **QC:** frame 0.03 s: hook readable, off the face, one accent word.

### Hook Card
- **Looks like:** the white Clean Line hook card (Plus Jakarta Sans ExtraBold, one accent word) from frame 0, captions hidden under it.
- **Use:** ONLY if you ask for the card. Otherwise use Hook Caption.
- **Props:** `"hook": { "text": "...", "highlight": "...", "duration": 2.0, "position": "top" | "lower", "bottom": 1150, "sfx": true }`
  (`lower` when the face sits high; face cams: `bottom` ~1700, tight webcam 1780, max 1840).
- **Built by:** `src/components/HookText.tsx`.
- **QC:** frame 0.03 s: readable, never covers the face.

### Statement Card
- **Looks like:** one bold statement on a Clean Line card, kicker "The truth", one accent word.
- **Use:** the subtle-truth moment, 1–2 cards per reel max. Not in montages unless a real spoken line earns it.
- **Props:** `{ "type": "StatementCard", "at": { "word": "..." }, "duration": 2.2, "hideCaptions": true, "props": { "text": "...", "highlight": "never", "kicker": "The truth", "position": "center" } }`
  (`position` `top` if the face sits low, `center` + `hideCaptions` if high; also `lower`, `full`; `theme` light/dark).
- **Built by:** `src/components/StatementCard.tsx`. Gets a pop (Whoosh / Pop SFX).
- **QC:** frame at the card mid: clear of the face, one accent word, text matches what's said or the truth.

### Process Flow
- **Looks like:** steps reveal one after another; the newest step gets the accent edge.
- **Use:** a spoken sequence of steps (counts toward the 1–2 card max). `hideCaptions` defaults true.
- **Props:** `{ "type": "ProcessFlow", "at": 30, "duration": 3, "props": { "title": "First hire", "steps": ["Scared", "Hire", "Train"] } }`
- **Built by:** `src/components/ProcessFlow.tsx`. **QC:** steps match the audio, clear of the face.

### Comparison Card
- **Looks like:** side-by-side (stacked on vertical) comparison; only the winner gets the accent.
- **Use:** a spoken this-vs-that (counts toward the card max). `hideCaptions` defaults true.
- **Props:** `{ "type": "ComparisonCard", "at": { "word": "competing" }, "duration": 3, "props": { "left": { "label": "Them", "points": ["Fantasy"] }, "right": { "label": "Last year's you", "points": ["Real"] }, "winner": "right" } }`
- **Built by:** `src/components/ComparisonCard.tsx`. **QC:** one accent side, readable, clear of the face.

### Full-Screen List
- **Looks like:** full-screen takeover: title, then numbered items stagger in.
- **Use:** a spoken list worth reading (counts toward the card max). `hideCaptions` defaults true.
- **Props:** `{ "type": "FullScreenList", "at": 40, "duration": 3, "props": { "title": "What I really do", "items": ["Film", "Review", "Post"], "highlight": "really" } }`
- **Built by:** `src/components/FullScreenList.tsx`. **QC:** one accent word, items match the audio.

### Pill List
- **Looks like:** short tags pop in one by one; the newest pill is filled with the accent color.
- **Use:** 2–4 short spoken words/phrases (counts toward the card max).
- **Props:** `{ "type": "PillList", "at": 12.0, "duration": 2.5, "props": { "items": ["Scared", "Hired anyway", "Grew"], "position": "top" } }` (`top`/`center`/`bottom`).
- **Built by:** `src/components/PillList.tsx`. **QC:** pills clear of the face, words match the audio.

---

## Look / time

### Spotlight
- **Looks like:** everything outside a soft ellipse is dimmed 30–40% (never black, never tinted).
- **Use:** point at one real thing in frame. Counts as the reel's one extra.
- **Props:** `{ "type": "Spotlight", "at": 50, "duration": 2, "props": { "x": 0.5, "y": 0.55, "w": 0.3, "h": 0.2, "dim": 0.38 } }` (0-1 of the frame; `feather` optional).
- **Built by:** `src/components/Spotlight.tsx` (ffmpeg-only: `helpers/effects.py` `spotlight_chain`).
- **QC:** the lit area is on the thing being talked about; dim reads as subtle.

### B-Roll Speed Ramp
- **Looks like:** stop-and-go B-roll: 1× -> fast -> 1× in steps, inside the overlay window; muted, the voice keeps playing.
- **Use:** "speed up the walk" style B-roll. Never ramp the talking track. Counts as the reel's one extra.
- **Props:** `{ "type": "SpeedRamp", "at": 55, "duration": 2, "props": { "sourceStart": 55, "sourceEnd": 63, "steps": 9 } }` (`src` optional B-roll file).
- **Built by:** `src/components/SpeedRamp.tsx` (ffmpeg-only: `helpers/effects.py` `speed_pieces`).
- **QC:** voice in sync after the window; no frozen or skipped frames.

### Speaker-Tracking Cuts (opt-in)
- **Looks like:** the 9:16 frame follows whoever is talking (hard cut on a sustained speaker change), with stacked 2-up /
  3-up composites during rapid back-and-forth or reactions.
- **Use:** multi-person podcasts/studio shots, opt-in per video. Follow whoever is speaking (no bias to one person). Not for single
  speaker, webcam or screen-share reels.
- **Settings:** `python helpers/speaker_reel.py faces|activity|plan|render ...` (faces -> speakers -> shots JSON -> 1080x1920
  reframe; you can edit the shots JSON), then Remotion on top. Alternate path: `python helpers/render.py ... --speaker-track`
  (uses `helpers/speaker_track.py`). Hold 1.5–2 s before switching, ignore interjections < 0.8 s, chin-safe anchor
  y ~ 0.85 of the face box, composite bg `#111418` (functional layout canvas). These crops are tight: punches stay 1.10–1.12 until the base is
  loosened; no PushIn/PunchIn over a composite.
- **Built by:** `helpers/speaker_reel.py`, `helpers/speaker_track.py`, `helpers/render.py --speaker-track`.
- **QC:** frames at every switch, hold boundary, punch peak and composite in/out (n-1 / n at cuts): face matches voice,
  no sub-0.8 s flicker, full faces in every panel, no text on any face. Report the speaker map + low-confidence matches.

---

## Talking-head motion

Built for the `talking-head-motion` profile (try it with `examples/sample.props.json`). All original Remotion / Python / ffmpeg code.
NOT part of the podcast profile unless a prompt opts in.
Geometry is px on the 1080x1920 design frame (scaled on 4:5 / 16:9). Persistent chrome (Karaoke Captions, + the Progress Bar only when you ask for it)
may run under everything; otherwise ONE big effect per moment (never a Count-Up, Callout, Split, Takeover and a punch on
the same beat). Place every graphic with `helpers/face_safe.py` FIRST, then still LOOK at the QC frames.
**Mix the three zoom tools per moment; never use the same one on every beat.** Recheck chips, count-up, and captions stay off the face at the peak and through any hold. Cap + chin in frame on every move. Never a 1-frame snap-back.

### Long Slow Push
- **Looks like:** one continuous, very slow linear crawl over 15-20 s, 1.00 -> about 1.12, then a hold at the peak until a hard cut or Takeover. No mid-reel ease-out or snap-back.
- **Use:** a longer setup / story stretch when one slow approach should carry that stretch. Mix with Short Slow Push and Quick Punch elsewhere in the reel; do not stack several of these, and do not use this as the only zoom on every talking-head job. Never on a Split or a Takeover.
- **Props:** `PushIn` with `style: "crawl"`, `duration` 15-20, `to` about 1.12, chin-safe origin on webcam sources (`x` 0.5, `y` 0.80). `holdSec` long enough to reach the next cut / Takeover; `outFrames` 8+ (the Takeover or cut should already cover the out). Do not use `outFrames: 1`.
  `{ "type": "PushIn", "at": 11.94, "duration": 20.0, "props": { "style": "crawl", "to": 1.12, "holdSec": 13.67, "outFrames": 8, "x": 0.5, "y": 0.8 } }`
- **Built by:** `src/components/Camera.tsx` (`moveScale`, linear when `style === "crawl"`, plus `holdSec`).
- **Tuned on:** a ~50 s talking-head reel: 11.9-31.9 s crawl to 1.12, held through the end takeover at 45.6 s.
- **QC:** frames at start, mid, peak, and late hold: cap + chin in, captions / logo chips / count-up still off the face at 1.12.

### Short Slow Push
- **Looks like:** a slow ~4-5 s eased push-in (1.00 -> about 1.08-1.10) on a short emphasis beat. No glitchy pop-back.
- **Use:** mid-length talking-head beats where a long 15-20 s crawl would overstay, but an Instant Punch would feel jumpy. Mix with the other two zooms; do not treat this as the only move in a long reel, and do not fire several back-to-back with mid-reel snap-backs. Never on a Split or a Takeover.
- **Props:** `PushIn` with `style: "eased"`, `duration` about 4-5 (up to ~6), `to` 1.08-1.10, chin-safe origin on webcam sources. After the window: `holdSec` through the next beat, and/or ease out over 30-45 frames (~1-1.5 s). Do not use `outFrames: 1`.
  `{ "type": "PushIn", "at": 11.94, "duration": 5.5, "props": { "style": "eased", "to": 1.08, "x": 0.5, "y": 0.8, "outFrames": 36 } }`
- **Built by:** `src/components/Camera.tsx` (`moveScale`, cubic ease-in-out, plus `holdSec`).
- **QC:** frames at start, peak, and out/hold: cap + chin in, no text on the face, no pop-back mid-sentence.

### Quick Punch (Instant Punch, talking-head)
- **Looks like:** a fast punch-in on a punchline, held, then a smooth return — or it holds until a hard cut / Takeover. Not a 1-frame jump out.
- **Use:** a real punchline only (question, payoff, closer). Mix with Long Slow Push and Short Slow Push; do not punch every clause. Tight-crop cap 1.10-1.12 on webcam sources (loosen the base before going to 1.16). Never on a Split or a Takeover. Whoosh only on a real punch (existing SFX caps).
- **Props:** `PunchIn`. Fast in (`inFrames` 1-4). `to` 1.10-1.12 on already-tight webcam crops. **Never `outFrames: 1`.** Ease out over >= 0.5 s (`outFrames` >= 15 at 30 fps), or set `duration` so the peak holds until a hard cut / Takeover (the out is covered or never plays).
  `{ "type": "PunchIn", "at": { "word": "how" }, "duration": 2.0, "props": { "to": 1.12, "inFrames": 1, "outFrames": 15, "x": 0.5, "y": 0.8 } }`
- **Built by:** `src/components/Camera.tsx`. This is a talking-head rule for the same `PunchIn` component; the Camera-section Instant Punch (1-frame in and out) is not the talking-head default.
- **Why:** a 1-frame snap-back mid-sentence reads as a glitch. Ease out over >= 0.5 s or hold to a cut.
- **QC:** full-res frame at the peak and during the out: whole cap and chin in, no text on mouth/beard/chin, no 1-frame snap-back.

### Karaoke Captions
- **Looks like:** Lower-Third Captions (same two Anton lines, same pages, same `bottomRanges` / `oneLineRanges`), but the
  word being spoken is "lit": pure white with a short scale pop (1.08, settling at 1.05); the other words sit at hairline
  white with the ink outline (readable, never gray-on-gray).
- **Use:** talking-head-motion reels. Not the podcast default (podcast keeps Lower-Third Captions unless a prompt opts in).
- **Money word rule (fixed choice):** the ONE accent money word per block is picked exactly like Lower-Third
  Captions and stays **accent at rest for the whole block**; when it is the active word it stays accent and also pops.
  The lit active word is white, never an accent, so `check-highlights.mjs` still guarantees max one accent word per block.
  No sentiment colors, no karaoke bar.
- **Props:** `"captions": { "mode": "karaoke", "maxWords": 4, "maxLineChars": 18, "moneyWords": [...], "bottomRanges": [...] }`
  (or `"mode": "lowerThird", "karaoke": true`). Run `node helpers/check-highlights.mjs props/<name>.json` (HIGHLIGHTS: PASS).
- **Built by:** `src/components/Captions.tsx` (karaoke branch of `LowerThirdCaptions`) + `src/captionLayout.js` (unchanged).
- **QC:** one accent word per block, the lit word follows the audio, captions ≥ 60 px under the beard at every peak.

### Progress Bar
- **Looks like:** a 7 px rounded bar: the accent color fill growing left to right over the whole reel (tail hold included)
  on a subtle `hairline` track at 32 % (or `paleFill`), 60 px side insets.
- **Use:** OFF by default: only when you ask for it on a talking-head-motion reel; then persistent. Sits in the Solo Frame ink headroom band (y 226): below the Reels top UI,
  above the cap, never on the face or the caption block.
- **Props:** `"progressBar": { "enabled": true, "position": "topSafe", "height": 7, "inset": 60, "track": "hairline" }`
  (`y` override; `position: "bottom"` exists but lands in the IG bottom UI, avoid it on Reels).
- **Built by:** `src/components/motion/ProgressBar.tsx` (drawn above the captions in `EditedVideo.tsx`).
- **QC:** every punch peak: bar not on the cap (the band is outside the camera panel, so punches never move under it).

### Solo Frame
- **Looks like:** the default talking-head shot WITH HEADROOM: an `ink` band on top (`topBand`, 420 on the demo)
  and the video in a panel under it (cover fit, wider than a tight face crop). Crawls / punches happen INSIDE the panel,
  so the band, the bar, the banner and the chips never move.
- **Use:** base layout of every talking-head-motion reel. `cropTop` hides a dirty/white top edge some webcams bake in.
- **Props:** `"layout": { "topBand": 420, "cropTop": 12 }` + `"focus": { "x": 0.517, "y": 0.5 }`.
  No `layout` = the old full-bleed look (every older props file renders exactly as before).
- **Built by:** `src/compositions/EditedVideo.tsx` (band + clipped panel); `src/components/Camera.tsx` unchanged.
- **QC:** cap tip and chin inside the panel at every punch peak (tight-crop cap 1.10–1.12 unless the base is loosened).

### Title Banner
- **Looks like:** one short line in the ink headroom band, Plus Jakarta Sans ExtraBold 60 px white, ONE accent word.
- **Use:** the opening ~2 s (or a chapter title): words the speaker actually says (a tight verbatim phrase, never a paraphrase).
  Leaves before the next band graphic (Count-Up / Chip) so they never stack. Not a second caption block.
- **Props:** `{ "type": "TitleBanner", "at": 0, "duration": 1.76, "props": { "text": "What I needed to grow", "highlight": "grow", "y": 316, "instantIn": true } }`
  (`instantIn` = fully on at frame 0 for the hook frame; `theme: "card"` = ink text on a white card).
- **Built by:** `src/components/motion/TitleBanner.tsx`.
- **QC:** frame 0.03 s readable; `face_safe.py check` SAFE; one accent word.

### Count-Up Card
- **Looks like:** a white card in the band: DM Sans kicker (neutral) + a Plus Jakarta ExtraBold accent number counting up
  (ease-out) + an ink unit; the number LANDS as the speaker says it, with a short pop (one pop SFX on the landing).
- **Use:** a number the speaker actually says; kicker/unit are the speaker's words. Hide captions while it shows if they'd double it.
- **Props:** `{ "type": "CountUpCard", "at": { "word": "13", "offset": -0.30 }, "duration": 1.72, "hideCaptions": true, "props": { "to": 13, "from": 0, "landSec": 0.30, "numberSize": 80, "kicker": "In business for", "unit": "years", "y": 314 } }`
  (`landSec` = number's word start − overlay start; `prefix` / `suffix` for `$` / `%`).
- **Built by:** `src/components/motion/CountUpCard.tsx`; landing pop planned in `src/components/Sfx.tsx`.
- **QC:** a frame after the landing shows the spoken number; `face_safe.py` SAFE.

### Callout Chip
- **Looks like:** a small white chip, Plus Jakarta ExtraBold uppercase ink, a thin `support`-color left edge
  (supporting use), ONE accent word max, soft shadow; pops in, fades out.
- **Use:** a short verbatim phrase (2–4 words) worth calling out. ONLY where `helpers/face_safe.py check` says SAFE for
  the WHOLE window (pad 40). If the detector is UNSURE or every open spot is UNSAFE, do not place it.
- **Props:** `{ "type": "CalloutChip", "at": { "word": "miserable", "offset": -0.04 }, "duration": 1.8, "props": { "text": "Miserable failure.", "highlight": "failure", "box": [60, 256, 760, 100], "align": "left" } }`
  Optional logo: `"logoSrc": "logos/<your-file>.png"` (a file in `public/logos/` that you are allowed to use) (+ `logoOnly` default true, `logoScale` = logo height as a fraction of the chip height, default 0.46). Intrinsic aspect ratio, never recolored, same white chip + support edge; widen `box` for wide wordmarks and re-run `face_safe.py`. Without `logoSrc` the chip is text-only as before.
- **Built by:** `src/components/motion/CalloutChip.tsx` + `helpers/face_safe.py`.
- **QC:** chip mid frame: off the face and cap, words match the audio, spaces intact.

### Logo Chip (Callout Chip variant)
- **Looks like:** the Callout Chip with a logo instead of words, popping in the moment the speaker names a tool or brand.
- **Use:** every time a named tool / product is said (e.g. "Claude Code", your own brand). **You supply the logo file**
  (PNG/SVG with transparency) in `public/logos/`, and only logos you are allowed to use; follow each company's brand
  guidelines (links in `public/logos/README.md`). No logo file = use the text chip.
- **Props:** `{ "type": "CalloutChip", "at": { "word": "Claude Code", "offset": -0.04 }, "duration": 1.7, "props": { "text": "Claude Code", "box": [60, 280, 620, 140], "align": "left", "logoSrc": "logos/claude-code.png", "logoOnly": true, "logoScale": 0.48 } }`
- **QC:** same as Callout Chip; the logo is not stretched or recolored.

### Keyword Chip (Callout Chip variant)
- **Looks like:** a short "TYPE <KEYWORD>" chip with the keyword in the accent color, right when the speaker says the
  comment keyword ("comment EDIT and I'll send you the guide").
- **Use:** comment-keyword CTAs (lead magnets, DM automations). Pair with a Takeover CTA at the end. Keyword verbatim.
- **Props:** `{ "type": "CalloutChip", "at": { "word": "EDIT", "occurrence": 2, "offset": -0.05 }, "duration": 1.3, "props": { "text": "Type EDIT", "highlight": "EDIT", "box": [60, 280, 540, 140], "align": "left" } }`
  (set `occurrence` when the keyword is also an ordinary word earlier in the clip).
- **QC:** chip lands on the spoken keyword, off the face.

### Browser-Frame B-Roll
- **Looks like:** a real public web page scrolling slowly inside OUR browser chrome: neutral window dots, a DM Sans address
  pill, a hairline, a rounded white frame with a soft shadow. No OS trademark, no company logo.
- **Use:** inside a Split Frame (graphic band) or a full-frame Takeover Frame; never as a sticker over the speaker's face. Only
  logo-safe public pages (e.g. Wikipedia); no company sites, no customer/supplier names.
- **Capture:** `node helpers/capture_browser_broll.mjs <url> -o public/media/broll/<name>.mp4 --width 1080 --height 640 --seconds 5.5 --scroll 600 --start 62 [--hide "<css>,..."]`
  (LOCAL Chrome via puppeteer-core, frame-by-frame screenshots, cookie / donation / chat overlays hidden, cached so a
  render never hits the network; a `.json` sidecar keeps the url and capture time).
- **Props:** graphic `{ "type": "browser", "src": "media/broll/<name>.mp4", "url": "en.wikipedia.org/wiki/Small_business", "startFrom": 0 }`.
- **Built by:** `helpers/capture_browser_broll.mjs`, `src/components/motion/BrowserFrame.tsx`.
- **QC:** no popups / widgets in the clip, text legible, frame clear of the face.

### Split Frame
- **Looks like:** a hard layout cut to an ink canvas: graphic band on top (y 258–858: browser B-roll or a short text card),
  a caption gap (block bottom 1068), the speaker in a full-width 16:9 band below (y 1150–1758, same source in sync, muted, whole
  head). Hard cut back to Solo at the end.
- **Use:** a 4–6 s stretch where a visual helps. NO PushIn/PunchIn while split (`check-highlights.mjs` fails on overlap).
  `videoZoom` is a STATIC band crop (e.g. 1.12 to keep a stray brand logo at the frame edge out of the band), not a move.
- **Props:** `{ "type": "SplitFrame", "at": { "word": "We stayed" }, "duration": 4.92, "props": { "videoBand": "bottom", "captionBottom": 1068, "videoZoom": 1.12, "videoFocus": { "x": 0.47, "y": 0.35 }, "graphic": { "type": "browser", ... } } }`
  (captions move to `captionBottom` exactly at the cuts automatically; `graphic: { "type": "text", "text", "highlight", "kicker" }` also works).
- **Built by:** `src/components/motion/SplitFrame.tsx` + `EditedVideo.tsx` (automatic byFrame bottomRange).
- **QC:** frames n-1 / n at the cut in and out + split mid: full head and chin in the band, captions in the gap, `face_safe.py` SAFE.

### Takeover Frame
- **Looks like:** full-screen white (or ink) card, video hidden: short accent rule, DM Sans kicker (neutral), a big Plus
  Jakarta ExtraBold headline with ONE accent word; `reveal: "spoken"` shows each word as the speaker says it. Pop on entry.
- **Use:** ONE per reel (`check-highlights.mjs` fails on a second), best as the end beat. Verbatim text only. Captions
  hidden by default. Top-level `tailHoldSec` holds it after the source ends so it can be read.
- **Props:** `{ "type": "TakeoverFrame", "at": { "word": "we've" }, "duration": 3.12, "props": { "kicker": "In the last three or four years,", "text": "We've really grown exponentially.", "highlight": "exponentially", "reveal": "spoken" } }` + `"tailHoldSec": 0.8`
  (`graphic: { "type": "browser", ... }` = full-frame browser B-roll instead of text).
- **Built by:** `src/components/motion/TakeoverFrame.tsx`, `EditedVideo.tsx` (word times), `src/compositions/presets.tsx` (tail hold).
- **QC:** takeover mid + last frame: verbatim, one accent word, no captions doubling it, the voice isn't cut.

### Takeover CTA (Takeover Frame variant)
- **Looks like:** the end card: full-screen light Takeover with the spoken CTA ("Comment EDIT and I'll send you the free
  guide."), keyword in the accent color, held ~0.8 s past the last word.
- **Use:** the last beat of a lead-magnet reel. Cut any dead stare before it so it lands right after the spoken line.
  Run it to the very end of the clip (+ `tailHoldSec`) so the last frames are never black.
- **Props:** `{ "type": "TakeoverFrame", "at": { "word": "comment edit", "offset": -0.01 }, "duration": 5.8, "hideCaptions": true, "props": { "text": "Comment EDIT and I'll send it to you.", "highlight": "EDIT", "theme": "light", "reveal": "spoken" } }` + `"tailHoldSec": 1.0`
- **QC:** first frame shows no leftover caption on top (nudge `offset` by -0.01 s if it does); last frame is not black.

### Hook Variations
- **What it does:** from ONE picture-locked body and 2+ REAL spoken hook ranges, builds standalone variants (hook + body,
  frame-exact ffmpeg cut) plus shifted captions and, with `--props`, a props copy per variant (numeric `at` shifted, word
  anchors left to re-resolve; warns when a hook repeats an anchor phrase).
- **Use:** A/B openings. Never invent a hook the speaker didn't say. Each variant is rendered, QC'd and delivered on its own, only if you ask.
- **Settings:** `python helpers/hook_variants.py --src public/media/<name>.mp4 --captions public/media/<name>.captions.json --body <s> --hook natural=0:3.4 --hook alt=<a>:<b> [--props props/<name>.json] [--out-dir public/media/hookvars] [--dry-run]`
- **Built by:** `helpers/hook_variants.py`.
- **QC:** each variant: hook words match the audio, body in sync, anchors land (`check-highlights.mjs` on each props file).

### Face-safe gate (helper behind the effects above)
`python helpers/face_safe.py check <src> --t0 <s> --t1 <s> --panel x,y,w,h --focus fx,fy [--cam-scale 1.12 --cam-origin ox,oy] --box name=x,y,w,h [--pad 40]`
-> SAFE / UNSAFE / UNSURE per box (exit 0 / 1 / 2). OpenCV Haar frontal + profile, outliers rejected, extended to cap and
chin; `scan` prints the head envelope. Conservative by design: a gate, not a substitute for looking at the frames.

---

## Audio

### Audio Cleanup
- **What it does:** highpass 80 Hz -> gentle denoise (`afftdn`, or `arnndn` if a model exists) -> 2:1 compression ->
  limiter -> two-pass linear loudnorm -14 LUFS / -1.5 dBTP. Subtle, no pumping.
- **Use:** ALWAYS, first, on every clip, never skipped. If it makes the voice worse: `--loudnorm-only` fallback on
  `public/media/orig/<name>.mp4`, and flag it in the report.
- **Settings:** `node helpers/clean-audio.mjs public/media/<name>.mp4` (exit 3 = off target). After render:
  `node helpers/finish.mjs out/<name>-shorts.mp4` (gate: -14 ±1 LUFS, TP ≤ -1 dBTP, exit 3 = QC FAIL; iPhone-safe encode).
- **Built by:** `helpers/clean-audio.mjs`, `helpers/finish.mjs`. 
- **QC:** report before/after LUFS + TP; `LOUDNESS: PASS` from finish.mjs; listen for watery/robotic voice.

### Whoosh / Pop SFX
- **What it does:** a subtle whoosh just before each PunchIn (peaks on the punch); a pop on the Hook Card and on each card.
- **Use:** light. A 60 s reel usually wants 2–3 whooshes, 1–2 pops. Whoosh only the strongest punches (`"sfx": false` on
  the rest). Never over a laugh or a word. Note: Hook Caption has no pop (only the `hook` card triggers one).
- **Props:** `"sfx": { "whooshDb": -24, "popDb": -26, "maxWhooshes": 4, "maxPops": 3, "minGapSec": 8 }`; "less SFX" =
  whooshDb -28 or `maxWhooshes: 0`; `"sfx": null` = none; manual `events: [{ "at": ..., "kind": "pop" }]` (still capped).
- **Built by:** `src/components/Sfx.tsx` (`planSfx`, files `public/sfx/whoosh.wav`, `pop.wav`).
- **QC:** listen: no SFX louder than a word.
