// Standard MIDI File (SMF, format 0) export.
//
// Turns a Score's notes into a single-track .mid file that opens in any DAW or
// notation app. This is the "nothing is ever lost" guarantee in practice: even
// a rough transcription can be carried into the user's real tools.
//
// We emit musical time using ticks-per-quarter-note timing, so the file is
// tempo-correct without depending on the seconds the audio happened to take.

import type { Note, Score } from './types.ts';

const TICKS_PER_QUARTER = 480;

function writeVarLen(value: number): number[] {
  // MIDI variable-length quantity, big-endian 7-bit groups.
  let buffer = value & 0x7f;
  const bytes: number[] = [];
  while ((value >>= 7) > 0) {
    buffer <<= 8;
    buffer |= (value & 0x7f) | 0x80;
  }
  // emit
  // eslint-disable-next-line no-constant-condition
  while (true) {
    bytes.push(buffer & 0xff);
    if (buffer & 0x80) buffer >>= 8;
    else break;
  }
  return bytes;
}

function u32(value: number): number[] {
  return [(value >> 24) & 0xff, (value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff];
}

function u16(value: number): number[] {
  return [(value >> 8) & 0xff, value & 0xff];
}

interface MidiEvent {
  tick: number;
  /** Lower order = fired first when ticks tie (note-off before note-on). */
  order: number;
  data: number[];
}

/**
 * Serialize a {@link Score} to the bytes of a format-0 .mid file.
 * Returns a Uint8Array suitable for writing to disk or sharing.
 */
export function scoreToMidi(score: Score, velocityDefault = 80): Uint8Array {
  const events: MidiEvent[] = [];
  const allNotes: Note[] = [];
  for (const bar of score.bars) allNotes.push(...bar.notes);

  for (const n of allNotes) {
    const startTick = Math.round(n.startBeat * TICKS_PER_QUARTER);
    const endTick = Math.round((n.startBeat + n.durationBeats) * TICKS_PER_QUARTER);
    const velocity = Math.max(
      1,
      Math.min(127, Math.round((n.velocity ?? velocityDefault / 127) * 127)),
    );
    const pitch = Math.max(0, Math.min(127, Math.round(n.pitch)));
    events.push({ tick: startTick, order: 1, data: [0x90, pitch, velocity] });
    events.push({ tick: endTick, order: 0, data: [0x80, pitch, 0] });
  }

  events.sort((a, b) => a.tick - b.tick || a.order - b.order);

  // Build the track: tempo meta, time-signature meta, then notes, then end.
  const track: number[] = [];
  const usPerQuarter = Math.round(60_000_000 / score.tempoBpm);
  track.push(
    ...writeVarLen(0),
    0xff,
    0x51,
    0x03,
    (usPerQuarter >> 16) & 0xff,
    (usPerQuarter >> 8) & 0xff,
    usPerQuarter & 0xff,
  );
  // Time signature meta: numerator, denominator as power of two, clocks, 32nds.
  const denomPow = Math.round(Math.log2(score.timeSignature.denominator));
  track.push(
    ...writeVarLen(0),
    0xff,
    0x58,
    0x04,
    score.timeSignature.numerator,
    denomPow,
    24,
    8,
  );

  let prevTick = 0;
  for (const ev of events) {
    const delta = ev.tick - prevTick;
    prevTick = ev.tick;
    track.push(...writeVarLen(delta), ...ev.data);
  }
  // End of track.
  track.push(...writeVarLen(0), 0xff, 0x2f, 0x00);

  const header = [
    0x4d, 0x54, 0x68, 0x64, // "MThd"
    ...u32(6),
    ...u16(0), // format 0
    ...u16(1), // one track
    ...u16(TICKS_PER_QUARTER),
  ];
  const trackChunk = [
    0x4d, 0x54, 0x72, 0x6b, // "MTrk"
    ...u32(track.length),
    ...track,
  ];
  return Uint8Array.from([...header, ...trackChunk]);
}

export { TICKS_PER_QUARTER };
