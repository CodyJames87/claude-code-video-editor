# Editing profiles

A profile is a recipe for one KIND of video. Every edit brief names one. The shared base never changes:

- `CLAUDE.md`: hard rules, the pipeline (probe -> clean audio -> transcript -> plan -> props -> render -> finish -> QA
  gate -> deliver for review), style defaults, face clearance.
- `style/effects-library.md`: every effect's settings.

A profile picks effects BY NAME from the library and sets pacing, captions, audio and music. It never redefines an
effect and never overrides a hard rule (text off the face; one accent word per caption block; audio cleanup first;
loudness gate; QA gate before delivery; nothing gets posted by the editor).

## Choosing a profile
- One person talking to camera (phone / webcam) -> `talking-head-motion`
- Two or more people (podcast, interview, studio), or plain lower-third talking clips -> `podcast`
- Mostly motion, little talking (sports, events, montage) -> `action`
- A recreated text-message conversation (no footage) -> `text-thread`
- No profile named: ask which one, or default to `talking-head-motion` for a single speaker.

## Profiles
| Profile | File |
|---|---|
| talking-head-motion | `talking-head-motion.md` |
| podcast | `podcast.md` |
| action | `action.md` |
| text-thread | `text-thread.md` |

## Adding a profile
Copy the closest one, name it, list the library effects it uses and when, its pacing, captions, audio, and the
"Template fills" block. New effects go into `style/effects-library.md` first (proposed, approved, then added).
