# Profile: text-thread

An animated, iMessage-style recreation of a REAL text conversation as a 1080x1920 reel: grey bubbles = them (left),
blue bubbles = me (right), typing dots, bubbles pop in and scroll, ~16-28 s, one accent-underlined money phrase, your
handle pinned near the bottom. Not a footage edit: no camera effects, no Lower-Third Captions, no Anton.

## Run it
1. Copy `threads/sample-thread.json` to `threads/<name>.json`. Set `name`, `contact.name` (+ `initial`), `handle`, and
   `messages` (`from: "them" | "me"`, `text`). Text is VERBATIM: keep casual spelling, never censor, never invent.
   Get permission from the other person before posting a real conversation, or change their name.
2. Timing is automatic (reading time per bubble). Override per message with `at` (appear time, s), `typing`, `hold`;
   global `pace`; `endHold` (default 4 s on the full thread at the end).
3. One money phrase: `"highlight": "<words>"` on ONE bubble; on blue bubbles use `"highlightStyle": "underline"`.
4. Render: `node helpers/render_text_thread.mjs threads/<name>.json` ->
   `out/<name>/<name>-shorts_final.mp4` (+ `-cover.png` when `output.coverAt` is set, + `.timeline.json` with QC times).
5. Sound: default `"sfxPreset": "soft"` = original tones synthesized on your machine (royalty-free). `"classic"` =
   brighter synthesized tones. `"custom"` = your own `sent.mp3`, `received.mp3`, `typing.mp3` in
   `assets/textthread/custom/` (e.g. made with ElevenLabs Sound Effects, or any sound you are licensed to use).
   `"sfx": false` = silent (add a trending sound in the app).
6. QC: frames at the `qc_times` in the timeline file: every bubble readable, nothing under the handle, one accent
   phrase. Then `python helpers/deliver.py <final>.mp4 --name <name>` for review.

## Rules
- Real conversations only, verbatim. No customer / private names without permission.
- Blue is the sent-bubble UI color, not a brand highlight; the accent color stays the one highlight.
- No music by default.
