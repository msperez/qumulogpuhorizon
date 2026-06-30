import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  quantizeNotes,
  buildBars,
  beatsPerBar,
  secondsToBeats,
} from './quantize.ts';
import type { RawNote } from './quantize.ts';
import type { ChordSymbol } from './types.ts';

const FOUR_FOUR = { numerator: 4, denominator: 4 };

test('seconds convert to beats at tempo', () => {
  // At 120 BPM a beat is 0.5s, so 1s = 2 beats.
  assert.equal(secondsToBeats(1, 120), 2);
});

test('beatsPerBar handles 4/4, 3/4 and 6/8', () => {
  assert.equal(beatsPerBar({ numerator: 4, denominator: 4 }), 4);
  assert.equal(beatsPerBar({ numerator: 3, denominator: 4 }), 3);
  assert.equal(beatsPerBar({ numerator: 6, denominator: 8 }), 3);
});

test('quantizes slightly-off onsets to the grid', () => {
  // 120 BPM, quarter = 0.5s. A note at 0.26s ~ beat 0.52 -> snaps to 0.5.
  const raw: RawNote[] = [{ pitch: 60, startSec: 0.26, endSec: 0.74 }];
  const [n] = quantizeNotes(raw, { tempoBpm: 120, timeSignature: FOUR_FOUR });
  assert.equal(n.startBeat, 0.5);
  assert.equal(n.durationBeats, 1); // ~0.48s ~ 0.96 beats -> snaps to 1
});

test('never drops a note to zero duration', () => {
  const raw: RawNote[] = [{ pitch: 64, startSec: 0, endSec: 0.001 }];
  const [n] = quantizeNotes(raw, { tempoBpm: 120, timeSignature: FOUR_FOUR });
  assert.ok(n.durationBeats >= 0.25);
});

test('notes sort by onset then pitch', () => {
  const raw: RawNote[] = [
    { pitch: 67, startSec: 1, endSec: 1.5 },
    { pitch: 60, startSec: 0, endSec: 0.5 },
    { pitch: 64, startSec: 0, endSec: 0.5 },
  ];
  const notes = quantizeNotes(raw, { tempoBpm: 120, timeSignature: FOUR_FOUR });
  assert.deepEqual(
    notes.map((n) => n.pitch),
    [60, 64, 67],
  );
});

test('buildBars places events in the right measure and pads empties', () => {
  // 4/4: bar 0 = beats 0-4, bar 1 = 4-8.
  const notes = quantizeNotes(
    [
      { pitch: 60, startSec: 0, endSec: 0.5 }, // beat 0 -> bar 0
      { pitch: 72, startSec: 2.5, endSec: 3 }, // 120bpm -> beat 5 -> bar 1
    ],
    { tempoBpm: 120, timeSignature: FOUR_FOUR },
  );
  const chords: ChordSymbol[] = [
    { root: 0, quality: 'maj', startBeat: 0, durationBeats: 4 },
  ];
  const bars = buildBars(notes, chords, FOUR_FOUR);
  assert.equal(bars.length, 2);
  assert.equal(bars[0].notes.length, 1);
  assert.equal(bars[0].chords.length, 1);
  assert.equal(bars[1].notes.length, 1);
  assert.equal(bars[1].notes[0].pitch, 72);
});

test('buildBars always yields at least one bar', () => {
  const bars = buildBars([], [], FOUR_FOUR);
  assert.equal(bars.length, 1);
});
