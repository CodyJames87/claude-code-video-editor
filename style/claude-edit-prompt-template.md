# Claude Code edit brief: template

Who fills it in: you, or your "engineer" assistant (Grok, ChatGPT, or any AI chat; see `ENGINEER.md`).
Where it goes: a terminal in this repo -> `claude` -> paste everything between the lines.
Fill every {{SLOT}}. Delete optional lines you don't need.

This template is **profile-neutral**. It carries only what is specific to THIS clip. The profile's defaults (music/audio,
hook style, pacing/cuts, captions/text density, camera effects, SFX) come from the **"Template fills"** block in
`style/profiles/<profile>.md`; don't restate them here. Write a line here only to OVERRIDE a fill for this clip.
Name effects ONLY by their names in `style/effects-library.md` (e.g. "Steady Crawl", "Instant Punch", "Hook Caption",
"Long Slow Push", "Quick Punch", "Keyword Chip"). Want something not in the library? Propose it first; it is added only after the creator approves it.

---------------------------------------------------------------------------------------------------------------
Edit this reel. Follow CLAUDE.md exactly (pipeline, "Never break these", Deliver rules).
Read style\effects-library.md; every effect named below is from it.

PROFILE (required): {{PROFILE}}    (talking-head-motion | podcast | action | text-thread)
  Read style\profiles\README.md and style\profiles\{{PROFILE}}.md. Take music/audio, hook style, pacing/cuts,
  captions/text density, camera effects and SFX from that profile's "Template fills" block, on top of the shared base
  (CLAUDE.md + style\effects-library.md). Lines under OVERRIDES below win over the fills; hard rules win over both.

CLIP
- Source(s): {{CLIP_PATHS}}        (one file, or a list for a montage; copy each into public\media\ if it's elsewhere)
- Name: {{NAME}}                   (props\{{NAME}}.json, out\{{NAME}}-shorts.mp4)
- Range: {{RANGE}}                 ("whole file", start-end s, or a selects list: file + in/out + why)
- Framing: {{FRAMING}}             (where the speaker / action sits, e.g. "speaker center-right, face ~x 0.54, y 0.30 of 9:16; focus x 0.57")
- Rough cut: {{ROUGH_CUT}}         ("per profile fills", or "already cut")

STORY (this clip's moments)
- Subtle truth: {{TRUTH}}
- Beats / stretches: {{BEATS}}     (first words -> last words, or file + in/out; name the library effect for each if the
                                    profile's camera fills use one there)
- Punchlines / hits: {{HITS}}      ("words" ~sec, or file + contact time; name the library effect that lands on each)
- Extra (optional, max one per reel, a real detail only): {{EXTRA}}   (Zoom To Detail / Spotlight / B-Roll Speed Ramp + where)

TEXT (only what the profile uses)
- Hook: "{{HOOK_TEXT}}", accent word "{{HOOK_WORD}}"   (style + placement per profile fills; verbatim if spoken)
- Money words: {{MONEY_WORDS}}
- Skip from captions: {{SKIP_WORDS}}            (other speakers' "mm-hmm", "yeah")
- Card (optional, 1-2 max): {{CARD}}            (library card name, text, accent word, anchor words, seconds, position)

OVERRIDES (optional): {{OVERRIDES}}   (anything you asked to differ from the profile fills for this clip)

HARD RULES (every profile)
- Text never on the speaker's face (mouth, beard, chin) or any face, at any frame, incl. punch / push peaks and slow-mo holds.
- Whole cap and chin in frame at every scale; skip a camera move rather than crop a face.
- Screen shares / slides: the FULL 16:9 slide visible (scale to width, letterbox), never cropped; no camera moves while it's on.
- The brand.config.json accent is the only accent, one accent word per on-screen block; the support color is supporting
  only, never a caption highlight. On-screen words match the audio; never invent quotes.
- Audio cleanup first; finish.mjs loudness gate; QA gate; deliver for review. Never post anything.

DO
1. Probe every source (python helpers\probe.py). Run Audio Cleanup (node helpers\clean-audio.mjs) per CLAUDE.md step 2b.
2. Cut as the profile fills say (rough cut / selects + hard cuts / "already cut"). Transcribe word-level if the
   reel has captions or word anchors (npm run transcribe), fix misheard words (keep timings).
3. Write props\{{NAME}}.json from the profile fills + the moments above. Check every "at": {"word": ...} anchor exists in
   the captions JSON (a missing anchor silently starts at 0 s). Run node helpers\check-highlights.mjs props\{{NAME}}.json
   (HIGHLIGHTS: PASS) if there are captions.
4. Render: npx remotion render ShortsVideo out\{{NAME}}-shorts.mp4 --props=props\{{NAME}}.json
5. Finish: node helpers\finish.mjs out\{{NAME}}-shorts.mp4  (must print LOUDNESS: PASS; iPhone-safe yuv420p TV range.
   Exit 2/3 = QC FAIL, never deliver.)
6. QA gate: python helpers\qa_gate.py out\{{NAME}}-shorts_final.mp4 --props props\{{NAME}}.json (must PASS).
   Extra frames if needed: python helpers\qc_frames.py out\{{NAME}}-shorts_final.mp4 --times 0.03,1.0,{{QC_TIMES}},{{END-0.5}}
   ({{QC_TIMES}} = every punch / push peak, every effect window, every card mid, every layout or hard cut that matters).
   Open contact_sheet.jpg and LOOK. Shared: hook readable on frame 0 and off the face; cap + chin in frame and no text on
   any face at every peak; max one accent word per block; nothing important cropped; no SFX louder than a word.
   Then run the profile's own QC (its file + the library entries it uses). Fix and re-render if anything fails.
7. Deliver: python helpers\deliver.py out\{{NAME}}-shorts_final.mp4 --name {{NAME}}
   (your review folder from deliver.config.json, or review\ in this repo). Status "awaiting review". Do not post anything.

REPORT (short)
- Profile used; final + preview file names and where they went
- Audio cleanup before/after, finish.mjs loudness, QA gate verdict, contact sheet path
- Caption words you corrected; anything you changed from this plan or the profile fills, and why
- One debate-question caption draft (100-200 chars, 5 hashtags). Status: awaiting review.
---------------------------------------------------------------------------------------------------------------

## Filled example
See `prompts/PROMPTS.md` ("First edit") for a filled talking-head brief, and `examples/sample.props.json` for the props
file such a brief produces. On macOS / Linux use forward slashes in the paths.
