// Offsets on the wire are Unicode code points into the original text, end exclusive (Section
// 18.3). JS strings index UTF-16 code units, so an astral character (e.g. an emoji) before a span
// shifts every later index by one. Every highlighted span is converted AND checked against `quote`;
// a span that does not match is never highlighted (showing the wrong words is worse than none).

/** UTF-16 index of code point `cp` in `text`, or null if `cp` is past the end. */
export function codePointToUtf16(text: string, cp: number): number | null {
  if (!Number.isInteger(cp) || cp < 0) return null;
  let i = 0;
  for (let n = 0; n < cp; n += 1) {
    if (i >= text.length) return null;
    const c = text.codePointAt(i) ?? 0;
    i += c > 0xffff ? 2 : 1;
  }
  return i;
}

export type SpanCheck =
  | { ok: true; start: number; end: number; text: string }
  | { ok: false; reason: 'out_of_range' | 'quote_mismatch' };

/** Convert a code-point span and verify the slice equals the server's quote. */
export function checkSpan(text: string, start: number, end: number, quote: string): SpanCheck {
  const s = codePointToUtf16(text, start);
  const e = codePointToUtf16(text, end);
  if (s === null || e === null || e < s) return { ok: false, reason: 'out_of_range' };
  const slice = text.slice(s, e);
  if (slice !== quote) return { ok: false, reason: 'quote_mismatch' };
  return { ok: true, start: s, end: e, text: slice };
}

export type Segment = { text: string; mark: boolean; first: boolean };

/** Split text into plain and marked segments for already-verified UTF-16 ranges (merged). */
export function segments(text: string, ranges: ReadonlyArray<{ start: number; end: number }>): Segment[] {
  const sorted = ranges.filter((r) => r.end > r.start).map((r) => ({ ...r })).sort((a, b) => a.start - b.start);
  const merged: { start: number; end: number }[] = [];
  for (const r of sorted) {
    const last = merged[merged.length - 1];
    if (last && r.start <= last.end) last.end = Math.max(last.end, r.end);
    else merged.push(r);
  }
  const out: Segment[] = [];
  let at = 0;
  merged.forEach((r, i) => {
    if (r.start > at) out.push({ text: text.slice(at, r.start), mark: false, first: false });
    out.push({ text: text.slice(r.start, r.end), mark: true, first: i === 0 });
    at = r.end;
  });
  if (at < text.length) out.push({ text: text.slice(at), mark: false, first: false });
  return out;
}
