This project won Best use of Pioneer, with a compensation of 500€.

# Glia

**Speak until you see it.**

A voice-powered visual thinking tool. Built at [{Tech: Europe} x Cala Hackathon — The Summer Lock-In](docs/HACKATHON.md), Barcelona, 29 August 2026.

---

The screen starts almost empty and says *Speak your mind*.

As you talk, Glia transcribes you live and starts surfacing visual references — images that drift in and reorganise as the idea sharpens. Pin the ones that resonate. Every pin teaches Glia more about the subject, mood, style, palette and composition you actually mean. When the direction feels right, hit **Generate**, and Glia composes the live conversation, the distilled essence of the idea, your pinned references and the visual direction it discovered into one original image — shown next to the transcript and a concise prompt capturing what you imagined.

It is for people who can describe a feeling but cannot write the perfect visual prompt. The gap between *"something warm and brutalist, but lonely"* and a working diffusion prompt is where Glia lives.

## Demo

- **2-minute video:** _TODO — Loom link_
- **Live:** _TODO — deployed URL_

## How it works

```
  mic ──WebRTC──▶ OpenAI Realtime (gpt-live-transcribe)
                        │ deltas paint locally · settled turns → FastAPI
                        ▼
              DISTILL — Pioneer GLiNER2
              transcript → {subject, mood, style, palette,
                            composition, medium, era}
              milliseconds, fractions of a cent
                        │
                        │ gate: did the idea materially change?
                        ▼ yes
        ┌───────────────┴───────────────┐
   LANE A — cited                  LANE B — open
   Cala resolves the entity        Wikimedia Commons
   + knowledge/search →            + Openverse
   cited article URLs →
   extract og:image
        └───────────────┬───────────────┘
                        ▼
          dedupe · rank · stream to the grid
                        │
                   user pins
                        ▼ Generate
          prompt synthesis, then fal kontext/max/multi
          with the pinned URLs as image_urls
                        ▼
          final image + transcript + the prompt
```

Two properties matter more than any single technology.

**The distiller is a cost gate.** Cala bills per query. Pioneer's GLiNER2 is an encoder model that returns typed visual attributes in milliseconds at $0.15/1M tokens, so it runs on every pause — and only a *material* change in those attributes is allowed to spend a Cala query. That is what makes a continuous, speech-driven loop affordable.

**Pins are functional.** A pinned image is not a mood-board sticker that gets quietly summarised into an adjective. Its URL goes to fal as a real conditioning input via `flux-pro/kontext/max/multi`. Unpin an image, regenerate, and the output visibly changes.

## What Cala does here

Worth stating plainly, because it is the most interesting constraint in the build.

**Cala returns no images.** There is no image, thumbnail, logo or media field anywhere in its OpenAPI schema, and its docs explicitly position it as the opposite of web search: *"Web search APIs crawl the open web and return URLs, scraped text, and HTML fragments… Cala is different. It's a verified entity graph."*

What Cala does is decide **what you are talking about** and **which sources are authoritative about it**. It resolves a messy spoken mention into a canonical typed entity, then returns the specific article pages it cites as evidence. We extract the reference images from **those** pages. So every Lane A image arrives with a publisher and a source document attached — something keyword image search structurally cannot offer.

Wikimedia Commons and Openverse run as a co-equal second lane, because most spoken visual thinking is not finance, legal or HR. Candidates are badged **cited** or **open** in the UI. Being explicit about where an image came from is what makes the Cala integration honest and worth advertising.

## Technologies

The rules require three partner technologies. We use six, and each does work nothing else could.

| | | Role |
|---|---|---|
| **OpenAI** | — | Live transcription (`gpt-live-transcribe`, WebRTC, true incremental deltas) and prompt synthesis at Generate. Deltas are what make the screen feel alive. |
| **Cala** | [cala.ai](https://www.cala.ai) | Entity resolution from speech, cited-source discovery, and salience — which fact is worth illustrating. |
| **Pioneer** (Fastino Labs) | [pioneer.ai](https://pioneer.ai) | GLiNER2 extracts typed visual attributes from speech on every pause, and gates spend. Optional PII redaction before anything leaves. |
| **fal** | [fal.ai](https://fal.ai) | The final image, conditioned on pinned references. |
| **Aikido** | [aikido.dev](https://www.aikido.dev) | Zen runtime firewall, CI gating, safe-chain, live security panel. We fetch arbitrary URLs from the open web — SSRF protection is a real requirement here. |
| **Entire** | [entire.io](https://entire.io) | Every commit bound to the agent session that produced it. |

Exact endpoints, auth headers, model ids, gotchas and what each vendor leaves undocumented: [`docs/PARTNERS.md`](docs/PARTNERS.md).

## Stack

**Frontend** — Vite 7, React 19, TypeScript strict, Zustand, Motion, Tailwind CSS v4, shadcn/ui, Biome. One screen, four phases (`idle → listening → converging → generated`), so no router. Audio goes browser→OpenAI directly over WebRTC using a short-lived ephemeral token our backend mints; raw audio never touches our server.

**Backend** — Python 3.13, FastAPI (WebSocket for the live channel), Pydantic v2, SQLAlchemy 2.0 async, PostgreSQL 17, Redis 7, httpx, selectolax, Pillow + imagehash, structlog, ruff, mypy strict, managed by `uv`. No task queue — `asyncio.TaskGroup` for the discovery fan-out, fal's own queue for slow work.

**Monorepo** — pnpm 10 workspaces + Turborepo.

Every decision and every rejected alternative: [`docs/STACK.md`](docs/STACK.md).

## Setup

**Prerequisites:** Node 22, pnpm 10, Python 3.13, uv, Docker.

```bash
git clone git@github.com:<org>/glia.git && cd glia

# supply-chain guard, before any install
curl -fsSL https://github.com/AikidoSec/safe-chain/releases/latest/download/install-safe-chain.sh | sh

pnpm install --frozen-lockfile
cd apps/api && uv sync --frozen && cd ../..

cp .env.example .env        # fill in the keys — see below

docker compose -f infra/docker-compose.yml up -d
cd apps/api && uv run alembic upgrade head && cd ../..

pnpm dev
```

Web on http://localhost:5173, API on http://localhost:8000, OpenAPI docs at http://localhost:8000/docs.

**Microphone access requires a secure context.** `localhost` counts; a deployed build needs HTTPS.

### Keys

| Variable | Where |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com — event credits are claimable from the hackathon page |
| `CALA_API_KEY` | https://console.cala.ai/api-keys |
| `PIONEER_API_KEY` | https://agent.pioneer.ai/api-keys |
| `FAL_KEY` | https://fal.ai/dashboard/keys — use an **API**-scoped key, not `ADMIN` |
| `AIKIDO_TOKEN` | https://app.aikido.dev/runtime/services → Add app → Generate token |
| `AIKIDO_API_CLIENT_ID` / `_SECRET` | Aikido settings → public API |

All server-side only. `apps/web` gets no provider credentials — anything prefixed `VITE_` is compiled into the public bundle. The browser's only credential is the 600-second OpenAI ephemeral token.

### Optional but recommended

```bash
entire enable -y --agent claude-code

curl -fsSL https://raw.githubusercontent.com/AikidoSec/pre-commit/6cc79e039ee78b206520f143d618a44665c904b3/installation-samples/install-global/install-aikido-hook.sh | bash
```

## Commands

```bash
pnpm dev          # everything, watch mode
pnpm build        # cached Turborepo build
pnpm lint         # Biome
pnpm typecheck    # tsc --noEmit
pnpm test         # Vitest
pnpm gen:api      # regenerate the typed API client from OpenAPI

cd apps/api
uv run ruff check --fix .
uv run mypy .
uv run pytest
uv run alembic upgrade head
```

## Security

Glia makes outbound requests to arbitrary URLs discovered from the open web and decodes whatever images it finds there. That is a textbook SSRF and malformed-media surface, and it is treated as the primary threat rather than an afterthought: host allowlisting, private-IP and redirect rejection, content-type and size caps before decode, and Aikido Zen blocking SSRF at runtime. The browser holds no long-lived credentials. CI gates on new critical dependency findings, and safe-chain intercepts both pnpm and uv installs.

Threat model, controls, and an honest list of what we are **not** doing: [`docs/SECURITY.md`](docs/SECURITY.md).

Found something? Open a private advisory, not a public issue.

## Documentation

| | |
|---|---|
| [`docs/HACKATHON.md`](docs/HACKATHON.md) | Event facts, rules, deliverables, timeline |
| [`docs/STACK.md`](docs/STACK.md) | Architecture and every technology decision |
| [`docs/PARTNERS.md`](docs/PARTNERS.md) | Complete API reference for all six technologies |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model and controls |
| [`docs/INSTRUCTIONS.md`](docs/INSTRUCTIONS.md) | Conventions, workflow, definition of done, demo script |
| [`AGENTS.md`](AGENTS.md) | Operating rules for AI coding agents |
| [`ENTIRE_CHALLENGE.md`](ENTIRE_CHALLENGE.md) | Entire checkpoint workflow for the side challenge |

## Team

Yazide · Sergio Pulido · Lluís Francesc Collell Erra

Three of us, equal call on every decision.

## Name

Glial cells do not fire. They connect, insulate and route — the tissue that makes signal possible. Between a half-formed thought and an image, that is the job.

## License

MIT. See [`LICENSE`](LICENSE).
