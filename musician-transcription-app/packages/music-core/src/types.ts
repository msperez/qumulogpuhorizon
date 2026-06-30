// Core domain model for Scorewright.
//
// These types are the single source of truth shared by the React Native app,
// the editor, the export code, and (eventually) the native DSP bridge.
//
// Music time is expressed in *beats* (quarter-note beats) so the model is
// independent of tempo. Wall-clock seconds only appear in the raw analysis
// coming off the audio; everything downstream works in musical time.

/** The 12 pitch classes, C = 0 … B = 11. */
export type PitchClass = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11;

/** A MIDI note number, 0–127. Middle C (C4) = 60. */
export type MidiNumber = number;

export interface TimeSignature {
  /** Beats per bar, e.g. 4 in 4/4, 3 in 3/4, 6 in 6/8. */
  numerator: number;
  /** Note value that gets the beat, e.g. 4 = quarter, 8 = eighth. */
  denominator: number;
}

/** One detected/edited melodic note, positioned in musical time. */
export interface Note {
  pitch: MidiNumber;
  /** Onset, in quarter-note beats from the start of the piece. */
  startBeat: number;
  /** Length in quarter-note beats. */
  durationBeats: number;
  /** 0–1 loudness if known. */
  velocity?: number;
  /** 0–1 detector confidence; low values are flagged for review. */
  confidence?: number;
}

export type ChordQuality =
  | 'maj'
  | 'min'
  | 'dim'
  | 'aug'
  | 'maj7'
  | 'min7'
  | '7'
  | 'dim7'
  | 'm7b5'
  | 'sus2'
  | 'sus4'
  | 'add9'
  | '6'
  | 'm6';

/** A chord symbol sitting above the staff (e.g. C, Am7, G/B). */
export interface ChordSymbol {
  root: PitchClass;
  quality: ChordQuality;
  /** Optional slash bass note (pitch class), e.g. the B in G/B. */
  bass?: PitchClass;
  startBeat: number;
  durationBeats: number;
  confidence?: number;
}

/** A measure. Time signature can change per bar. */
export interface Bar {
  index: number;
  startBeat: number;
  timeSignature: TimeSignature;
  notes: Note[];
  chords: ChordSymbol[];
}

export interface Score {
  /** Pitch class of the estimated key tonic, if known. */
  keyRoot?: PitchClass;
  keyIsMinor?: boolean;
  tempoBpm: number;
  timeSignature: TimeSignature;
  bars: Bar[];
}

export interface Project {
  id: string;
  title: string;
  tags: string[];
  createdAt: string;
  /** Path/uri to the retained source audio; the model is never destructive. */
  audioRef?: string;
  score: Score;
}

/** Names for the 12 pitch classes using sharps. */
export const PITCH_CLASS_NAMES = [
  'C',
  'C#',
  'D',
  'D#',
  'E',
  'F',
  'F#',
  'G',
  'G#',
  'A',
  'A#',
  'B',
] as const;

export function pitchClassOf(midi: MidiNumber): PitchClass {
  return (((midi % 12) + 12) % 12) as PitchClass;
}

export function noteName(midi: MidiNumber): string {
  const octave = Math.floor(midi / 12) - 1;
  return `${PITCH_CLASS_NAMES[pitchClassOf(midi)]}${octave}`;
}
