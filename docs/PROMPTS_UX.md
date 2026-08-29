# Execution prompts — UX tickets

Paste one prompt per agent session. Tickets are defined in `docs/TICKETS_UX.md`. Each prompt states its objective first, because an agent that knows what the feature is for makes better decisions when the spec meets the code than one following a field list.

Repo state at 14:20: `apps/api` serves `/api/realtime-token` and `/ws`. `packages/api-client/src/realtime.ts` holds the `ServerMessage` union and hand-written parsers. `apps/web/src/screens/landing-screen.tsx` is the only screen on `main`. The session screen, the transcript list and the waveform live on the `waveform-layout-transition` worktree branch and are not merged.

Rules that apply to every prompt. TypeScript is strict, `any` is banned, non-null `!` is banned. Python is `mypy --strict` clean. Import backend types from `@glia/api-client`, never hand-write them in `apps/web`. Do not add a second Cala call site. Do not put a secret behind a `VITE_` variable. Render every string that came from a page we do not control as text, never as HTML. Run `pnpm lint`, `pnpm typecheck` and `pnpm build` before reporting done. Do not run `git commit`.

---

## G-0 · Candidate contract

Both ends. One agent. G-1, G-2 and G-3 are blocked on it.

```
OBJECTIVE

Glia's backend can currently tell the browser two things: what the user said, and what
the distiller understood. It cannot yet say "here is an image I found, and here is
where it came from". That message does not exist, so the image grid has nothing to
render and there is nowhere to carry the evidence quote Cala returns with each source.

That quote is what the demo turns on. The claim Glia makes is that Cala decided what
the user meant and which sources were credible, and that the reference images come
from documents Cala cited. A reference image with no publisher and no quote under it
is an anonymous pixel and the claim is unprovable. Your job is to open the channel
that carries the proof.

You are writing plumbing that four visible features depend on. Get the shape right and
they are all cheap. Get it wrong and they are all blocked at 16:30 with an hour left.

CONTEXT

Read docs/STACK.md, section "What Cala actually does here", so you understand why
publisher and evidence exist and why there is no image field coming from Cala itself.
Read apps/api/glia/contracts.py and packages/api-client/src/realtime.ts and match
their existing style exactly. Both files already carry a working message union.

TASK

Add to apps/api/glia/contracts.py, following the StrictModel pattern already there:

  CandidateLane = Literal["cited", "open"]

  class Candidate(StrictModel):
      id: str
      lane: CandidateLane
      image_url: str
      source_url: str
      publisher: str | None = None
      title: str | None = None
      evidence: str | None = None
      licence: str | None = None
      entity_name: str | None = None
      entity_type: str | None = None
      width: int | None = None
      height: int | None = None
      score: float

  class CandidatesBatch(StrictModel):
      type: Literal["candidates.batch"] = "candidates.batch"
      revision: int
      candidates: list[Candidate]

  class LedgerUpdated(StrictModel):
      type: Literal["ledger.updated"] = "ledger.updated"
      cala_queries: int
      references: int
      cited: int

Add both messages to the ServerMessage union.

What each field is for. source_url is the article page, image_url is the picture we
extracted from it, and they are different URLs on lane cited. publisher and title
describe the document. evidence is the quote Cala returned alongside that origin.
licence is set on lane open only, where the image comes from Commons or Openverse and
attribution is a licence condition rather than a claim. entity_name and entity_type
carry the entity Cala resolved for the query that produced this candidate, and are
null on lane open because no entity resolution happened there. LedgerUpdated exists so
the UI can show what the cost gate saved, which is the number the demo leads with.

Every descriptive field is nullable because real pages are missing og:site_name, real
Cala origins sometimes carry no quote, and a contract that pretends otherwise fails on
stage rather than in review.

Mirror all of it in packages/api-client/src/realtime.ts. Write parseCandidate,
parseCandidatesBatch and parseLedgerUpdated by hand in the style of the existing
parseVisualIntent. Do not add zod or any other validation dependency. A message with a
missing or wrong-typed required field returns null, exactly as every other parser in
that file does. Reject a candidate whose image_url or source_url is not http or https.
Export the new types from packages/api-client/src/index.ts.

Add unit tests. Python: a valid batch parses, an unknown extra field is rejected, a
candidate with evidence null parses. TypeScript: parseServerMessage returns null for a
batch containing one malformed candidate.

CONSTRAINTS

Do not change any existing message type. Other work is in flight against them right
now. Do not touch the socket handler. Do not implement discovery, ranking or the
ledger's arithmetic. This ticket is the contract and nothing else.

DONE WHEN

Both ends agree, tests pass, and a frontend agent can import Candidate and build
against it without the discovery pipeline existing.
```

---

## G-1 · Fixture harness

Frontend. Start once G-0 has merged. Blocks G-2 and G-3.

```
OBJECTIVE

The image grid is the largest piece of frontend work left and the discovery pipeline
that feeds it does not exist yet. If the grid waits for real candidates it gets built
at 16:30, integrated at 16:55 and rehearsed never. This ticket removes that
dependency: a scripted candidate stream so the grid, the badges and the provenance
card can be built and polished now, against data that is deliberately nastier than
what the real pipeline will send.

The fixture is also the test suite. Every ugly case you put in it is a case that
cannot embarrass us on stage.

CONTEXT

Read apps/web/src/hooks/use-realtime-transcription.ts and reuse its FIXTURE_TRANSCRIPT
convention. Read packages/api-client/src/realtime.ts for the Candidate type from G-0.

TASK

Create apps/web/src/lib/fixtures/candidates.ts. Export a function taking a callback of
(message: ServerMessage) => void and returning a cleanup function. It emits a
candidates.batch after 900ms, a second after 3200ms, and a ledger.updated after each.
Two waves, because the grid reflowing when the idea sharpens is the product's central
moment and you cannot tune it against a single batch.

The fixture data carries every case the UI has to survive:
  - both lanes, roughly eight cited and eight open
  - one candidate with a 240-character evidence quote
  - one candidate with publisher null and title null
  - one candidate whose image_url 404s, to prove a tile degrades instead of vanishing
  - one portrait image and one very wide panorama
  - one title containing <script>alert(1)</script>, to prove strings render as text

Gate it behind import.meta.env.VITE_GLIA_FIXTURES === '1' and document the variable in
.env.example. It is a dev flag and carries no secret.

CONSTRAINTS

Wire it at the same boundary the real WebSocket messages arrive on, so deleting the
fixture later is deleting one call rather than unpicking a parallel code path. Do not
change the parsers. Do not change behaviour when the flag is off.

DONE WHEN

VITE_GLIA_FIXTURES=1 pnpm dev, no API running, and two waves of candidates arrive.
```

---

## G-2 · CandidateTile and lane badge

Frontend. Depends on G-0 and G-1. Critical path.

```
OBJECTIVE

Two thirds of Glia's screen is currently an empty region. This ticket fills it, and it
is the moment the product sells itself: the user talks, images arrive, the user changes
direction mid-sentence and the images reorganise. A judge remembers that or remembers
nothing.

The badge on each tile carries a second job. Cala returns no images. Ours come from
the pages Cala cited, and from Wikimedia Commons and Openverse. Saying which lane each
image came from, on every tile, is what makes the Cala claim honest and therefore worth
making. An unbadged grid is a mood board. A badged grid is an argument.

CONTEXT

Read docs/STACK.md, section "What Cala actually does here", for what the two lanes are.
Read docs/CALA_DEMOS.md, section "For Glia", for why the badge is not hover-only.
Develop against the G-1 fixture.

TASK

Hold the candidate pool in the Zustand session store, keyed by id, newest batch last,
deduplicated by id on arrival. Create apps/web/src/components/candidate-tile.tsx and
apps/web/src/components/candidate-grid.tsx, and render the grid inside Workpane. CSS
grid, not canvas.

Every tile carries a badge reading CITED or OPEN, always visible. Both lanes use the
same position, size and shape, so the two read as one system rather than as a claim and
a disclaimer.

Motion is the product's feel here, not decoration. A batch lands as a staggered wave.
Use AnimatePresence for arrival and departure, and a layoutId on the tile, because a
tile becomes a pin later and that shared-element transition is already planned. Under
useReducedMotion the grid reaches the same end state with no travel.

A tile whose image fails to load keeps its badge and its source line and shows a
neutral placeholder. It is never removed. An image 404 is not a reason to make the
grid flicker on stage.

CONSTRAINTS

Titles and publishers come from pages we do not control. Render them as text. No
dangerouslySetInnerHTML.

DONE WHEN

Two fixture waves land as waves, every tile is badged, the 404 tile degrades in place,
and reduced motion reaches the same layout.
```

---

## G-3 · ProvenanceCard

Frontend. Depends on G-2. Highest value per minute on the board.

```
OBJECTIVE

Answer the question "why am I looking at this image?" in the source's own words.

Everything else in Glia could be built on a keyword image search. This cannot. Cala
returns, with each source it cites, the quote that made that source relevant. Putting
that quote under the image is the difference between "we found some pictures" and
"Cala decided what you meant, judged these sources credible, and here is the sentence
that made it choose this one". It is also the answer to the question every judge is
already forming, which is whether Glia is a text-to-image wrapper with extra steps.

Twenty-five minutes of work. It carries the whole partner integration.

CONTEXT

Read docs/CALA_DEMOS.md, section "For Glia". The three demos Cala features on its own
site all expose sources this way, and the community demos that won both built an
explicit explainability surface. Read the Candidate type from G-0. Develop against the
G-1 fixture.

TASK

Create apps/web/src/components/provenance-card.tsx, opening on hover and on keyboard
focus of a CandidateTile. Both, not one. Use a shadcn primitive if one already exists
in apps/web/src/components/ui, otherwise add the smallest Radix primitive that gives
correct focus and dismiss behaviour.

A cited candidate shows publisher, title and the evidence quote. Give the quote the
most visual weight of the three and clamp it at four lines. An open candidate shows
publisher and licence in the same slots, in the same card, at the same size.

Every field is nullable. A candidate with publisher, title and evidence all null shows
the source host alone. It never shows an empty card, a blank row, or the string "null".
This case is in the fixture because it will happen live.

CONSTRAINTS

Every string in this card came from a page we do not control. All of it renders as
text. No dangerouslySetInnerHTML in this file.

DONE WHEN

Hover and Tab both open it, Escape dismisses it, the 240-character quote clamps rather
than overflowing, and the all-null candidate renders the host with no empty rows.
```

---

## G-4 · Openers on the landing screen

Frontend. No dependency. Run it in parallel.

```
OBJECTIVE

Glia opens on a microphone and the words "Speak your mind". For the demo that restraint
is right. For a judge who picks up the laptop it is a blank page: they hold the mic,
say nothing, and hand it back. Every demo Cala features on its own site opens with a
search box plus hand-picked examples, each with a line saying why that one is
interesting, precisely so nobody has to think of a query cold.

Give a stranger a line to say, without spending the opening beat of our own demo.

CONTEXT

Read apps/web/src/screens/landing-screen.tsx and keep its restraint. Read
docs/STACK.md for Cala's coverage.

TASK

Three cards below the caption. Each names a subject to speak and gives one line on why
it is interesting. Write the copy so a stranger knows what to say two seconds after
reading it.

At least one subject sits inside Cala's coverage, which is finance, legal, healthcare,
HR and agro, so lane cited visibly fires for someone trying it unaided. The other two
can be anything a person would actually want to see.

The cards fade in 2500ms after the screen reaches idle. They do not appear with the
caption. The empty screen is the first beat of the demo and the speaker starts talking
before the cards arrive, so both audiences are served by the same screen.

CONSTRAINTS

Clicking a card does not fill the transcript. Glia is a voice product and a
click-to-fill card quietly turns it into a text box on stage. A card is a line to read
aloud, so a click may highlight it and nothing more.

Cards are keyboard reachable. Their appearance does not move the microphone control.
Under useReducedMotion they appear without the fade.

DONE WHEN

The mic control sits at an identical position before and after the cards appear.
```

---

## G-5 · Pipeline legend in the empty workpane

Frontend. No dependency.

```
OBJECTIVE

For the first twenty seconds of the demo the right two thirds of the screen is empty
while the user talks. Six partner technologies are doing real work in that silence and
the audience can see none of it. Name them there, quietly, and let the first wave of
images wipe the legend away.

The demos that won on Cala's own site all state plainly which component does what.
This is that, in the dead space we already have.

CONTEXT

Read docs/STACK.md for the pipeline and name each stage as that document names it.

TASK

One faint line, six stages: transcription, distiller, Cala, lanes, ranking, generation.
Under Cala, one short line saying it resolves entities and cites sources.

It renders only while the candidate pool is empty. The first batch replaces it, and the
replacement does not shift the grid's first row.

CONSTRAINTS

Cala returns no images. No wording may imply otherwise, here or anywhere in the UI.

DONE WHEN

Visible before the first fixture batch, gone after it, no layout jump.
```
