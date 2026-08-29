# Cala highlighted demos — what they reward

Source: https://www.cala.ai/demos (checked 2026-08-29). Six featured demos; all
are gated behind "Request access" — public pages give a description plus one
preview screenshot. Notes below are from those pages.

## The six

| Demo | Origin | What it does |
|---|---|---|
| AML Screening | Cala + Cognition (built with Devin) | Traces ownership/control structure of an entity and its related parties; flags EU & UN sanctions designations and PEP exposure; sourced findings in an interactive investigation workflow. Entry screen = one search box + 4 curated example entities (Glencore, DN Capital, Libyan Investment Authority, Petropars UK), each with a one-line reason it is interesting. Header badge: `DEMO · SANCTION DATA: EU & UN`. |
| Adverse Media Screening | Cala × ElevenLabs | Negative-news screening (fraud, corruption, enforcement) on an entity and its related parties, every hit backed by its source. Findings also rendered as an ElevenLabs voice explainer on top of the static report. Entry screen = 14 pre-picked companies (Enron, Theranos, FTX, WorldCom, Parmalat, Petrobras, Boeing, VW, Wells Fargo, McKinsey, Adani, First Brands…) each labelled with sector, country and the scandal in italics. |
| Entity Watch | Cala × Lovable | Continuous monitoring of a chosen portfolio of entities across public sources; surfaces adverse media, regulatory actions, leadership changes and other material signals in a single matrix. Entry screen = multi-select chips of banks, cap 5, plus "add your own entity → Search Cala". |
| Trace Intelligence | Community (Mian Deng, Megathon Amsterdam) | Turns a contested question ("what's moving the Dutch housing market?") into a causal graph + user-added personal variables + a deterministic engine that recomputes on every change. Shows indicator triggers (what the decision is most sensitive to) and a deep mode exposing every element, its assigned weight, the source article and a confidence level. Cala supplies the graph elements. |
| Monte Carlo Cathedral | Community, runner-up, Project Europe Barcelona (Team Abrollo) | Claude reads Cala entities (companies, people, countries) to form hypotheses about how they relate; a shock propagates along the graph (Taiwan/TSMC supply risk → global chip supply −15% → NVDA/AMD/ASML down together), one of hundreds of chains. Then 10,000 Monte Carlo futures pick the portfolio that survives the worst case. Best run +55%, average +42%. |
| Orbit / "simulated year" | Community, winner, Project Europe Barcelona (Jeffrey Chang) | Six-agent research pipeline, one agent per data source (macro, supply chain via Cala's entity graph, Reddit sentiment, options flow, on-chain BTC, SEC filings), each finding narrowing the next agent's search. 52-stock portfolio, +1,547% simulated vs 32% S&P. >150 Cala API calls, each cited. Extra Explainability Agent answers "why this stock?" with a sourced thesis. |

## Pattern — what gets you featured

1. **Traceability is the thesis, not a feature.** Every write-up ends on the
   same line: nothing asserted without a place to verify it. Weights, sources
   and confidence levels are shown in the UI, not buried.
2. **The graph is used as a graph.** Winners traverse relationships — related
   parties, beneficial owners, causal chains between entities — rather than
   doing single-entity lookup. "One fact doesn't stay isolated."
3. **Cala is one lane, explicitly bounded.** The best write-ups name what Cala
   does and what other components do ("Claude does the reading, the graph does
   the connecting, the simulation does the deciding, each part stays in its own
   lane"). Composition with a named partner (Devin, ElevenLabs, Lovable, fal)
   is a plus, not a distraction.
4. **A hard number as the headline.** +1,547%, $16.5M, 10,000 simulations,
   150 cited API calls, 3 days of work → 2 hours. Every community demo leads
   with one.
5. **Curated entry points.** All three first-party demos open on a search box
   plus hand-picked examples with a one-line "why this one is interesting".
   Nobody is asked to think of a query cold.
6. **An explainability surface.** Orbit's Explainability Agent, Trace's deep
   investigative mode, AML's "sourced findings" — a second view that answers
   "why did you show me this?" with citations.
7. **All six are finance/risk.** Cala's featured set is entirely AML, adverse
   media, monitoring and investment. Anything outside finance is uncontested
   territory — and unproven with them.

## For Glia — where each ingredient lands in the UI

Written 14:09, freeze at 17:00. Ordered so that everything in "already in the
build" is a component Sergio is writing regardless; the ingredient is a
decision about what that component renders, not extra scope.

### Already in the build — decide these now, they cost nothing extra

**Candidate tile → badge + provenance on hover.** (ingredients 1, 6)
Every tile carries its lane badge, `CITED` or `OPEN`, always visible, never on
hover only — a badge you have to discover does not read as a claim. Hover or
focus opens a provenance card: publisher, document title, and **the evidence
quote Cala returned with that origin**. The quote is the part no image search
can produce; it is the single most convincing pixel in the product. `OPEN`
tiles show source and licence in the same slot, same shape, so the honesty is
structural rather than a disclaimer.

**Pin rail → "conditioning input", stated in the UI.** (Trace's recompute)
Label the rail `3 pins · conditioning input`, not `Pinned`. On Generate, the
pinned thumbnails render inside the prompt panel, upstream of the prompt text,
so the causal direction is visible without narration.

**Result view → keep the previous generation.** (demo step 8)
When a regeneration follows an unpin, keep the prior image as a small `BEFORE`
thumbnail beside the new one. The demo beat currently depends on the audience
remembering an image from thirty seconds ago. Do not make them.

### Cheap additions — under twenty minutes each, high demo yield

**Curated openers on the landing screen.** (ingredient 5)
All three first-party Cala demos open on a search box plus hand-picked examples
with a one-line reason. Glia opens on a blank mic, which is worse: a judge who
picks up the laptop has to invent a subject cold. Three cards under the
caption, each a subject and one line of why, e.g. *"a shipping company at
dusk — Cala resolves the entity, references arrive cited."* Fade them in ~2.5s
after idle so the empty-screen beat in the demo script survives intact; the
speaker starts talking before they appear, the hands-on judge sees them.
Make at least one opener finance-adjacent so Lane A visibly fires — every
featured demo is finance, and that is where Cala's coverage is.

**The understanding strip.** (ingredient 2 — the one Glia is missing)
A slim row between transcript and grid: the distilled attribute chips
(subject, mood, style, palette, composition, medium, era) updating live, then
one line reading `resolved → <Entity> · <type>` and, beneath it, the cited
documents. Chips → entity → sources, one hop per line. This is the difference
between querying a graph and traversing one, and it is the visual proof for
demo beat 4 that Glia is listening rather than searching. If time runs short,
ship the chips row alone with the resolved entity name appended.

**The ledger, promoted out of the dev HUD.** (ingredient 4)
Every community demo leads with one hard number; ours is the gate.
`4 Cala queries · 63 references · 19 cited` in the corner during the session,
and as the headline stat on the result view. It makes the cost argument
visible without a slide, and it is a field the WebSocket already carries.

**Pipeline legend in the empty workpane.** (ingredient 3)
The pane is empty until the first candidates arrive. Put the six-partner chain
there in faint type — transcription → distiller → Cala (entities + citations)
→ lanes → fal — and let the first tile wave replace it. It occupies dead space
during the beat when the audience is looking at nothing, and it names each
lane the way the winning write-ups do.

### Cut line

Drop first if 16:00 arrives and the grid is not solid: salience weight bars on
the chips, entity UUIDs on screen, the BEFORE thumbnail. Keep the badge and
the provenance quote under every circumstance — without those the Cala
integration is invisible and the demo is a text-to-image wrapper.
