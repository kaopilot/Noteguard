// Offset conversion (Section 18.3; B3 owned test test_offset_conversion_utf16).
// Mutation spot-check: replace codePointToUtf16's loop with `return cp` -> the golden and emoji cases fail.
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { checkSpan, codePointToUtf16, segments } from '../src/lib/offsets';
import { sgtInputToUtc, toSgtInputSecondsCeil } from '../src/lib/time';

const ROOT = resolve(__dirname, '..', '..');
type Ev = { note_version_id: string | null; start: number; end: number; quote: string; role_in_flag: string };

function extractionTexts(): Map<string, string> {
  const out = new Map<string, string>();
  for (const f of readdirSync(resolve(ROOT, 'fixtures/encounters')).filter((n) => n.startsWith('ENC-'))) {
    const enc = JSON.parse(readFileSync(resolve(ROOT, 'fixtures/encounters', f), 'utf-8'));
    for (const e of enc.extractions) out.set(e.source_version_id, e.text);
  }
  return out;
}

function goldenEvidence(): Ev[] {
  const out: Ev[] = [];
  const walk = (x: unknown) => {
    if (Array.isArray(x)) x.forEach(walk);
    else if (x && typeof x === 'object') {
      const o = x as Record<string, unknown>;
      if ('quote_sha256' in o && 'role_in_flag' in o) out.push(o as unknown as Ev);
      Object.values(o).forEach(walk);
    }
  };
  for (const f of readdirSync(resolve(ROOT, 'fixtures/expected')).filter((n) => n.endsWith('.json'))) {
    walk(JSON.parse(readFileSync(resolve(ROOT, 'fixtures/expected', f), 'utf-8')));
  }
  return out;
}

test('every golden evidence span converts to UTF-16 and matches its quote', () => {
  const texts = extractionTexts();
  const spans = goldenEvidence().filter((e) => e.note_version_id !== null && e.quote !== '');
  expect(spans.length).toBeGreaterThan(20);
  const bad = spans.filter((e) => !checkSpan(texts.get(e.note_version_id ?? '') ?? '', e.start, e.end, e.quote).ok);
  expect(bad).toEqual([]);
});

test('the 16:00 social-work span sits after an astral emoji: naive slicing is wrong, conversion is right', () => {
  const texts = extractionTexts();
  const sw = goldenEvidence().find((e) => e.quote === 'Patient stable' && (texts.get(e.note_version_id ?? '') ?? '').includes('\u{1F642}'));
  expect(sw).toBeDefined();
  const text = texts.get(sw?.note_version_id ?? '') ?? '';
  expect(text).toMatch(/[\u4e00-\u9fff]/);
  expect(text).toContain('\u030d');
  const s = sw as Ev;
  expect(text.slice(s.start, s.end)).not.toBe(s.quote);
  const c = checkSpan(text, s.start, s.end, s.quote);
  expect(c).toEqual({ ok: true, start: s.start + 1, end: s.end + 1, text: 'Patient stable' });
});

test('a mismatching or out-of-range span is refused and never highlighted', () => {
  const text = 'A\u{1F642}B combining a\u0301 end';
  expect(codePointToUtf16(text, 2)).toBe(3);
  expect(checkSpan(text, 2, 3, 'B')).toMatchObject({ ok: true });
  expect(checkSpan(text, 1, 3, 'B')).toEqual({ ok: false, reason: 'quote_mismatch' });
  expect(checkSpan(text, 0, 999, text)).toEqual({ ok: false, reason: 'out_of_range' });
  expect(checkSpan(text, 5, 2, '')).toEqual({ ok: false, reason: 'out_of_range' });
  expect(segments('abcdef', [{ start: 1, end: 3 }, { start: 2, end: 4 }]).filter((s) => s.mark).map((s) => s.text)).toEqual(['bcd']);
});

test('cutoff times: rounded up to the second, parsed with or without seconds, in Singapore time', () => {
  expect(toSgtInputSecondsCeil('2026-09-23T08:33:40.938Z')).toBe('2026-09-23T16:33:41');
  expect(toSgtInputSecondsCeil('2026-09-21T08:00:00Z')).toBe('2026-09-21T16:00:00');
  expect(toSgtInputSecondsCeil('2026-09-21T15:59:59.500Z')).toBe('2026-09-22T00:00:00');
  expect(sgtInputToUtc('2026-09-21T16:00')).toBe('2026-09-21T08:00:00Z');
  expect(sgtInputToUtc('2026-09-23T16:33:41')).toBe('2026-09-23T08:33:41Z');
  expect(sgtInputToUtc('2026-09-23T16:33:41.000')).toBe('2026-09-23T08:33:41Z');
  expect(sgtInputToUtc('21/09/2026 16:00')).toBeNull();
});
