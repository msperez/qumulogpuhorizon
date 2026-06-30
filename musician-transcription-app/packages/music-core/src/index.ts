// Public surface of the Scorewright music-core package.
//
// This package is pure TypeScript with no platform dependencies, so it runs
// unchanged in the React Native app, in Node tests, and anywhere else.

export * from './types.ts';
export * from './chords.ts';
export * from './quantize.ts';
export * from './midi.ts';
export { transcribeToScore } from './transcribe.ts';
export type { Analysis } from './transcribe.ts';
