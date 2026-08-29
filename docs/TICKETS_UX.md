# UX tickets — Cala ingredients

Cut from `docs/CALA_DEMOS.md`. Written 14:15, freeze 17:00. Frontend lane
unless stated. Estimates assume agent-assisted work and no integration
surprises.

## G-0 · Candidate contract addendum — BLOCKING, do first

All three, 15 min, before anyone writes a tile.

The provenance card needs fields that may not be in the agreed `Candidate`
shape. Confirm or add now; discovering it at 16:30 costs the ingredient.

```
lane:        'cited' | 'open'
publisher:   string | null      # Cala origin publisher, or Commons/Openverse
title:       string | null      # document title
evidence:    string | null      # the quote Cala returned with the origin
source_url:  string             # the page, not the image
licence:     string | null      # lane B only
```

`evidence` is the one that will be missing. It is also the single most
convincing element in the demo. Lluís owns `Candidate`; Yazide owns the
WebSocket union. Agreed in the channel, in writing, before 14:30.

Acceptance: the shape is posted in the channel and both ends have read it.

## G-1 · Fixture harness for the candidate stream

Frontend, 25 min. No dependency. **Do this before any other frontend ticket.**

A local module that emits a scripted sequence of `Candidate` messages on a
timer — two waves, mixed lanes, one with a long evidence quote, one with a
null publisher, one with a broken image URL. Toggled by a dev flag; the real
WebSocket replaces it at the same boundary.

Without this the whole frontend lane is blocked on a backend that does not
exist yet, and every ticket below inherits that block.

Acceptance: `pnpm dev`, no API running, tiles arrive in waves and reflow.

## G-2 · CandidateTile with lane badge

Frontend, 30 min. Depends: G-0, G-1. Critical path — this is the grid.

`CITED` / `OPEN` badge always visible, never hover-only. Same slot, same
shape, both lanes. Motion staggered entry so a wave lands as a wave.

Acceptance: a mixed wave renders, every tile is badged, reduced-motion gives
the same end state with no travel.

## G-3 · ProvenanceCard

Frontend, 25 min. Depends: G-2.

Hover and keyboard focus open publisher, document title and the evidence
quote. Lane B fills the same card with source and licence. All of it renders
as text, never as HTML — these strings come from pages we do not control.

Acceptance: hover and focus both open it; a candidate with null publisher and
null evidence degrades to source only without an empty box.

## G-4 · Openers on the landing screen

Frontend, 20 min. No dependency. Standalone — can be done any time.

Three cards under the caption, each a subject and one line of why. Fade in
~2.5s after idle so the empty-screen beat survives. At least one subject
inside Cala's coverage so Lane A visibly fires for a judge holding the laptop.

Acceptance: cards appear after the beat, not with the caption; keyboard
reachable; they do not shift the mic's layout position.

## G-5 · Pipeline legend in the empty workpane

Frontend, 15 min. No dependency. Standalone.

The six-partner chain in faint type where the pane is empty, replaced by the
first candidate wave.

Acceptance: visible before the first candidate, gone after, no layout jump.

## G-6 · Ledger chip

Frontend + backend field, 15 min frontend. Depends: a `ledger` field on the
session message — mock it in G-1 until it lands.

`4 Cala queries · 63 references · 19 cited` in the corner during the session;
the same numbers as the headline stat on the result view.

Acceptance: increments on a real query, does not move while idle.

## G-7 · Understanding strip

Frontend, 40 min. Depends: distilled attributes on the WebSocket — mock in
G-1. The ingredient Glia is missing; also the most expensive here.

Chips row (subject, mood, style, palette, composition, medium, era) updating
live, then `resolved → <Entity> · <type>`, then the cited documents.

Reduced scope if 16:00 passes: chips row alone with the entity name appended.
Ship the reduced version rather than nothing — the chips carry demo beat 4.

Acceptance: chips change visibly when the transcript changes direction.

## G-8 · Pin rail wording and prompt panel thumbnails

Frontend, 15 min. Depends: pin state, result view.

Rail reads `N pins · conditioning input`. Pinned thumbnails render inside the
prompt panel, above the prompt text.

Acceptance: the panel shows thumbnails upstream of the prompt with no
narration needed.

## G-9 · BEFORE thumbnail on regeneration

Frontend, 20 min. Depends: result view. **First to cut.**

Keep the prior generation as a small `BEFORE` beside the new one after an
unpin-and-regenerate.

Acceptance: demo step 8 is legible without the audience remembering an image.

## Order

```
14:15  G-0   all three, in the channel
14:30  G-1   fixture harness
15:00  G-2   tile + badge          ─┐ critical path
15:30  G-3   provenance card       ─┘
16:00  G-4   openers                  standalone, hand off if someone is free
16:15  G-5   pipeline legend          standalone
16:30  G-6   ledger chip
16:45  G-7   understanding strip, reduced scope
       G-8   fold into the result view as it is built
       G-9   cut unless everything above is done and rehearsed
```

G-2 and G-3 are non-negotiable. Without a badge and a source under every
image the Cala integration is invisible and Glia reads as a text-to-image
wrapper — which is the one question the demo exists to pre-empt.
