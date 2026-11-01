# 0004 Keyframes replace zoom & pan — 2026-11-01

## Context

Video clips had a zoom & pan effect (ranges with a scale, a focus point and ease lengths). Version 0.11.0 adds keyframed transforms (position, size, rotation, crop, opacity), which cover zooms and much more.

## Decision

- Keyframes replace zoom & pan: the `zooms` field, its interface, its render path (`zoompan`) and its Camtasia mapping are removed.
- No migration: nobody uses the app yet (the owner's decision). A project saved with zooms opens; the unknown `zooms` field is kept as an unknown field and ignored. This is the one exception to the migration rule of `AGENTS.md`; later structural changes follow it again.

## Consequences

- One animation model for preview, render and exports (`editor/keyframes.py`, `frontend/src/keyframes.ts`).
- A zoom is now made with keyframes (for example: a keyframe, then a larger one 0.3 s later, then the same size, then back).
