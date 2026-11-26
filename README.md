# Claude Code Video Editor

**Edit your own talking-head and short-form videos with AI.** Clone this repo, open it in
[Claude Code](https://docs.anthropic.com/en/docs/claude-code), and tell it "here's a new video, please edit it."
It cuts, cleans the audio, captions, zooms, adds graphics, checks its own work, and hands you a finished vertical
video to review. You stay the director: nothing gets posted unless you post it.

This is the same system I use for my own Reels, packaged so you can run it on your computer.
Free, MIT licensed. Not affiliated with Anthropic or xAI.

**The setup in one picture**

```
 You  --talk-->  Your assistant (Grok, ChatGPT, ...)  --writes a brief-->  Claude Code in this repo  --renders-->  video
  ^                    the "engineer"                                        the "editor"                            |
  |__________________________________ you review every cut, and post it yourself _______________________________|
```

- **The editor** is Claude Code running in this folder. It reads `CLAUDE.md` (the rulebook) and
  `style/effects-library.md` (every effect, by name) on every job.
- **The engineer** is the AI assistant you already talk to (we use Grok). You talk like a person; it turns that into
  a precise brief for Claude Code and checks the result against your rules. See [`ENGINEER.md`](ENGINEER.md).
  No assistant? Paste the prompts in [`prompts/PROMPTS.md`](prompts/PROMPTS.md) into Claude Code yourself.

---

## 5-minute setup

**1. Install the tools** (once)

| Tool | Why | Get it |
|---|---|---|
| Node.js 18+ (20 or 22 LTS recommended) | Remotion renders the video | https://nodejs.org |
| Python 3.10+ | quality checks, face-safe checks, helpers | https://www.python.org/downloads (Windows: tick "Add to PATH") |
| ffmpeg | audio cleanup, encoding | Windows: `winget install Gyan.FFmpeg` / Mac: `brew install ffmpeg` / Linux: `sudo apt install ffmpeg` |
| Git | to clone this repo | https://git-scm.com |
| Claude Code | the editor | https://docs.anthropic.com/en/docs/claude-code (needs a Claude subscription or API key) |

**2. Clone and install**

```bash
git clone https://github.com/CodyJames87/claude-code-video-editor.git
cd claude-code-video-editor
npm install
python -m pip install -r requirements.txt      # Mac/Linux: python3 -m pip install -r requirements.txt
```

**3. Check everything works** (makes a 15-second sample clip, renders it with the motion effects, runs the
loudness gate and the QA gate)

```bash
npm run demo
```

You should end on `DEMO OK`. Open `out/sample-shorts_final.mp4` and the contact sheet it prints. (The sample has no
real person in it, so the face check honestly says "UNSURE" and the demo accepts that. On your own footage, don't.)
`npm run setup:check` prints what's installed if something fails.

**4. Local transcription** (once, free, no API key): `npm run setup:whisper` downloads whisper.cpp + the
`medium.en` model (~1.5 GB). Smaller / faster: `WHISPER_MODEL=small.en npm run setup:whisper`
(Windows PowerShell: `$env:WHISPER_MODEL="small.en"; npm run setup:whisper`).
Use the same `WHISPER_MODEL` value when you run `npm run transcribe`. On macOS/Linux this compiles whisper.cpp,
so you need `make` and a C++ compiler (macOS: `xcode-select --install`; Ubuntu/Debian: `sudo apt install make g++`).
Windows downloads a prebuilt binary. Rather not install anything? Transcribe with ElevenLabs/Descript and convert:
`node scripts/transcribe.mjs public/media/clip.mp4 --from transcript.json`.

**5. Make it yours**
- Colors + handle: edit [`brand.config.json`](brand.config.json) (`accent` = your one highlight color).
  Orange example: `examples/brand.orange.json`.
- Logos: put your own logo files in `public/logos/` (see [`public/logos/README.md`](public/logos/README.md)).
- Review folder (optional): copy `deliver.config.example.json` to `deliver.config.json` and point it at a synced
  Google Drive / Dropbox folder so finished cuts land on your phone. Default: `review/` in this repo.

**6. Open it in Claude Code**

```bash
claude
```

That's it. Claude Code reads `CLAUDE.md` automatically.

---

## Your first edit

1. Film a vertical talking-head video (phone is fine). Leave a little room above your head.
2. Copy it into `public/media/`, e.g. `public/media/my-first-reel.mp4`.
3. In Claude Code, paste:

> Here is a new video: public/media/my-first-reel.mp4. Profile: talking-head-motion. Please edit it.
> Name it my-first-reel. Follow CLAUDE.md exactly. Tell me your plan in 3-5 lines before you render.

4. It will probe the file, clean the audio, transcribe it, plan the edit (hook, zooms, captions, graphics),
   write `props/my-first-reel.json`, render, run the loudness gate and the QA gate, and put the final in `review/`.
5. Watch it. Tell it what to change in plain words ("slow the zoom down", "cut the part after I say 'guide'",
   "put my logo up when I say the company name"). It edits the props and re-renders.

More copy-paste prompts (first edit, revisions, CTA reels, text-thread reels, "edit it like this reel",
turning an approved cut into a reusable profile): [`prompts/PROMPTS.md`](prompts/PROMPTS.md).

---

## Connect Grok (or any assistant) as the engineer

The editor does the cutting; the engineer does the thinking and the checking. Two ways to set it up:

- **Chat only (works with any assistant):** paste [`ENGINEER.md`](ENGINEER.md) into Grok / ChatGPT / Claude as its
  instructions (or the first message of a project). Then talk to it about your video. It writes the brief using
  `style/claude-edit-prompt-template.md`; you paste the brief into Claude Code and paste Claude's report back.
- **Hands-on (assistants that can run commands on your computer):** give the assistant access to this repo
  (a GitHub connection to your fork, and/or a terminal on the PC where the repo lives). It can then run
  Claude Code headless for you, e.g. `claude -p "$(cat brief.txt)"`, read the report and the QA contact sheet, and come
  back with the cut. Keep the rules in `ENGINEER.md`: the assistant never posts for you, and you approve every
  caption and time yourself.

---

## What's in it

**Profiles** (`style/profiles/`): `talking-head-motion` (one person to camera), `podcast` (interviews, multi-person),
`action` (sports / events / montage), `text-thread` (animated text-message reel).

**Effects** (`style/effects-library.md`, all original Remotion / Python code):

| Effect | What it does |
|---|---|
| Karaoke Captions | Two-line Anton captions, the spoken word lights up, ONE highlighted money word per block |
| Lower-Third Captions | Same captions without the lit word (podcast default) |
| Long Slow Push | One continuous 15-20 s creep in (to ~1.12), then hold; carries a setup or story stretch |
| Short Slow Push | A 4-5 s eased push on a short emphasis beat |
| Quick Punch | A fast punch-in on a punchline, smooth return (never a glitchy 1-frame snap-back) |
| Steady Crawl / Eased Push / Hero Push / Instant Punch | Shorter classic zooms for podcast-style cuts |
| Title Banner / Hook Caption / Hook Card | The opening line, verbatim, readable on frame 0 |
| Count-Up Card | A number you say counts up and lands exactly as you say it |
| Callout Chip | A short phrase you say, in a chip placed where the face-safe check says it's clear |
| Logo Chip | Your logo (or a tool's logo you're allowed to use) pops up when you name it |
| Keyword Chip | "TYPE EDIT" pops up when you say your comment keyword |
| Takeover CTA | Full-screen end card ("Comment EDIT and I'll send you the guide") |
| Solo / Split / Takeover Frame | Headroom band layout, split-screen with a graphic, full-screen graphic |
| Browser-Frame B-Roll | A real public web page scrolling inside a clean browser frame |
| Statement Card, Process Flow, Comparison Card, Full-Screen List, Pill List | Simple text cards |
| Zoom To Detail, Spotlight, B-Roll Speed Ramp | One "extra" per reel for a real detail |
| Text Thread | iMessage-style animated recreation of a real text conversation |
| Audio Cleanup, Whoosh / Pop SFX | Clean, -14 LUFS voice; subtle synthesized whoosh / pop (royalty-free) |

**Tools** (`style/tools.md`): **QA Gate** (black / freeze / flash / loudness / clipping / cut seams / text-on-face check,
blocks delivery on FAIL), **Crop Previews** (loose vs tight framing per moment, flags any crop that would cut off the
head), **Face-safe check** (is this graphic box clear of the face for the whole window?), **EDL Remap** (re-time every
caption and graphic after you cut something), **Footage Catalog** (search your clips by what you said), **Hook
Variations** (A/B openings from real spoken hooks), **Style Breakdown** (measure how a reference reel is edited),
**Review Page** (local frame-accurate review page with notes).

---

## Folder map

```
CLAUDE.md                 the editor's rulebook (Claude Code reads it on every job)
ENGINEER.md               instructions for your assistant (Grok, ChatGPT, ...)
prompts/PROMPTS.md        copy-paste prompts
brand.config.json         your colors + handle
style/                    effects-library.md, tools.md, profiles/, edit-brief template
src/                      Remotion compositions + components (ShortsVideo 9:16, FeedVideo 4:5, LongForm 16:9, TextThread)
helpers/                  Python + Node helpers (audio, QA gate, face-safe, crop previews, EDL remap, catalog, deliver ...)
scripts/                  whisper.cpp install + transcription
examples/                 sample generator, sample props, brand example, sample EDL
threads/                  text-thread specs
public/media/             your videos + captions (git-ignored)   public/logos/  your logos (git-ignored)
public/fonts/             Anton, Plus Jakarta Sans, DM Sans (SIL Open Font License)
public/sfx/               whoosh.wav + pop.wav (synthesized by helpers/make_sfx.py; free to use)
```

## Limits and honest notes

- You need a Claude Code plan (subscription or API). Rendering is local and free; a 60 s reel renders in a few
  minutes on a normal laptop.
- The face-safe check uses OpenCV's classic face detector: it can miss faces in profile or behind hands, which is why
  "UNSURE" counts as a FAIL until you look at the frames. It's a gate, not a replacement for watching the cut.
- Logos of other companies are not included. Use your own, or download official files from the brand pages linked in
  `public/logos/README.md` and follow their rules.
- No music or third-party sound effects are included. Add a trending sound in the app, or generate / license your own.
- Optional extras the editor can use if you connect them: Descript (rough cut of long talks), ElevenLabs (speech-to-text,
  sound effects, voice isolation). Neither is required.
- Windows, Mac and Linux all work. On Windows type `python`, on Mac/Linux `python3` (the npm scripts find whichever you have).

## Troubleshooting

- `npm install` warns about install scripts (`esbuild`): safe to ignore, renders still work. Or run
  `npm install-scripts approve esbuild`.
- `cv2 has no attribute CascadeClassifier`: you have OpenCV 5; install from `requirements.txt` (`opencv-python-headless<5`).
- First render is slow: Remotion downloads a headless Chrome once.
- `python helpers/env_check.py` prints what's installed and does a smoke render.

## License

MIT (see `LICENSE`). Fonts: SIL Open Font License (see `public/fonts/OFL-*.txt`).
Claude and Claude Code are trademarks of Anthropic. Grok is a trademark of xAI. This project is independent and is not
endorsed by either.
