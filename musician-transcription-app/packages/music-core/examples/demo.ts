// End-to-end demo of the music-core pipeline, runnable with:
//
//   node --experimental-strip-types examples/demo.ts
//
// It fabricates the kind of `Analysis` the native DSP module will eventually
// hand us (a I–V–vi–IV progression in C with a simple melody), assembles a
// Score, prints the chart, and writes a real .mid file you can open in a DAW.

import { writeFileSync } from 'node:fs';
import { transcribeToScore } from '../src/transcribe.ts';
import type { Analysis } from '../src/transcribe.ts';
import { scoreToMidi } from '../src/midi.ts';
import { formatChord } from '../src/chords.ts';
import { noteName } from '../src/types.ts';
import type { ChordQuality } from '../src/types.ts';
import { CHORD_INTERVALS } from '../src/chords.ts';

function chroma(root: number, quality: ChordQuality): number[] {
  const v = new Array(12).fill(0);
  for (const i of CHORD_INTERVALS[quality]) v[(root + i) % 12] += 1;
  return v;
}

// I–V–vi–IV in C major: C, G, Am, F — one chord per 4/4 bar at 100 BPM.
const progression: [number, ChordQuality][] = [
  [0, 'maj'], // C
  [7, 'maj'], // G
  [9, 'min'], // Am
  [5, 'maj'], // F
];

const beatChroma: number[][] = [];
for (const [root, quality] of progression) {
  for (let beat = 0; beat < 4; beat++) beatChroma.push(chroma(root, quality));
}

// A melody that walks the top of each chord, one note per beat at 100 BPM
// (a beat = 0.6s).
const melodyPitches = [72, 74, 76, 74, 79, 78, 76, 74, 81, 79, 76, 72, 77, 76, 74, 72];
const secPerBeat = 60 / 100;
const notes = melodyPitches.map((pitch, i) => ({
  pitch,
  startSec: i * secPerBeat,
  endSec: (i + 1) * secPerBeat,
}));

const analysis: Analysis = {
  tempoBpm: 100,
  timeSignature: { numerator: 4, denominator: 4 },
  notes,
  beatChroma,
  keyRoot: 0,
  keyIsMinor: false,
};

const score = transcribeToScore(analysis);

console.log('Scorewright — transcription demo');
console.log(`Tempo: ${score.tempoBpm} BPM   Time: 4/4   Key: C major\n`);
for (const bar of score.bars) {
  const chord = bar.chords[0] ? formatChord(bar.chords[0]) : '—';
  const conf = bar.chords[0]?.confidence?.toFixed(2) ?? '—';
  const melody = bar.notes.map((n) => noteName(n.pitch)).join(' ');
  console.log(
    `Bar ${String(bar.index + 1).padStart(2)} | ${chord.padEnd(6)} (conf ${conf}) | ${melody}`,
  );
}

const midi = scoreToMidi(score);
const outPath = new URL('./demo-output.mid', import.meta.url).pathname;
writeFileSync(outPath, midi);
console.log(`\nWrote ${midi.length}-byte MIDI file -> ${outPath}`);
