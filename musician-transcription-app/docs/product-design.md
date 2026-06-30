# Scorewright — Product Design Document

> Working title. A mobile app for musicians to capture a live performance and
> turn it into a readable chart: melody notes, bars, and chord progressions.

**Status:** Draft v0.1 (product design — pre-code)
**Date:** 2026-06-30
**Platforms:** iOS + Android
**Stack decision:** React Native (TypeScript) UI + native audio/DSP modules (Swift / Kotlin)

---

## 1. The one-sentence pitch

Hit record, play a song, and get back an editable chart — melody note-by-note,
organized into bars, with chord names recognized automatically — so you never
lose an idea and can clean it up later.

## 2. Who it's for

| Persona | Need | Why this app |
|---------|------|--------------|
| **The writer at the piano** (primary) | Caught a progression at 1am, wants it saved as a chart before it's gone | One tap to capture, auto-transcribed, edit in the morning |
| **The gigging/cover musician** | Wants to figure out a song's chords and melody by ear, faster | Record a reference, get a first-pass chart to correct |
| **The student/teacher** | Wants to notate exercises and share them | Clean charts, export to PDF/MIDI/MusicXML |
| **The arranger** | Sketching ideas across sessions | A library of captures, named and tagged |

**Primary instrument for v1: Piano / keys.** Design the notation, ranges, and
detection tuning around keyboard first; keep the data model instrument-agnostic
so guitar/vocals can follow.

## 3. Scope decisions (locked for v1)

These were the big forks. Decisions:

- **Transcription scope:** *Melody + chords.* Detect the lead/most-prominent
  melodic line note-by-note, **and** recognize chord names (e.g. `Cmaj7`, `G7`,
  `Am`). We do **not** attempt full polyphonic multi-voice separation in v1 —
  that's research-grade and would tank accuracy.
- **Capture mode:** *Record-then-transcribe for v1.* A live real-time mode is a
  later phase (see §10). Record-then-process is more accurate, simpler, and lets
  the user edit before committing.
- **Editing is first-class.** Auto-transcription is a *first draft*, never
  assumed correct. The edit surface is as important as the capture.

### Explicit non-goals for v1
- No full orchestral/band separation (each instrument on its own staff).
- No real-time live transcription (phase 2).
- No social feed / marketplace.
- No desktop app (mobile-first; export covers the "open on a computer" need).

## 4. Core concepts / domain model

The vocabulary the user works in maps directly to our data model.

```
Project (a captured song / idea)
├── metadata: title, key, tempo (BPM), time signature, tags, createdAt
├── Recording (the source audio + analysis)
│   ├── audioRef (file)
│   └── analysis: detected tempo, beat grid, key estimate, confidences
└── Score
    └── Bars[]  (a "measure" — defined by time signature)
        ├── index, timeSignature (can change mid-piece)
        └── Beats / positions
            ├── Note  { pitch, octave, startBeat, durationBeats, velocity?, confidence }
            └── ChordSymbol { root, quality, bass?, startBeat, confidence }
```

Key ideas the user explicitly asked for, and where they live:

- **"Define my bars"** → `Bar` objects, derived from the detected beat grid +
  time signature, but fully user-editable (split, merge, set time signature).
- **"Define my notes"** → `Note` objects on a piano-roll / staff grid; add,
  delete, drag pitch, drag duration, nudge timing.
- **"Define my chords"** → `ChordSymbol` objects above the staff; auto-suggested
  with confidence, tap to confirm or swap from a picker.
- **"Note-by-note progressions and charts"** → the `Score` rendered two ways:
  a **piano-roll** (for editing timing/pitch precisely) and a **lead-sheet /
  chart** view (chords over a staff or chord-grid, for reading and sharing).

## 5. The core user flow

```
[ Home / Library ]
        │  tap “＋ Capture”
        ▼
[ Capture ] ── count-in / metronome (optional) ── tap Record
        │      live input-level meter, elapsed time
        │  tap Stop
        ▼
[ Analyzing… ]  (on-device; progress + “this takes a few seconds”)
        │
        ▼
[ Review & Edit ]  ← the heart of the app
        │   • Chart view (chords + melody, by bar)
        │   • Piano-roll view (precise note editing)
        │   • Transport: play original audio synced to the transcription
        │   • Per-element confidence highlighting (low-confidence = needs a look)
        │
        ├── edit bars / notes / chords
        ├── set key, tempo, time signature
        ▼
[ Save to Library ]
        │
        ▼
[ Export ]  → PDF (lead sheet) · MusicXML · MIDI · share link
```

## 6. Key screens

1. **Library / Home** — grid or list of projects; search, tags, sort by date.
   Each card: title, key, tempo, tiny chart thumbnail, duration.
2. **Capture** — big record button, input meter, optional metronome + count-in,
   pre-set time signature & tempo (or "detect automatically").
3. **Analyzing** — friendly progress; cancelable.
4. **Review & Edit** (two tabs):
   - **Chart tab:** bars laid out left-to-right, chord symbols above, melody on a
     staff (or simplified note row). Tap any chord/note to edit. Playback head
     scrubs across as audio plays.
   - **Piano-roll tab:** horizontal time, vertical pitch; drag to move/resize
     notes; pinch to zoom; snap-to-grid toggle.
5. **Chord picker** — root × quality matrix (maj, min, 7, maj7, min7, dim, aug,
   sus2/4, add9, slash bass), with audio preview.
6. **Export / Share** — format choice, preview, share sheet.
7. **Settings** — default tempo/time-sig, A=440 reference, input source,
   account/sync (later).

## 7. Technical architecture

**Why React Native + native modules:** the UI (library, editor, chart rendering,
forms) is standard app work that RN handles well with one codebase. The hard,
performance-critical parts — microphone capture, DSP, pitch/chord detection — are
done in **native modules** (Swift on iOS, Kotlin on Android) and exposed to JS
through a thin bridge. This avoids the trap of doing audio math in JavaScript.

```
┌──────────────────────────────────────────────────────────┐
│  React Native (TypeScript)                                 │
│  • Screens, navigation, state (Zustand/Redux)              │
│  • Score data model + edit operations                      │
│  • Chart & piano-roll rendering (Skia / SVG)               │
│  • Export (MusicXML / MIDI / PDF) — pure TS libs           │
└───────────────▲───────────────────────┬───────────────────┘
                │ JS bridge (events,     │ commands
                │  analysis results)     │ (start/stop record)
┌───────────────┴───────────────────────▼───────────────────┐
│  Native Audio + DSP module  (Swift / Kotlin)               │
│  • Mic capture (AVAudioEngine / Oboe)                      │
│  • Pre-processing: resample, frame, window                 │
│  • Pitch / melody detection (CREPE-tiny or pYIN)           │
│  • Chord recognition (chroma features → template/ML model) │
│  • Beat / tempo tracking (onset detection → beat grid)     │
│  → returns structured Note[] + ChordSymbol[] + beat grid   │
└────────────────────────────────────────────────────────────┘
```

### The transcription pipeline (record-then-transcribe)
1. **Capture** raw audio (mono, 44.1/48 kHz) to a file.
2. **Onset & beat tracking** → tempo (BPM) + a beat/bar grid.
3. **Melody pitch detection** (monophonic-strong): frame-wise f0 → quantize to
   pitches → segment into notes → snap onsets/durations to the beat grid.
4. **Chord recognition:** compute chroma (12-bin pitch-class energy) per beat →
   classify against chord templates / a small trained model → chord per beat or
   per bar, smoothed over time.
5. **Assembly:** fold notes + chords into Bars using the beat grid → `Score`.
6. **Confidence:** every note/chord carries a confidence; the UI flags the weak
   ones so the musician knows where to look.

### Candidate building blocks (to validate in spike phase)
- Pitch/melody: **CREPE** (tiny variant for on-device), **pYIN**, or **aubio**.
- Chords/chroma: **librosa**-style chroma in native, template matching, or a
  small CNN; **Chordino**-style approaches as reference.
- Beat/tempo: onset-strength + dynamic programming beat tracking.
- Render: **Skia** (react-native-skia) for the piano-roll; **VexFlow** or
  **OpenSheetMusicDisplay** for staff/lead-sheet notation.
- Export: **MusicXML** (interop with Sibelius/MuseScale/Finale), **MIDI**, PDF.

### On-device vs cloud
Default to **on-device** processing for v1: privacy, offline capture, no per-use
cost. Keep the pipeline behind an interface so a heavier cloud model can be
swapped in later for "enhance accuracy" without changing the app.

### Optional backend (where Ruby/Rails *could* fit)
The app itself can't be Rails (it's a web framework, not mobile). But a Rails or
Python/FastAPI backend is a natural fit *later* for: accounts, cloud sync,
project sharing, and an optional server-side "high-accuracy" transcription. Not
needed for v1 (local-only library).

## 8. Editing model (why it makes or breaks the app)

Auto-transcription will never be 100% right, so editing must feel fast and
forgiving:
- **Snap-to-grid** with an easy override (musical time vs. free time).
- **Confidence highlighting:** low-confidence notes/chords are visually marked so
  correction is targeted, not a full re-entry.
- **Audio-synced playback** so the user hears the original against the
  transcription and spots errors by ear.
- **Undo/redo** everywhere; non-destructive (original audio always retained).
- **Bar operations:** split, merge, insert, set/clear time signature per bar.
- **Chord operations:** confirm suggestion, swap via picker, set slash bass,
  delete, move to a different beat.

## 9. Tech stack summary

| Layer | Choice | Notes |
|-------|--------|-------|
| App UI | React Native + TypeScript | One codebase, iOS + Android |
| Navigation/state | React Navigation + Zustand | Lightweight |
| Audio capture | Native: AVAudioEngine (iOS), Oboe (Android) | Low-latency |
| DSP / detection | Native module (Swift/Kotlin), optional Rust core via FFI | Reusable across platforms |
| Rendering | react-native-skia (piano-roll) + VexFlow/OSMD (notation) | — |
| Persistence | SQLite (e.g. WatermelonDB / op-sqlite) + file store for audio | Local-first |
| Export | MusicXML, MIDI, PDF (TS libraries) | Interop + sharing |
| Backend (later) | Rails or FastAPI | Accounts, sync, cloud transcription |

## 10. Phased roadmap

- **Phase 0 — Spikes & feasibility (de-risk the hard part first)**
  Standalone native prototype that records piano audio and runs pitch + chord +
  beat detection on a few test clips. Measure accuracy honestly before building
  UI around it. *Go/no-go gate.*
- **Phase 1 — MVP (record → transcribe → edit → save, piano-only)**
  Capture, on-device transcription, the two-view editor, local library,
  MusicXML/MIDI/PDF export.
- **Phase 2 — Live mode + polish**
  Real-time transcription view, metronome/count-in refinements, better chord
  vocabulary, key/tempo detection improvements.
- **Phase 3 — Accounts, cloud sync & sharing**
  Optional backend, share links, "enhance accuracy" cloud model.
- **Phase 4 — More instruments**
  Guitar (tab + capo/tuning), vocals (lyrics-with-chords), generic mode.

## 11. Open questions / risks

- **Accuracy is the core risk.** On-device chord + melody detection on real piano
  recordings (with sustain, overlap, room noise) is genuinely hard. Phase 0 must
  prove it before we invest in UI. Mitigation: editing-first UX + confidence
  cues so a "70% right" first draft is still a big time-saver.
- **Polyphony creep.** Piano is inherently polyphonic; "melody + chords" is a
  pragmatic simplification. We may detect the chord well but pick the wrong
  "melody" voice. Need test material to tune voice selection.
- **Latency/battery** for the eventual live mode.
- **Notation rendering** on mobile (small screens) — chart view must stay
  readable; consider chord-grid + simplified melody before full staff.

## 12. Success criteria for the MVP

- A user can capture a 30–60s piano idea and, within ~10s of processing, see a
  chart that's recognizable enough to correct in under a couple of minutes.
- Export opens cleanly in MuseScore/Sibelius (MusicXML) and a DAW (MIDI).
- Nothing is ever lost: the original audio is always recoverable.

---

### Next step
Once this design is approved, the recommended first build is **Phase 0**: a
narrow native spike that proves the transcription pipeline on real piano audio,
*before* writing the app around it. That's where we'd "transform it into code."
