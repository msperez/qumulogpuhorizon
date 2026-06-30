# @scorewright/music-core

Pure-TypeScript music logic for Scorewright. No platform dependencies, so the
exact same code runs in the React Native app, in Node, and in tests. This is the
**cross-platform half of the transcription pipeline** — everything *after* the
native DSP module turns audio into a structured `Analysis`.

## What's here

| Module | Responsibility |
|--------|----------------|
| `types.ts` | Domain model: `Project`, `Score`, `Bar`, `Note`, `ChordSymbol`, pitch helpers |
| `chords.ts` | Chord recognition from a 12-bin chroma vector (cosine vs. templates) + chord-symbol formatting |
| `quantize.ts` | Seconds→beats, snap-to-grid, group notes/chords into bars |
| `transcribe.ts` | Assemble a native `Analysis` into a finished `Score` |
| `midi.ts` | Export a `Score` to a Standard MIDI File (format 0) |

## The seam

```
 native DSP (Swift/Kotlin)            this package (TypeScript)
 ───────────────────────────         ────────────────────────────────────
 mic → pitch + chroma + beats   ─►    Analysis ─► transcribeToScore ─► Score
                                                   │
                                                   ├─► editor (RN UI)
                                                   └─► scoreToMidi ─► .mid
```

The native side is swappable (Swift module, Rust core, or a cloud service) — it
only has to produce an `Analysis`. Everything downstream is here and testable
without any audio.

## Run it

```bash
# Unit tests (Node's built-in runner + native TS type-stripping)
npm test

# Typecheck / build to dist/
npm run build

# End-to-end demo: prints a chart and writes examples/demo-output.mid
node --experimental-strip-types examples/demo.ts
```

## Known limitation (by design)

Chroma carries no bass information, so chords sharing a pitch-class set are
indistinguishable here — `Eb6` vs `Cm7`, `C6` vs `Am7`, and the symmetric
`dim7` family. The bass note is the real disambiguator and comes from a later
detection stage. The recognizer documents this and the tests assert
*same-notes* equivalence rather than exact spelling.

## Next

- Bass-note detection to disambiguate inversions/slash chords.
- MusicXML export (notation-app interop) alongside MIDI.
- Wire to the native DSP module that produces real `Analysis` from audio.
