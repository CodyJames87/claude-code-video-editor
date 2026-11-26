// "Text Thread" animated text post: an iMessage-style recreation of a real conversation, 1080x1920.
// Spec JSON lives in threads/<name>.json (passed as --props). Not a footage edit: no camera, no captions, no Anton.
// Colors: white bg, ink #212121 text, neutral #595959 handle, light grey incoming bubble, iMessage blue outgoing
// bubble (the sent-bubble UI color, chosen for white-text contrast; NOT a brand highlight). The brand accent stays the
// only brand accent (one highlighted idea). Avatar green is the contact-photo UI color the original brief asked for.
import React from 'react';
import { AbsoluteFill, CalculateMetadataFunction, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND } from '../brand';
import { buildTimeline, ThreadMessage, ThreadSpec } from './timeline';

export const THREAD_FPS = 30;

const C = {
  bg: BRAND.white,
  incoming: '#E9E9EB', // iMessage received bubble
  incomingText: BRAND.ink,
  outgoing: '#007AFF', // iMessage sent bubble; white text ~4.0:1
  outgoingText: BRAND.white,
  ui: BRAND.neutral,
  rule: BRAND.hairline,
  avatar: '#34C759', // contact-photo green (per brief), white initials
};

// Layout (px, 1080x1920) inside the IG Reels safe zones:
// header below the top 160 px; handle + last bubble above the bottom 280 px; right margin 140 px (IG action column).
const HEADER_TOP = 178;
const HEADER_BOTTOM = 400;
const VIEW_TOP = HEADER_BOTTOM + 2;
const VIEW_BOTTOM = 1548;
const HANDLE_Y = 1574; // handle text top; ~40 px tall -> bottom ~1614 < 1640
const LEFT = 72; // bubble edge; the tail reaches ~16 px further out (>= 56 px from the edge)
const RIGHT = 158; // bubble edge; tail tip stays >= 140 px from the right edge (IG action column)
const PAD = 24; // inner row padding so the tails never clip (subtracted from the margins above)
const FONT = 38;
const SAME_GAP = 6;
const SWITCH_GAP = 22;

const Tail: React.FC<{ side: 'left' | 'right'; color: string }> = ({ side, color }) => (
  <svg
    width={32}
    height={30}
    viewBox="0 0 40 36"
    style={{ position: 'absolute', bottom: 0, [side]: -16, transform: side === 'left' ? 'scaleX(-1)' : undefined }}
  >
    <path d="M0,0 H20 C20,18 26,30 40,36 C26,37 10,34 0,28 Z" fill={color} />
  </svg>
);

const BubbleText: React.FC<{ m: ThreadMessage }> = ({ m }) => {
  if (!m.highlight) return <>{m.text}</>;
  const i = m.text.indexOf(m.highlight);
  if (i < 0) throw new Error(`highlight "${m.highlight}" not found in "${m.text}"`);
  const hl = m.text.slice(i, i + m.highlight.length);
  const style: React.CSSProperties =
    (m.highlightStyle ?? 'text') === 'underline'
      ? {
          fontWeight: 700,
          textDecorationLine: 'underline',
          textDecorationColor: BRAND.accent,
          textDecorationThickness: 5,
          textUnderlineOffset: 7,
          textDecorationSkipInk: 'none',
        }
      : { color: BRAND.accent, fontWeight: 700 };
  style.whiteSpace = 'nowrap'; // keep the highlighted idea on one line
  return (
    <>
      {m.text.slice(0, i)}
      <span style={style}>{hl}</span>
      {m.text.slice(i + m.highlight.length)}
    </>
  );
};

const Bubble: React.FC<{ m: ThreadMessage; tail: boolean }> = ({ m, tail }) => {
  const me = m.from === 'me';
  const bg = me ? C.outgoing : C.incoming;
  const r = 38;
  return (
    <div
      style={{
        position: 'relative',
        maxWidth: '76%',
        background: bg,
        color: me ? C.outgoingText : C.incomingText,
        fontFamily: BRAND.headlineFont,
        fontWeight: 500,
        fontStyle: 'normal',
        fontSize: FONT,
        lineHeight: 1.3,
        padding: '18px 30px',
        borderRadius: r,
        borderBottomRightRadius: me && tail ? 14 : r,
        borderBottomLeftRadius: !me && tail ? 14 : r,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      <BubbleText m={m} />
      {tail ? <Tail side={me ? 'right' : 'left'} color={bg} /> : null}
    </div>
  );
};

// Optional quoted reply (only when a message sets `replyTo`; threads without it render exactly as before):
// a small faded copy of the quoted message on its sender's side, a thin connector curving down to the reply bubble.
const ReplyBlock: React.FC<{ m: ThreadMessage; msgs: ThreadMessage[]; tail: boolean }> = ({ m, msgs, tail }) => {
  const quoted = msgs.find((x) => x.text === m.replyTo);
  const quoteFrom = quoted ? quoted.from : m.from === 'me' ? 'them' : 'me';
  const quoteLeft = quoteFrom === 'them';
  const replyRight = m.from === 'me';
  const line = '#C7C7CC';
  const GAP = 14;
  const quote = (
    <div
      style={{
        maxWidth: '68%',
        background: quoteFrom === 'me' ? C.outgoing : C.incoming,
        color: quoteFrom === 'me' ? C.outgoingText : C.incomingText,
        opacity: 0.55,
        fontFamily: BRAND.headlineFont,
        fontWeight: 500,
        fontStyle: 'normal',
        fontSize: 29,
        lineHeight: 1.28,
        padding: '12px 24px',
        borderRadius: 30,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {m.replyTo}
    </div>
  );
  const connector = (
    <div style={{ position: 'relative', flex: '1 1 0', alignSelf: 'stretch' }}>
      <div
        style={{
          position: 'absolute',
          top: '50%',
          bottom: -GAP,
          [quoteLeft ? 'left' : 'right']: 10,
          [quoteLeft ? 'right' : 'left']: 70,
          borderTop: `3px solid ${line}`,
          [quoteLeft ? 'borderRight' : 'borderLeft']: `3px solid ${line}`,
          [quoteLeft ? 'borderTopRightRadius' : 'borderTopLeftRadius']: 26,
        }}
      />
    </div>
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {quoteLeft ? quote : connector}
        {quoteLeft ? connector : quote}
      </div>
      <div style={{ display: 'flex', justifyContent: replyRight ? 'flex-end' : 'flex-start', marginTop: GAP }}>
        <Bubble m={m} tail={tail} />
      </div>
    </div>
  );
};

const TypingBubble: React.FC<{ localFrame: number; fps: number }> = ({ localFrame, fps }) => (
  <div style={{ position: 'relative', background: C.incoming, borderRadius: 38, padding: '27px 28px', display: 'flex', gap: 11 }}>
    {[0, 1, 2].map((k) => {
      const w = 0.5 + 0.5 * Math.sin((localFrame / fps) * Math.PI * 2 * 1.6 - k * 0.9);
      return (
        <div
          key={k}
          style={{ width: 16, height: 16, borderRadius: 8, background: '#8E8E93', opacity: 0.35 + 0.6 * w, transform: `translateY(${-3 * w}px)` }}
        />
      );
    })}
    <div style={{ position: 'absolute', left: -3, bottom: -3, width: 18, height: 18, borderRadius: 9, background: C.incoming }} />
    <div style={{ position: 'absolute', left: -14, bottom: -13, width: 9, height: 9, borderRadius: 5, background: C.incoming }} />
  </div>
);

/** A row that grows from 0 to its natural height (grid 0fr -> 1fr), so older bubbles slide up smoothly. */
const Row: React.FC<{ grow: number; gapTop: number; align: 'left' | 'right'; children: React.ReactNode }> = ({ grow, gapTop, align, children }) => (
  <div style={{ display: 'grid', gridTemplateRows: `${Math.max(0, Math.min(1, grow))}fr`, flexShrink: 0 }}>
    <div
      style={{
        minHeight: 0,
        overflow: grow < 1 ? 'hidden' : 'visible',
        paddingTop: gapTop,
        paddingLeft: PAD,
        paddingRight: PAD,
        display: 'flex',
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
      }}
    >
      {children}
    </div>
  </div>
);

const Header: React.FC<{ name: string; initial: string; color: string }> = ({ name, initial, color }) => (
  <div style={{ position: 'absolute', top: HEADER_TOP, left: 0, right: 0, height: HEADER_BOTTOM - HEADER_TOP, borderBottom: `2px solid ${C.rule}` }}>
    <svg width={28} height={48} viewBox="0 0 34 58" style={{ position: 'absolute', left: LEFT, top: 50 }}>
      <path d="M28,4 L6,29 L28,54" fill="none" stroke={C.outgoing} strokeWidth={7} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    <div style={{ position: 'absolute', left: 0, right: 0, top: 6, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div
        style={{
          width: 120,
          height: 120,
          borderRadius: 60,
          background: color,
          color: BRAND.white,
          fontFamily: BRAND.headlineFont,
          fontWeight: 600,
          fontSize: 48,
          letterSpacing: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {initial}
      </div>
      <div style={{ marginTop: 14, fontFamily: BRAND.headlineFont, fontWeight: 600, fontSize: 34, color: BRAND.ink, display: 'flex', alignItems: 'center', gap: 10 }}>
        {name}
        <svg width={13} height={22} viewBox="0 0 14 24">
          <path d="M3,3 L11,12 L3,21" fill="none" stroke={C.ui} strokeWidth={3.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  </div>
);

export const TextThread: React.FC<ThreadSpec> = (spec) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { timings } = buildTimeline(spec, fps);
  const msgs = spec.messages;
  const sv = spec.startVisible ?? 0;

  const rows: React.ReactNode[] = [];
  let prevFrom: 'them' | 'me' | null = null;
  msgs.forEach((m, i) => {
    const t = timings[i];
    const gap = prevFrom === null ? 0 : prevFrom === m.from ? SAME_GAP : SWITCH_GAP;

    // typing dots (incoming): grow in, then collapse over 4 frames as the bubble arrives
    if (t.typingFrame !== null && frame >= t.typingFrame && frame < t.appearFrame + 4) {
      const g = spring({ frame: frame - t.typingFrame, fps, config: { damping: 18, stiffness: 220, mass: 0.5 } });
      const c = interpolate(frame, [t.appearFrame, t.appearFrame + 4], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
      rows.push(
        <Row key={`typing-${i}`} grow={Math.min(1, g) * c} gapTop={gap} align="left">
          <div style={{ opacity: Math.min(1, g * 1.5) * c, transform: `scale(${0.7 + 0.3 * Math.min(1, g)})`, transformOrigin: 'bottom left' }}>
            <TypingBubble localFrame={frame - t.typingFrame} fps={fps} />
          </div>
        </Row>,
      );
    }

    if (frame < t.appearFrame) return;
    // snap to exactly 1 once settled (0.8 s) so end holds are pixel-static (no sub-pixel spring tail)
    const since = frame - t.appearFrame;
    const pp = i < sv || since >= Math.round(0.8 * fps) ? 1 : spring({ frame: since, fps, config: { damping: 15, stiffness: 210, mass: 0.6 } });
    // tail only on the last bubble of a same-sender run that is on screen right now
    const next = msgs[i + 1];
    const nextShown = next && frame >= timings[i + 1].appearFrame;
    const tail = !(next && next.from === m.from && nextShown);
    const me = m.from === 'me';
    rows.push(
      <Row key={`msg-${i}`} grow={pp} gapTop={gap} align={me ? 'right' : 'left'}>
        <div
          style={{
            display: 'flex',
            justifyContent: me ? 'flex-end' : 'flex-start',
            width: '100%',
            opacity: Math.min(1, pp * 2),
            transform: me ? `translateY(${(1 - Math.min(1, pp)) * 36}px) scale(${0.8 + 0.2 * pp})` : `scale(${0.6 + 0.4 * pp})`,
            transformOrigin: me ? 'bottom right' : 'bottom left',
          }}
        >
          {m.replyTo ? <ReplyBlock m={m} msgs={msgs} tail={tail} /> : <Bubble m={m} tail={tail} />}
        </div>
      </Row>,
    );
    prevFrom = m.from;
  });

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {/* Thread viewport: fills from the top; once full, the newest bubble stays pinned to the bottom and older ones
          scroll up under a soft fade below the header (spacer flex trick, no DOM measuring). */}
      <div
        style={{
          position: 'absolute',
          top: VIEW_TOP,
          height: VIEW_BOTTOM - VIEW_TOP,
          left: LEFT - PAD,
          right: RIGHT - PAD,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
          paddingTop: 28,
          maskImage: 'linear-gradient(to bottom, transparent 0px, black 72px)',
          WebkitMaskImage: 'linear-gradient(to bottom, transparent 0px, black 72px)',
        }}
      >
        {rows}
        <div style={{ flex: '1 1 0', minHeight: 0 }} />
      </div>
      <Header name={spec.contact.name} initial={spec.contact.initial ?? spec.contact.name.slice(0, 1).toUpperCase()} color={spec.contact.color ?? C.avatar} />
      {spec.handle ? (
        <div
          style={{
            position: 'absolute',
            top: HANDLE_Y,
            left: 0,
            right: 0,
            textAlign: 'center',
            fontFamily: BRAND.headlineFont,
            fontWeight: 600,
            fontSize: 28,
            letterSpacing: 0.5,
            color: C.ui,
          }}
        >
          {spec.handle}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const calcThreadMetadata: CalculateMetadataFunction<ThreadSpec> = async ({ props }) => ({
  durationInFrames: buildTimeline(props, THREAD_FPS).durationInFrames,
  fps: THREAD_FPS,
});

export const defaultThreadProps: ThreadSpec = {
  name: 'demo-thread',
  contact: { name: 'Friend', initial: 'F' },
  handle: '@yourhandle',
  messages: [
    { from: 'them', text: 'Demo message' },
    { from: 'me', text: 'Render with --props=threads/<name>.json' },
  ],
};
