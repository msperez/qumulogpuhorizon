import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recognizeChord, formatChord, CHORD_INTERVALS } from './chords.ts';
import type { ChordQuality, PitchClass } from './types.ts';

/** Build a clean chroma for a chord by summing its template pitch classes. */
function chromaFor(root: number, quality: ChordQuality): number[] {
  const v = new Array(12).fill(0);
  for (const interval of CHORD_INTERVALS[quality]) v[(root + interval) % 12] += 1;
  return v;
}

test('recognizes a clean C major triad', () => {
  const [best] = recognizeChord(chromaFor(0, 'maj'));
  assert.equal(best.root, 0);
  assert.equal(best.quality, 'maj');
  assert.ok(best.score > 0.99);
});

test('distinguishes major from minor', () => {
  const [cmaj] = recognizeChord(chromaFor(0, 'maj'));
  const [amin] = recognizeChord(chromaFor(9, 'min'));
  assert.equal(formatChord(cmaj), 'C');
  assert.equal(formatChord(amin), 'Am');
});

test('recognizes a dominant seventh', () => {
  const [best] = recognizeChord(chromaFor(7, '7')); // G7
  assert.equal(formatChord(best), 'G7');
});

/** The set of sounding pitch classes for a chord, as a sorted string key. */
function pcSet(root: number, quality: ChordQuality): string {
  return [...new Set(CHORD_INTERVALS[quality].map((i) => (root + i) % 12))]
    .sort((a, b) => a - b)
    .join(',');
}

test('every template round-trips to a chord with the same notes', () => {
  // Note: chroma alone cannot distinguish chords that share a pitch-class set
  // (e.g. Eb6 == Cm7, C6 == Am7, and dim7 is symmetric). The bass note is the
  // real disambiguator and is supplied by a later stage. So we assert the
  // recognized chord sounds the *same notes*, not the same spelling.
  const qualities = Object.keys(CHORD_INTERVALS) as ChordQuality[];
  for (let root = 0; root < 12; root++) {
    for (const quality of qualities) {
      const [best] = recognizeChord(chromaFor(root, quality));
      assert.equal(
        pcSet(best.root, best.quality),
        pcSet(root, quality),
        `notes for ${root}/${quality} -> got ${best.root}/${best.quality}`,
      );
    }
  }
});

test('is robust to a noisy chroma (extra energy on a non-chord tone)', () => {
  const chroma = chromaFor(0, 'maj'); // C E G
  chroma[1] += 0.3; // a bit of C# bleed
  const [best] = recognizeChord(chroma);
  assert.equal(formatChord(best), 'C');
});

test('formats a slash chord', () => {
  assert.equal(
    formatChord({ root: 7 as PitchClass, quality: 'maj', bass: 11 as PitchClass }),
    'G/B',
  );
});

test('rejects malformed chroma length', () => {
  assert.throws(() => recognizeChord([1, 2, 3]));
});
