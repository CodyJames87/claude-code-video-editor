# Copy-paste prompts

Paste these into Claude Code (in this repo), or give them to your engineer assistant (`ENGINEER.md`).
Replace the [brackets].

## First edit (talking head)
```
Here is a new video: public/media/[name].mp4. Profile: talking-head-motion. Name: [name].
Follow CLAUDE.md exactly. Read style/effects-library.md first.
The point of this video: [one sentence]. The hook is my line "[exact words]".
Highlight these money words: [word], [word].
Mix the zooms: a Long Slow Push over the setup, a Short Slow Push on [beat], a Quick Punch on "[punchline words]".
Tell me your plan in 3-5 lines, then render, finish, run the QA gate, look at the contact sheet, and deliver for review.
Report: file path, audio before/after, loudness, QA verdict, any caption words you fixed, and a caption draft.
```

## Lead-magnet reel with a comment keyword
```
Same as a normal talking-head edit, plus: when I say "comment [KEYWORD]", show a Keyword Chip "Type [KEYWORD]"
(keyword in the accent color). End on a Takeover CTA with my exact words "[CTA line]", running to the last frame
with tailHoldSec 1.0. Cut any dead stare between my last line and the end card. Everything after "[last line]"
that repeats itself: cut it (EDL Remap with --recut-media).
```

## Logo when I name a tool
```
Every time I say "[tool name]", show a Logo Chip with public/logos/[file].png for ~1.7 s, top-left box
[60, 280, 620, 140], placed where face_safe.py says SAFE. If the logo file is missing, use a text chip and tell me.
```

## Revision notes
```
v2 notes: [e.g. the zoom is too fast: slow it down / cut from "[X]" to the end card / take the progress bar off /
the captions say "[wrong]" at 0:19, I said "[right]"]. Change only that. Keep everything else. Re-render, finish,
QA gate, deliver as v2, and tell me exactly what changed.
```

## Podcast clip
```
Here is a podcast episode: public/media/[name].mp4. Profile: podcast. Transcribe it, then pitch me 3-5 clip moments
(start-end, the hook line, why it works). Wait for my pick before you cut or render anything.
```

## Text-thread reel
```
Here's a real text conversation. Recreate it as a text-thread reel (style/profiles/text-thread.md).
Contact name "[first name]", handle @[your handle]. Grey = them, blue = me. Use the text exactly, typos included:
[paste the thread, labeled THEM / ME in order]
One accent underline on "[money phrase]" only. Default soft tones, no music. Give me the final and a cover frame.
```

## "Edit it like this reel"
```
Here's a reference reel file: [path]. Run the Style Breakdown (style/style-breakdown.md). Tell me what it does in our
effect names, what conflicts with CLAUDE.md, and what would be new. Don't change any edit. Wait for my pick.
```

## Find footage
```
Index my footage (python helpers/footage_catalog.py index) and find every clip where I talk about "[topic]".
Give me the file, timestamp, and the sentence.
```

## Lock in what we learned
```
I approved [name] with these notes: [what to keep, what to change, what to never do again].
Update the [profile] profile (and the effects library if a setting changed) so the next edit starts from this version.
Show me the diff before you save it.
```
