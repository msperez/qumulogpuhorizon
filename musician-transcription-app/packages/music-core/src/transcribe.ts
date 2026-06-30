// Assembly: fold raw analysis (from the native DSP module) into a Score.
//
// This is step 5 of the pipeline described in the product design doc. The
// native side does the signal processing and hands us a plain JSON `Analysis`;
// everything from here on is the pure, testable, cross-platform logic in this
// package. Keeping the seam here means the DSP can be a Swift module, a Rust
// core, or a cloud service without the app code knowing the difference.

import { recognizeChord } from './chords.ts';
import { buildBars, beatsPerBar, quantizeNotes, secondsToBeats } from './quantize.ts';
import type { RawNote } from './quantize.ts';
import type { ChordSymbol, Score, TimeSignature } from './types.ts';

/** The structured result the native analyzer produces from one recording. */
export interface Analysis {
  tempoBpm: number;
  timeSignature: TimeSignature;
  /** Detected melodic notes, timed in seconds. */
  notes: RawNote[];
  /**
   * Per-beat chroma vectors (12 bins each), starting at beat 0. One entry per
   * quarter-note beat is typical; chords are summarized per bar from these.
   */
  beatChroma: number[][];
  keyRoot?: number;
  keyIsMinor?: boolean;
}

export interface TranscribeOptions {
  /** Grid for note quantization, in quarter-note beats (default sixteenth). */
  grid?: number;
  /** Below this cosine score a chord is dropped rather than guessed. */
  minChordConfidence?: number;
}

/**
 * Summarize per-beat chroma into one chord per bar by averaging the chroma
 * across each bar's beats, then recognizing the dominant chord. Returns one
 * {@link ChordSymbol} per bar that clears the confidence threshold.
 */
function chordsFromChroma(
  beatChroma: number[][],
  timeSignature: TimeSignature,
  minConfidence: number,
): ChordSymbol[] {
  const perBar = beatsPerBar(timeSignature);
  const chords: ChordSymbol[] = [];
  const totalBeats = beatChroma.length;
  const barCount = Math.ceil(totalBeats / perBar);

  for (let bar = 0; bar < barCount; bar++) {
    const startBeat = bar * perBar;
    const endBeat = Math.min(totalBeats, startBeat + perBar);
    const avg = new Array(12).fill(0);
    let count = 0;
    for (let beat = Math.floor(startBeat); beat < endBeat; beat++) {
      const c = beatChroma[beat];
      if (!c) continue;
      for (let i = 0; i < 12; i++) avg[i] += c[i] ?? 0;
      count++;
    }
    if (count === 0) continue;
    for (let i = 0; i < 12; i++) avg[i] /= count;

    const [best] = recognizeChord(avg, 1);
    if (!best || best.score < minConfidence) continue;
    chords.push({
      root: best.root,
      quality: best.quality,
      startBeat,
      durationBeats: endBeat - startBeat,
      confidence: best.score,
    });
  }
  return chords;
}

/** Build a complete {@link Score} from a native {@link Analysis}. */
export function transcribeToScore(
  analysis: Analysis,
  opts: TranscribeOptions = {},
): Score {
  const grid = opts.grid ?? 0.25;
  const minChordConfidence = opts.minChordConfidence ?? 0.6;

  const notes = quantizeNotes(analysis.notes, {
    tempoBpm: analysis.tempoBpm,
    timeSignature: analysis.timeSignature,
    grid,
  });
  const chords = chordsFromChroma(
    analysis.beatChroma,
    analysis.timeSignature,
    minChordConfidence,
  );
  const bars = buildBars(notes, chords, analysis.timeSignature);

  const score: Score = {
    tempoBpm: analysis.tempoBpm,
    timeSignature: analysis.timeSignature,
    bars,
  };
  if (analysis.keyRoot !== undefined) score.keyRoot = analysis.keyRoot as Score['keyRoot'];
  if (analysis.keyIsMinor !== undefined) score.keyIsMinor = analysis.keyIsMinor;
  return score;
}

// Re-exported for convenience in callers assembling analyses by hand/tests.
export { secondsToBeats };
