# Reference style breakdown

Measures how a reference reel is edited (camera moves, cuts, captions, faces, color, audio) and writes it up in our
effect vocabulary, with a CONFLICTS list against the CLAUDE.md rules. It is a **read-only study tool**: it never changes an edit.

## When to use
- you supply a reference reel FILE ("edit it like this one", "what is this creator doing?").
- Before proposing a new effect: measure the reference first, then propose by name.
- Not for QC of our own renders (use `qc_frames.py` / `face_safe.py`), though it runs fine on them as a known-answer check.

## Files only, no downloads
- Only files you put on disk. No yt-dlp, no URL scraping, no downloading from IG / TikTok / YouTube / Facebook.
  The tool refuses URLs. If you send a link, ask for the file.
- The input is never modified; outputs never go next to it.

## Command
```
python helpers\style_breakdown.py <reel.mp4> [--captions <sidecar>.captions.json] [--captions-offset S] [--out out\style-breakdown\<name>] [--name N]
```
- `--captions`: optional word-level transcript (our `captions.json` or `{words:[...]}`), for words, wpm and words per page.
  `--captions-offset`: seconds added to the sidecar times if the edit trimmed the source or moved words for a hook.
- Takes ~1 min for a 36 s 1080x1920 reel. Exit 0 = done.

## Outputs (`out\style-breakdown\<name>\`)
| File | What it is |
|---|---|
| `contact_sheet.jpg` | One frame per cut / punch / push end (+ start, end), max 24, labeled time + kind. LOOK AT IT FIRST. |
| `cuts.csv` / `cuts.json` | Every event: time, frame, kind (hard cut, layout cut, jump cut, punch in/out, push), ratio, frames. |
| `breakdown.json` | All numbers: pacing, captions, faces, color/graphics, audio, conflicts, thresholds used. |
| `style_guide.md` | Camera / Captions / Pacing / Color & graphics / Audio, "In our vocabulary", "What we could borrow", CONFLICTS. |

## How to read it
- **Punch in xR over N frames**: R is the jump between frames; "peak ~" adds a push it lands on. 1 frame = Instant Punch;
  2-4 frames = an eased PunchIn (old `inFrames: 4`); ~12 frames to ~1.30 = Hero Push.
- **Push linear / eased**: slow zoom inside a shot (rate in scale/s). Linear = Steady Crawl, eased = Eased Push. A push that
  ends in a snap-out counts as a camera move even when the speaker moves under it.
- **Not counted** lines: scale drift that is jittery (the speaker leaning in/out) or happens with no full-size face (B-roll
  or a graphic moving inside a Split Frame).
- **Jump cut** = same shot spliced (the head jumps); **layout cut** = the flat-band layout changes (Solo <-> Split);
  **overlay change** = a card fade, chip or hand gesture, not a cut.
- **Captions**: zone, lines per block, line height (font-size proxy), fill colors, highlight words per block, page flips.
- **CONFLICTS**: each item is CONFLICT / OK / UNKNOWN with when, evidence and the rule. UNKNOWN = check by eye.

## Hard STOP
- Present the contact sheet, the style guide and the CONFLICTS to you, then **wait for you to pick** what to apply.
- Never apply a style, write props, touch `src\` or silently add an effect because a reference did it.
- Anything not already in `style/effects-library.md` is a PROPOSAL (marked "NEW — would need your approval").
  It goes into the library only after you approve it.
-  rules beat the reference: brand.config.json colors, one accent word per block, text never on the face, cap + chin in
  frame, no music bed by default, light SFX, verbatim captions.

## Limits
- **No OCR**: caption words, upper vs lower case and verbatim vs paraphrase cannot be read. Paraphrase is always UNKNOWN.
- **Faces**: Haar (via `face_safe.py`) misses profile turns, hands over the face and small faces in split bands. Its cap
  margin is conservative, so cap crops are "possible" unless the face box itself touches the edge.
- **Cuts are heuristic** (ORB + RANSAC between frames): a cut between two similar angles can read as a punch; a splice
  during a big gesture can be missed. Absolute scales drift on tight crops when the speaker leans, so punch RATIOS are
  more trustworthy than the absolute "peak" values.
- **Pushes**: an eased push cut short by a punch looks linear. Rates are approximate on tight crops.
- **Audio**: SFX hits are compared with a chance level from random times; whoosh vs pop and a quiet whoosh under speech
  can't be separated reliably (confidence is printed). Music bed = level in the quietest moments.
- **AI likenesses**: not detectable automatically; check by eye.
