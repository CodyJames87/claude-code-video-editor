# Profile: talking-head-motion

Single-person talking-head reels (phone or webcam, one speaker to camera) with motion graphics on top: karaoke
captions, a mix of three zooms, and at most one bigger graphic at a time. This is NOT the podcast profile.
Base: `CLAUDE.md` + `style/effects-library.md` ("## Talking-head motion" has every setting). This file only says which
effects and when. Try it first on the sample: `examples/sample.props.json`.

## Effects (library names)
| Effect | When |
|---|---|
| **Audio Cleanup** | Always, first, on the source. Report before/after LUFS + TP. |
| **Solo Frame** | Base layout: ink headroom band on top, video panel below, wider than a tight face crop. |
| **Karaoke Captions** | Every reel (lower-third layout, one accent money word per block, lit active word). |
| Progress Bar (optional, OFF by default) | Only when asked for. Then in the headroom band (topSafe). Otherwise omit `progressBar` or set `"enabled": false`. |
| **Hook Caption** or **Title Banner** | The hook: verbatim, one accent word, off the face. Banner in the band for ~2 s, gone before the next band graphic. |
| **Long Slow Push** | One continuous 15–20 s linear crawl (`PushIn` `style: "crawl"`) to about 1.12, then hold until a cut or Takeover. Slow the whole way: no mid-reel ease-out or snap-back. Cap + chin in frame. Webcam origin often chin `y` 0.80. Use on a longer setup / story stretch when one slow approach should carry that stretch. |
| **Short Slow Push** | A ~4–5 s eased push-in (`PushIn` `style: "eased"`, to about 1.08–1.10). No 1-frame snap-back: `holdSec` through the next beat, or ease out over 30–45 frames (~1–1.5 s). Cap + chin in. Use on a short emphasis beat, not as a stand-in for a 15–20 s crawl. |
| **Quick Punch** | Fast punch-in on a real punchline (`PunchIn`). Never `outFrames: 1` (a 1-frame snap-back reads as a glitch). Ease out over ≥ 0.5 s (`outFrames` ≥ 15 at 30 fps) or hold the peak until a hard cut / Takeover. Tight-crop cap 1.10–1.12 on webcam sources. Never on a Split or a Takeover. |
| Count-Up Card (optional) | A number the speaker says; lands on the spoken word. |
| Callout Chip (optional) | A short verbatim phrase, only where `face_safe.py` says SAFE for the whole window (and stays safe at the current zoom scale). **Logo Chip** when a tool / brand is named (your own logo files in `public/logos/`). **Keyword Chip** ("TYPE EDIT") on a comment-keyword CTA. |
| Browser-Frame B-Roll (optional) | Inside a Split Frame (or a full-frame Takeover); logo-safe public pages only. |
| Split Frame (optional) | One 4–6 s stretch where a visual helps; no camera moves while it's on. |
| Takeover Frame / **Takeover CTA** (optional) | ONE per reel, best as the end beat (the CTA card); verbatim; `tailHoldSec` ~0.8 s so it reads. Cut any dead stare before it so the takeover lands right after the spoken line. |
| **Whoosh / Pop SFX** | Light: whoosh only on a real punch, pops on the count-up landing / takeover (1–2 max). |
| Hook Variations (tool) | Only when you ask for A/B openings; real spoken hooks only. |

**Mix the three zooms per moment. Never use the same one on every beat.** Pick the tool that fits the stretch: one Long Slow Push can carry a setup; sprinkle Short Slow Pushes on mid-length beats; save Quick Punch for a real punchline. Do not stack several Long Slow Pushes, do not punch every clause, and do not treat Short Slow Push as the only move in a long talking-head reel.

At most ONE big extra per moment (Count-Up, Chip, Split, Takeover, punch never on the same beat). Karaoke (and the Progress Bar, when asked for) may run under everything. Recheck chips / count-up / captions stay off the face at the zoom peak and through any hold.

## Template fills (drop-in values for `style/claude-edit-prompt-template.md`)
- **Music / audio:** `"music": null`, no bed. Audio Cleanup first; finish.mjs loudness gate.
- **Hook:** Hook Caption or Title Banner, verbatim, one accent word, off the face (readable on frame 0).
- **Captions:** Karaoke Captions (lower-third layout, `bottomRanges` on the chest, ≥ 60 px under the beard). No Progress Bar
  unless you ask for one (`"progressBar": { "enabled": false }` or omit it).
- **Optional extras, at most one big one at a time:** Count-Up Card, Callout / Logo / Keyword Chip, Browser-Frame B-Roll, Split Frame, Takeover Frame.
- **Camera:** mix **Long Slow Push**, **Short Slow Push**, and **Quick Punch** per moment (never the same zoom every time). Tight-crop cap 1.10–1.12. No punch on a Split or a Takeover. Never a 1-frame snap-back (`outFrames: 1`).
- **SFX:** light, existing whoosh / pop only (default sfx caps).
- **QC:** library QC for every effect used, `face_safe.py` on every graphic box, plus face / cap / chin at every peak and
  every layout cut (frames n-1 / n). Then the mandatory **QA Gate** (`helpers/qa_gate.py --props ...`): it knows the band /
  split / takeover layout from props and allows the Takeover + `tailHoldSec` still. **Crop Previews**
  (`helpers/crop_previews.py --props ...`) before a render if the punch scale per moment is a judgment call.