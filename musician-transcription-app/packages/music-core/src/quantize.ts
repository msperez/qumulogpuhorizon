// Quantization: turn raw detected notes (timed in seconds) into musical time
// (beats), snap them to a grid, and group everything into bars.
//
// This is the bridge between what the audio analysis produces (onsets in
// seconds) and what the editor shows (notes in bars). Every value here is
// derived but user-overridable in the UI.

import type { Bar, ChordSymbol, Note, TimeSignature } from './types.ts';

/** A note as it comes off the detector: timing in seconds, pitch as MIDI. */
export interface RawNote {
  pitch: number;
  startSec: number;
  endSec: number;
  velocity?: number;
  confidence?: number;
}

export interface QuantizeOptions {
  tempoBpm: number;
  timeSignature: TimeSignature;
  /**
   * Grid resolution as a fraction of a quarter-note beat to snap to.
   * 0.25 = sixteenth-note grid (default), 0.5 = eighth, 1 = quarter.
   */
  grid?: number;
  /** Minimum kept duration in beats; shorter notes are clamped up. */
  minDurationBeats?: number;
}

export function secondsToBeats(seconds: number, tempoBpm: number): number {
  return (seconds * tempoBpm) / 60;
}

export function beatsToSeconds(beats: number, tempoBpm: number): number {
  return (beats * 60) / tempoBpm;
}

function snap(value: number, grid: number): number {
  return Math.round(value / grid) * grid;
}

/**
 * Convert raw detected notes into beat-quantized {@link Note}s. Onsets and
 * durations are snapped to the grid; zero-length results are bumped to the
 * grid size so nothing disappears.
 */
export function quantizeNotes(
  raw: RawNote[],
  opts: QuantizeOptions,
): Note[] {
  const grid = opts.grid ?? 0.25;
  const minDur = opts.minDurationBeats ?? grid;
  return raw
    .map((r) => {
      const startBeat = snap(secondsToBeats(r.startSec, opts.tempoBpm), grid);
      const rawDur = secondsToBeats(r.endSec - r.startSec, opts.tempoBpm);
      const durationBeats = Math.max(minDur, snap(rawDur, grid));
      const note: Note = {
        pitch: r.pitch,
        startBeat,
        durationBeats,
      };
      if (r.velocity !== undefined) note.velocity = r.velocity;
      if (r.confidence !== undefined) note.confidence = r.confidence;
      return note;
    })
    .sort((a, b) => a.startBeat - b.startBeat || a.pitch - b.pitch);
}

/** Beats per bar for a time signature (in quarter-note beats). */
export function beatsPerBar(ts: TimeSignature): number {
  return ts.numerator * (4 / ts.denominator);
}

/**
 * Group quantized notes and chords into bars based on a (single) time
 * signature. A note/chord is placed in the bar its onset falls into. Enough
 * bars are created to cover the latest event, even if some are empty.
 */
export function buildBars(
  notes: Note[],
  chords: ChordSymbol[],
  timeSignature: TimeSignature,
): Bar[] {
  const perBar = beatsPerBar(timeSignature);
  let lastBeat = 0;
  for (const n of notes) lastBeat = Math.max(lastBeat, n.startBeat + n.durationBeats);
  for (const c of chords) lastBeat = Math.max(lastBeat, c.startBeat + c.durationBeats);

  const barCount = Math.max(1, Math.ceil(lastBeat / perBar));
  const bars: Bar[] = [];
  for (let i = 0; i < barCount; i++) {
    bars.push({
      index: i,
      startBeat: i * perBar,
      timeSignature,
      notes: [],
      chords: [],
    });
  }

  const barOf = (beat: number) =>
    Math.min(barCount - 1, Math.max(0, Math.floor(beat / perBar)));

  for (const n of notes) bars[barOf(n.startBeat)].notes.push(n);
  for (const c of chords) bars[barOf(c.startBeat)].chords.push(c);
  return bars;
}
