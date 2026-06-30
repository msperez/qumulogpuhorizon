import { test } from 'node:test';
import assert from 'node:assert/strict';
import { transcribeToScore } from './transcribe.ts';
import type { Analysis } from './transcribe.ts';
import { scoreToMidi } from './midi.ts';
import { formatChord, CHORD_INTERVALS } from './chords.ts';
import type { ChordQuality } from './types.ts';

function chromaFor(root: number, quality: ChordQuality): number[] {
  const v = new Array(12).fill(0);
  for (const interval of CHORD_INTERVALS[quality]) v[(root + interval) % 12] += 1;
  return v;
}

/** A two-bar 4/4 analysis at 120 BPM: C major bar, then G7 bar. */
function sampleAnalysis(): Analysis {
  const cmaj = chromaFor(0, 'maj');
  const g7 = chromaFor(7, '7');
  return {
    tempoBpm: 120,
    timeSignature: { numerator: 4, denominator: 4 },
    notes: [
      { pitch: 60, startSec: 0, endSec: 0.5 }, // C4 beat 0
      { pitch: 64, startSec: 0.5, endSec: 1.0 }, // E4 beat 1
      { pitch: 67, startSec: 1.0, endSec: 1.5 }, // G4 beat 2
      { pitch: 71, startSec: 2.0, endSec: 2.5 }, // B4 beat 4 (bar 1)
    ],
    // 8 beats of chroma: first 4 = C major, next 4 = G7.
    beatChroma: [cmaj, cmaj, cmaj, cmaj, g7, g7, g7, g7],
  };
}

test('assembles an analysis into a two-bar score with the right chords', () => {
  const score = transcribeToScore(sampleAnalysis());
  assert.equal(score.bars.length, 2);

  const bar0Chord = score.bars[0].chords[0];
  const bar1Chord = score.bars[1].chords[0];
  assert.equal(formatChord(bar0Chord), 'C');
  assert.equal(formatChord(bar1Chord), 'G7');
  assert.ok((bar0Chord.confidence ?? 0) > 0.6);
});

test('places melody notes into the correct bars', () => {
  const score = transcribeToScore(sampleAnalysis());
  assert.equal(score.bars[0].notes.length, 3); // C E G
  assert.equal(score.bars[1].notes.length, 1); // B
  assert.equal(score.bars[1].notes[0].pitch, 71);
});

test('drops chords below the confidence threshold', () => {
  const analysis = sampleAnalysis();
  // Flat chroma -> no chord should clear the default 0.6 threshold.
  analysis.beatChroma = analysis.beatChroma.map(() => new Array(12).fill(1));
  const score = transcribeToScore(analysis);
  const totalChords = score.bars.reduce((sum, b) => sum + b.chords.length, 0);
  assert.equal(totalChords, 0);
});

test('exports a valid SMF header and is non-trivial in size', () => {
  const score = transcribeToScore(sampleAnalysis());
  const midi = scoreToMidi(score);
  // "MThd" magic.
  assert.deepEqual([...midi.slice(0, 4)], [0x4d, 0x54, 0x68, 0x64]);
  // "MTrk" magic at offset 14 (header is 14 bytes).
  assert.deepEqual([...midi.slice(14, 18)], [0x4d, 0x54, 0x72, 0x6b]);
  // Has a tempo meta event (0xff 0x51).
  let hasTempo = false;
  for (let i = 0; i < midi.length - 1; i++) {
    if (midi[i] === 0xff && midi[i + 1] === 0x51) hasTempo = true;
  }
  assert.ok(hasTempo);
  assert.ok(midi.length > 40);
});
