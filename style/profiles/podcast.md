# Profile: podcast

Clips cut from talking-head and multi-person podcast / studio / interview footage.
Base: `CLAUDE.md` + `style/effects-library.md`. Settings for every effect below live in the library; this file only says
which ones and when.

## Effects (library names)
| Effect | When |
|---|---|
| **Audio Cleanup** | Always, first, on the source (step 2b). Report before/after LUFS + TP. |
| **Speaker-Tracking Cuts (opt-in)** | Multi-person podcast / studio shots, opt-in per video. Follow whoever is speaking. NOT for single-speaker, webcam or screen-share reels. |
| **Lower-Third Captions** | Every reel. |
| **Hook Caption** | The default hook (`"hook": null`, hook line as the first caption block 0-2.0 s). **Hook Card** only if you ask for it. |
| **Steady Crawl** | Under long talking stretches (setup, anecdote, list), ending where the next punch starts. |
| **Instant Punch** | On the FIRST word of a new phrase: question, new instruction, payoff word, closer. |
| **Hero Push** | Once per reel max, on the title / payoff line only, from a wide base. Never on a tight crop. |
| **Whoosh / Pop SFX** | Light: whoosh only on the strongest punches, pop on cards / Hook Card. |
| Statement Card (optional) | The subtle-truth moment; 1-2 cards per reel max (all card types count). |
| Eased Push (optional) | Only for a cinematic / emotional / B-roll beat inside the reel, not talking-head speech. |

Extras (Zoom To Detail, Spotlight, B-Roll Speed Ramp): at most one per reel, only for a real detail.

## Pacing
- Rough cut first (CLAUDE.md step 2; Descript or by hand) unless the clip is already cut: filler and false starts out, gaps > 0.35 s
  -> 0.25 s, **keep the 0.4-0.6 s pause** before/after the punchline.
- Long podcasts: pitch moments and WAIT for your pick before rendering.
- Speaker-Tracking Cuts: hold 1.5-2 s before switching, ignore interjections < 0.8 s, hard cut on a sustained speaker
  change, composites for rapid back-and-forth / reactions (CLAUDE.md "Speaker tracking + multi-person composite").

## Captions
- Two short Anton lines (<= 4 words / 18 chars each), ONE accent money word per on-screen block, rest white.
  `check-highlights.mjs` must print `HIGHLIGHTS: PASS`.
- Placement: block bottom y 1150 (Reels / Shorts safe zone). Full-frame face cams: `bottomRanges` to the chest (~1630). Tight webcam
  panes: bottom 1690 (max 1760), >= 60 px gap above the beard. `oneLineRanges` when the chin sits too low for two lines.
- Screen-share stack: caption block bottom 995 in the caption band; slide never cropped, no camera moves while it's on.
- Composites: captions in the dark gap / bottom safe zone, on no face in any panel.
- `skipWords` for other speakers' "mm-hmm". Words match the audio; never invent quotes.

## Camera (by reference only)
Settings: the Camera entries in `style/effects-library.md`. In short: wider base
frame first; Instant Punch at the standard scale with `inFrames: 1, outFrames: 1`; crawl at the library rate; already-tight
crops (webcam panes, speaker-tracking close-ups) stay at the tight-crop cap until the base is loosened; cap + chin safe
and no text on the face at every peak. No PushIn/PunchIn over a composite or a full screen share.

## Music + SFX
- Music: `null` by default (most creators add a trending sound in the app). A bed only if asked (royalty-free or generated, ducked under the voice).
- SFX: the default `sfx` block from CLAUDE.md "Style defaults". Do not overdo it.

## Template fills (drop-in values for `style/claude-edit-prompt-template.md`)
Short form of the sections above; if they ever differ, the sections above win.
- **Music / audio:** `"music": null` (you add a trending sound in the app); a ducked royalty-free bed only if asked. Audio Cleanup first.
- **Hook:** Hook Caption (`"hook": null`, hook line verbatim <= 7 words as the first caption block 0-2.0 s, one accent
  word). Hook Card only if asked.
- **Pacing / cuts:** Rough cut (CLAUDE.md step 2) unless "already cut"; keep the 0.4-0.6 s pause around the
  punchline. Long podcasts: pitch moments, wait for your pick. Speaker-Tracking Cuts only if opted in (see Pacing).
- **Captions / text:** Lower-Third Captions (`captions.mode "lowerThird"`), money words + `skipWords`, placement per
  Captions above. Statement Card optional, 1-2 cards max.
- **Camera:** Steady Crawl on talking stretches (ending where the next punch starts); Instant Punch on the first word of
  a new phrase (`inFrames: 1, outFrames: 1`); one Hero Push max on the payoff line; Eased Push only for a cinematic /
  B-roll beat. Settings + tight-crop cap: see Camera above.
- **SFX:** the default `sfx` block from CLAUDE.md: whoosh on the strongest punches only, pop on cards / Hook Card. Light.
- **QC extras:** frame at every crawl end, punch peak and Hero Push peak; card mid; speaker switches / composites if tracked.

## Not the podcast look (don't default to these)
- Slow-Mo Hit Ramp (never on talking faces; never slow speech).
- Music as the driver / wall-to-wall music bed.
- Action-montage pacing (hard cuts on the beat, cut-per-second rhythm).
- Hook Card by default; 

> QA Gate: `helpers/qa_gate.py` on the finished MP4 is now mandatory before `deliver.py`, for every profile (see `style/tools.md`).
