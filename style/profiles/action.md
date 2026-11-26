# Profile: action

Sports, events, B-roll montages, behind-the-scenes: footage that is mostly motion, little or no talking.
Base: `CLAUDE.md` + `style/effects-library.md` (settings live there). This file only says which effects and when.

## Effects (library names)
| Effect | When |
|---|---|
| **Audio Cleanup** | On any natural audio you keep (cheers, hits, a spoken line). |
| Hook Caption / Statement Card | 1 short verbatim or title line in the first 2 s, one accent word, off any face or the action. |
| Lower-Third Captions | Only for real speech, sparse. |
| B-Roll Speed Ramp (optional) | The one extra: a stop-and-go ramp on a walk-up or a reveal. Never ramp speech. |
| Quick Punch (optional) | On a real hit / payoff moment only, from a wide base; skip it rather than crop a face. |
| **Whoosh / Pop SFX** | Very light: at most 1-2 pops; whooshes only on a real punch, never over a hit or a laugh. |

## Pacing + length
- About 20-45 s, fast and fun. Hard cuts on the beat (e.g. every 0.5 s at 120 BPM); trim dead space, settling and empty walk-ups.
- Keep authentic imperfections; no beauty filter or heavy grade. iPhone HDR (HLG) sources: tonemap to SDR.
- End on a smile / celebration / the payoff, not on a walk-away.

## Text
- ONE accent word per text block. Short, upper-case title lines; never on a face, a ball or a product in motion.

## Audio + music
- **Music is expected** for this profile (unlike talking-head / podcast): energetic instrumental, no vocals, royalty-free
  or generated (e.g. ElevenLabs Music) and licensed for your use. Natural sound ducked ~-13 dB under the music.
- Or leave `"music": null` and add a trending sound in the app.

## Template fills (drop-in values for `style/claude-edit-prompt-template.md`)
- **Music / audio:** a bed is expected (licensed / generated), natural sound ducked under it; Audio Cleanup on kept speech.
- **Hook:** one short title line, one accent word, first 2 s, off the action.
- **Pacing / cuts:** hard cuts on the beat, 20-45 s, trim dead space.
- **Camera:** mostly none; one Quick Punch on a real payoff at most.
- **SFX:** 1-2 pops max.

## QC (in addition to the base QC)
- Frame strip around every cut on the beat: no flash frames, nothing important cropped, no text on faces or the action.
