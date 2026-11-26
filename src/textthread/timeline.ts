// Timing for the "Text Thread" animated text post (iMessage-style). Pure functions, no React.
// Shared by TextThread.tsx (rendering) and calculateMetadata (duration). helpers/render_text_thread.mjs mirrors it.

export type ThreadMessage = {
  /** "them" = grey bubble, left (incoming). "me" = blue bubble, right (you, outgoing). */
  from: 'them' | 'me';
  /** Exact text, verbatim (casual spelling kept, never censored). */
  text: string;
  /** Explicit appear time (s). If set, it wins over the automatic timing. */
  at?: number;
  /** Seconds of typing dots before an incoming bubble (or the gap before an outgoing one in auto timing). */
  typing?: number;
  /** Auto timing only: seconds this bubble is read before the next thing happens. */
  hold?: number;
  /** Optional words inside this bubble to mark with the accent color (one idea only). */
  highlight?: string;
  /** "text" = accent-colored letters; "underline" = bold white letters + thin accent underline (use on the blue bubble). */
  highlightStyle?: 'text' | 'underline';
  /** Optional iMessage-style quoted reply: the exact text of the earlier message this one answers (shown small above it). */
  replyTo?: string;
};

export type ThreadSpec = {
  name: string;
  contact: { name: string; initial?: string; color?: string };
  messages: ThreadMessage[];
  /** Small handle pinned near the bottom (never scrolls). */
  handle?: string;
  /** Total length (s). Default: last bubble + endHold. */
  duration?: number;
  /** Auto timing: global speed multiplier (1 = default). */
  pace?: number;
  /** Bubbles already on screen at frame 0. Default 0. */
  startVisible?: number;
  /** Seconds held on the full thread at the end (when `duration` is not set). Default 4 (loops don't restart too fast). */
  endHold?: number;
  /** Render helper only: output folder / file stem and the cover frame time (s). */
  output?: { dir?: string; name?: string; coverAt?: number };
};

export type MessageTiming = { typingFrame: number | null; appearFrame: number };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
// Auto-timing read hold (~25 % more generous than the old clamp(0.5 + 0.045 * len, 0.9, 3.0)).
// Only used for messages without an explicit "at". Mirrored in helpers/render_text_thread.mjs + text_thread_sfx_classic.py.
export const defaultHold = (text: string) => clamp(0.62 + 0.056 * text.length, 1.1, 3.7);
export const defaultTyping = (text: string) => clamp(0.4 + 0.01 * text.length, 0.4, 0.7);
export const OUTGOING_GAP = 0.3;

export const buildTimeline = (spec: ThreadSpec, fps: number) => {
  const pace = spec.pace ?? 1;
  const sv = spec.startVisible ?? 0;
  const f = (s: number) => Math.round(s * pace * fps);
  const timings: MessageTiming[] = [];
  let t = 0;
  spec.messages.forEach((m, i) => {
    if (i < sv) {
      timings.push({ typingFrame: null, appearFrame: 0 });
      if (i === sv - 1) t = f(m.hold ?? defaultHold(m.text));
      return;
    }
    if (m.at !== undefined) {
      const appearFrame = Math.round(m.at * fps);
      const ty = m.from === 'them' ? Math.round((m.at - (m.typing ?? defaultTyping(m.text))) * fps) : null;
      timings.push({ typingFrame: ty, appearFrame });
      t = appearFrame + f(m.hold ?? defaultHold(m.text));
      return;
    }
    if (m.from === 'them') {
      const typingFrame = t;
      t += f(m.typing ?? defaultTyping(m.text));
      timings.push({ typingFrame, appearFrame: t });
    } else {
      t += f(m.typing ?? OUTGOING_GAP);
      timings.push({ typingFrame: null, appearFrame: t });
    }
    t += f(m.hold ?? defaultHold(m.text));
  });
  const last = timings.length ? timings[timings.length - 1].appearFrame : 0;
  const durationInFrames = spec.duration
    ? Math.round(spec.duration * fps)
    : Math.max(1, last + Math.round((spec.endHold ?? 4) * fps));
  return { timings, durationInFrames };
};
