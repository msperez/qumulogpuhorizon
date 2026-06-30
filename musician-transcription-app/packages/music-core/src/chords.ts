// Chord recognition from a chroma vector + chord symbol formatting.
//
// A "chroma" (a.k.a. pitch-class profile) is a 12-element vector giving the
// energy present at each pitch class C…B over some time window. The native DSP
// module produces these per beat; this pure function turns one into a named
// chord. Keeping it in TypeScript means we can unit-test the musical logic
// without any audio, and reuse the exact same code in the editor when a user
// asks "what chord are these notes?".

import type { ChordQuality, ChordSymbol, PitchClass } from './types.ts';
import { PITCH_CLASS_NAMES } from './types.ts';

/** Interval sets (semitones above the root) for each supported quality. */
const CHORD_INTERVALS: Record<ChordQuality, number[]> = {
  maj: [0, 4, 7],
  min: [0, 3, 7],
  dim: [0, 3, 6],
  aug: [0, 4, 8],
  maj7: [0, 4, 7, 11],
  min7: [0, 3, 7, 10],
  '7': [0, 4, 7, 10],
  dim7: [0, 3, 6, 9],
  m7b5: [0, 3, 6, 10],
  sus2: [0, 2, 7],
  sus4: [0, 5, 7],
  add9: [0, 4, 7, 14],
  '6': [0, 4, 7, 9],
  m6: [0, 3, 7, 9],
};

/** How chord qualities print after the root (root is added separately). */
const QUALITY_SUFFIX: Record<ChordQuality, string> = {
  maj: '',
  min: 'm',
  dim: 'dim',
  aug: 'aug',
  maj7: 'maj7',
  min7: 'm7',
  '7': '7',
  dim7: 'dim7',
  m7b5: 'm7b5',
  sus2: 'sus2',
  sus4: 'sus4',
  add9: 'add9',
  '6': '6',
  m6: 'm6',
};

const ALL_QUALITIES = Object.keys(CHORD_INTERVALS) as ChordQuality[];

/** Build a unit-normalized 12-bin binary template for root+quality. */
function template(root: number, quality: ChordQuality): number[] {
  const v = new Array(12).fill(0);
  for (const interval of CHORD_INTERVALS[quality]) {
    v[(root + interval) % 12] += 1;
  }
  return normalize(v);
}

function normalize(v: number[]): number[] {
  let mag = 0;
  for (const x of v) mag += x * x;
  mag = Math.sqrt(mag);
  if (mag === 0) return v.slice();
  return v.map((x) => x / mag);
}

function dot(a: number[], b: number[]): number {
  let s = 0;
  for (let i = 0; i < 12; i++) s += a[i] * b[i];
  return s;
}

// Precompute all 12 roots × every quality once at module load.
const TEMPLATES: { root: PitchClass; quality: ChordQuality; vec: number[] }[] =
  [];
for (let root = 0; root < 12; root++) {
  for (const quality of ALL_QUALITIES) {
    TEMPLATES.push({ root: root as PitchClass, quality, vec: template(root, quality) });
  }
}

export interface ChordMatch {
  root: PitchClass;
  quality: ChordQuality;
  /** Cosine similarity 0–1 of the chroma to this chord's template. */
  score: number;
}

/**
 * Recognize the most likely chord for a chroma vector via cosine similarity
 * against every root×quality template. Returns ranked matches, best first.
 *
 * Caveat: chroma carries no bass information, so chords that share a
 * pitch-class set are indistinguishable here — Eb6 vs Cm7, C6 vs Am7, and the
 * symmetric dim7 family. When two templates tie, the lower root wins by sort
 * order; a downstream bass-note detector is what ultimately disambiguates.
 *
 * @param chroma 12 non-negative energies, index 0 = C … 11 = B. Need not be
 *   normalized; this function normalizes internally.
 * @param topN how many ranked candidates to return (default 3).
 */
export function recognizeChord(chroma: number[], topN = 3): ChordMatch[] {
  if (chroma.length !== 12) {
    throw new Error(`chroma must have 12 bins, got ${chroma.length}`);
  }
  const c = normalize(chroma.map((x) => (x < 0 ? 0 : x)));
  const matches = TEMPLATES.map((t) => ({
    root: t.root,
    quality: t.quality,
    score: dot(c, t.vec),
  }));
  matches.sort((a, b) => b.score - a.score);
  return matches.slice(0, topN);
}

/** Render a chord symbol as text, e.g. {root:0,quality:'maj7'} -> "Cmaj7". */
export function formatChord(chord: Pick<ChordSymbol, 'root' | 'quality' | 'bass'>): string {
  const base = `${PITCH_CLASS_NAMES[chord.root]}${QUALITY_SUFFIX[chord.quality]}`;
  if (chord.bass !== undefined && chord.bass !== chord.root) {
    return `${base}/${PITCH_CLASS_NAMES[chord.bass]}`;
  }
  return base;
}

export { CHORD_INTERVALS };
