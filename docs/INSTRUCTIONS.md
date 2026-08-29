# Project instructions

How we build Glia today. `docs/HACKATHON.md` for event facts, `docs/STACK.md` for architecture, `docs/PARTNERS.md` for every API detail, `docs/SECURITY.md` for the threat model.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node | 22 LTS | `fnm install 22` |
| pnpm | 10 | `corepack enable && corepack prepare pnpm@latest --activate` |
| Python | 3.13 | `uv python install 3.13` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker | latest | Postgres + Redis |
| entire | latest | `brew tap entireio/tap && brew install --cask entire` |

## First run

```bash
git clone git@github.com:<org>/glia.git && cd glia

curl -fsSL https://github.com/AikidoSec/safe-chain/releases/latest/download/install-safe-chain.sh | sh
entire enable -y --agent claude-code

pnpm install --frozen-lockfile
cd apps/api && uv sync --frozen && cd ../..

cp .env.example .env      # fill in the keys; never commit .env

docker compose -f infra/docker-compose.yml up -d
cd apps/api && uv run alembic upgrade head && cd ../..

pnpm dev
```

Web `http://localhost:5173`, API `http://localhost:8000`, OpenAPI `/docs`. Microphone needs a secure context — `localhost` counts, deployed needs HTTPS.

## Commands

| Command | What |
|---|---|
| `pnpm dev` | everything, watch mode |
| `pnpm build` | Turborepo build, cached |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` | Biome / tsc / Vitest |
| `pnpm gen:api` | regenerate `packages/api-client` from the live OpenAPI schema |
| `uv run ruff check --fix .` | lint + format Python |
| `uv run mypy .` | strict type check |
| `uv run pytest` | backend tests |
| `uv run alembic revision --autogenerate -m "..."` | new migration |

## The three spikes — do these before anything else

Each is a known unknown that will cost an hour if discovered late. Timebox each to 20 minutes. If one fails, take the fallback and move on.

1. **OpenAI WebRTC + transcription session.** No end-to-end example exists in the docs. Get a token minted, a peer connection open, and one `...transcription.delta` printed to the console. *Fallback: browser → our FastAPI WebSocket → OpenAI WebSocket. Fully documented, one extra hop.*
2. **GLiNER2 response shape.** Pioneer publishes no example `result` body. Send one request with our `structures` schema and print the raw response. Pin the parser against what actually comes back. *No fallback — everything downstream depends on this shape.*
3. **Cala → images.** Run one `knowledge/search` on a demo-realistic subject and confirm `context[].origins[].document.url` yields pages with usable `og:image`. Count how many of ten URLs actually produce an image. *If the hit rate is poor, Lane B carries the demo and Lane A becomes the differentiator rather than the workhorse — adjust the script, not the architecture.*

Report all three results in the channel before 12:30. They determine whether the plan survives contact.

## Conventions

**Language.** Code, comments, commits, docs and UI strings in English.

**TypeScript.** `strict: true`, no `any`, no non-null `!`. Never hand-write a backend response type — import from `packages/api-client`.

**Python.** Full annotations, `mypy --strict` clean. Pydantic v2 at every boundary. Every I/O `async def` gets an explicit timeout. No bare `except`.

**One fetcher.** Every outbound request to a URL we did not hardcode goes through `glia/discovery/fetch.py`. It carries the SSRF guards, the byte caps and the redirect rules. There is no second path, and adding one is a security bug.

**One gate.** Cala is called from exactly one place, behind the distiller gate and the debounce, through the cache, and it increments the credit ledger. Do not add a second call site "just to try something" — that is how 1,100 credits become 40.

**Errors.** RFC 9457 problem details. Never leak a stack trace or an upstream vendor error body to the client — log it, return a correlation id.

**No secrets in `apps/web`.** Anything `VITE_`-prefixed is public. The browser's only credential is the 600-second OpenAI ephemeral token.

**Untrusted text is text.** Titles, authors, licences and `og:` tags come from pages we do not control. They render as text, never as HTML, and they never enter a model prompt as instructions.

**Migrations.** Alembic, generated and committed. Nobody edits the database by hand.

## Git workflow

Trunk-based. `main` is always deployable. Short-lived branches, small PRs, squash merge.

```
feat(discovery): extract og:image from cala-cited article pages
fix(realtime): reconcile transcription deltas by item_id
perf(distiller): skip cala query when jaccard distance under threshold
chore(ci): gate builds on new critical dependency findings
```

Conventional commits. Every commit gets an `Entire-Checkpoint` trailer — answer `[a]lways` at the first prompt.

Never force-push `main`. Never commit `.env`, `.entire/settings.local.json`, `.entire/logs/`, or `.aikidotmp/`.

## Definition of done

- [ ] Works on a clean clone following the README verbatim
- [ ] `pnpm typecheck` and `uv run mypy .` pass
- [ ] `pnpm lint` and `uv run ruff check .` pass
- [ ] No secret reachable from the browser
- [ ] Any new outbound call goes through the one fetcher, with timeout and cache
- [ ] The Cala credit ledger did not move when it should not have
- [ ] It is visible in the 2-minute demo, or it should not have been built today

## Division of work

Three people, seven hours, no overlap. Own your lane, integrate at the seams.

| Owner | Lane | Seam |
|---|---|---|
| **Yazide** (captain) | Backend core: FastAPI, WebSocket session channel, Postgres schema, OpenAI token minting, prompt synthesis, fal generation | The OpenAPI schema and the WebSocket message contract — publish both early |
| **Sergio** | Frontend: the four-phase screen, live transcript, image grid with Motion choreography, pinning, the result view | `packages/api-client` (generated) and the WebSocket message types |
| **Lluís** | Discovery + ops: the distiller, the gate, the fetcher with SSRF guards, both image lanes, dedupe and ranking, Aikido, Entire, deploy | The `Candidate` type — lane, url, attribution, hash, score |

Agree the `Candidate` shape and the WebSocket message union **in the first thirty minutes**. Everything else can move independently once those two contracts are fixed.

The captain also owns the submission form. Everyone owns the demo script.

## Cadence

Fifteen minutes, standing, on the hour: what shipped, what is blocked, is anything at risk of missing 17:00. No status essays.

**17:00 is feature freeze.** After 17:00 the only permitted changes are bug fixes on the demo path, docs and the README. A feature started at 17:15 has never once been finished by 19:00.

## Demo script (5 minutes, finalist stage)

Rehearse twice before 19:00.

1. **0:00 — the problem.** "I can tell you exactly how I want an image to feel. I cannot write the prompt." One sentence, no slide.
2. **0:20 — the empty screen.** *Speak your mind.* Let it sit for a beat. The restraint is the point.
3. **0:30 — speak.** Start talking about a real subject inside Cala's coverage. Transcript appears word by word. First references drift in.
4. **1:15 — the idea shifts.** Change direction mid-sentence — "actually, more like a film still, colder." Show the grid reorganising. *This is the moment that sells the product: it is listening, not searching.*
5. **2:00 — the badges.** Hover a **cited** image: publisher and source document. "Cala decided what I meant and which sources were credible. This image came from one it cited." Then an **open** one. Honest, and it makes the Cala integration concrete.
6. **2:30 — pin three.** Explain that pins are conditioning inputs, not mood-board decoration.
7. **3:00 — Generate.** The prompt appears next to the transcript. Read it aloud — "this is what we understood you to mean." Then the image.
8. **3:45 — the proof pins matter.** Unpin one, regenerate. The output visibly changes. Thirty seconds, and it kills the "is this just a text-to-image wrapper" question before anyone asks it.
9. **4:15 — the engineering.** Zen blocking a hostile URL live, the security panel, and `entire why` on the fetcher. "We request URLs the open web chose for us — here is what stops that being a problem."
10. **4:45 — close.** "Six partner technologies, each doing real work. Speak until you see it."

Record a fallback video of steps 2–8 on the laptop. Conference wifi and a live microphone have ended better projects than ours.

## Risk register

| Risk | Mitigation |
|---|---|
| WebRTC + transcription session is undocumented | Spike #1 in the first 20 minutes; WebSocket fallback is fully documented |
| GLiNER2 response shape unknown | Spike #2 before any code depends on it |
| Cala returns nothing for the demo subject | Script the demo around a subject inside Cala's coverage; Lane B always runs |
| Cala credits leak during dev | Redis ledger in the dev HUD; hard ceiling that refuses rather than overspends |
| Image fetch is slow and the grid feels dead | Bounded concurrency, stream candidates as they arrive rather than batching, skeleton tiles immediately |
| Zen blocks our own fetcher | Build in detect-only; flip at 17:30 and re-test the happy path |
| Mic permission fails on stage | HTTPS deploy verified by 15:00; test on the actual demo laptop, not a dev machine |
| Conference wifi | Recorded fallback video; pre-warmed cache |
| Deploy eats the last hour | Deploy hello-world at 14:00, before there is anything to lose |
