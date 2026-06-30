# Scorewright (working title)

A mobile app (iOS + Android) for musicians to **capture a live performance and
transcribe it into an editable chart** — melody note-by-note, organized into
bars, with chord progressions recognized automatically.

> **Status:** Product design phase (pre-code).
> Start here → [`docs/product-design.md`](docs/product-design.md)

## What it does (v1)
- 🎹 Record a piano/keys idea or song.
- 🎵 Auto-transcribe the melody **note by note**.
- 🎼 Recognize **chord progressions** (Cmaj7, G7, Am…).
- 📐 Lay it out in **bars** you can define and edit.
- ✏️ Edit everything — notes, chords, bars — in a two-view editor
  (chart + piano-roll).
- 📤 Export to MusicXML / MIDI / PDF.

## Locked scope decisions
| Decision | Choice |
|----------|--------|
| Transcription | Melody + chord recognition (not full polyphonic separation) |
| Capture | Record-then-transcribe for v1; live mode later |
| Primary instrument | Piano / keys |
| Stack | React Native (TypeScript) UI + native Swift/Kotlin audio/DSP modules |

## Roadmap
- **Phase 0** — Feasibility spike: prove pitch + chord + beat detection on real
  piano audio (go/no-go gate).
- **Phase 1** — MVP: capture → transcribe → edit → save → export (piano-only).
- **Phase 2** — Live real-time mode + polish.
- **Phase 3** — Accounts, cloud sync, sharing.
- **Phase 4** — More instruments (guitar, vocals, generic).

See the full [product design document](docs/product-design.md) for details.
