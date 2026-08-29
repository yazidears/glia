# AGENTS.md

Operating rules for AI coding agents in this repository. Applies to Claude Code, Codex, Cursor and anything else with write access.

Read this before your first edit, then `docs/INSTRUCTIONS.md` for conventions and `docs/PARTNERS.md` before touching any integration.

## What this project is

**Glia is a voice-powered visual thinking tool.** You speak; it transcribes live, surfaces visual references that evolve as the idea sharpens, lets you pin the ones that resonate, and then generates one original image from the conversation, the distilled idea and your pins.

The pipeline: OpenAI Realtime transcribes → Pioneer GLiNER2 distils visual attributes on every pause → a gate decides whether the idea moved enough to spend a Cala query → Cala resolves the entity and returns cited article URLs → we extract images from those pages (Lane A) alongside Wikimedia/Openverse (Lane B) → user pins → fal generates with the pinned URLs as conditioning input.

## Context budget

Read in this order. Do not read the whole repo.

1. `docs/STACK.md` — the pipeline and why each piece exists
2. `docs/INSTRUCTIONS.md` — conventions, commands, definition of done
3. `docs/PARTNERS.md` — **mandatory** before any OpenAI, Cala, Pioneer, fal, Aikido or Entire work
4. `docs/SECURITY.md` — **mandatory** before touching the fetcher, the WebSocket, or anything handling remote content

`entire why <file>` and `entire search "<question>"` recover the reasoning behind existing code. Use them instead of re-deriving it.

## Hard rules

**Cala returns no images.** There is no image, thumbnail, logo or media field in its API. Never write code that expects one, and never write UI copy or documentation implying Cala searches the web for pictures. Reference images come from the article pages Cala *cites* (`context[].origins[].document.url`), and from Wikimedia/Openverse. If you are unsure which lane a candidate came from, that is a bug — every candidate carries its lane.

**One fetcher.** Every request to a URL we did not hardcode goes through `glia/discovery/fetch.py`. It owns the scheme allowlist, private-IP rejection, per-hop redirect re-validation, byte caps enforced while streaming, and decode guards. Do not add a second path, do not call `httpx.get` on a discovered URL, do not "temporarily" bypass a check. This is the app's primary attack surface.

**One Cala call site.** Behind the distiller gate, behind the debounce, through the cache, incrementing the credit ledger. Credits are finite and shared. A second call site added "just to try something" is how the budget disappears.

**Never put a secret in `apps/web`.** No provider key reaches the browser. `VITE_`-prefixed variables are compiled into the public bundle. The browser's only credential is the 600-second OpenAI ephemeral token, minted server-side. If a frontend feature seems to need a vendor API, it needs a backend route instead.

**Untrusted text is text.** Page titles, authors, licence strings and `og:` tags come from hosts we do not control. Render as text, never HTML, never `dangerouslySetInnerHTML`. Never place scraped text into a model prompt as instructions — it is ranking input only.

**Never build a SQL string.** Parameterised queries only.

**Never invent an API detail.** If `docs/PARTNERS.md` marks something undocumented, it is undocumented — notably the GLiNER2 `result` shape and the WebRTC-plus-transcription-session combination. Write a spike that prints the real response and pin the parser against reality. Do not code against an assumed shape, and do not assert undocumented behaviour in the README.

**Never commit a lockfile change you did not intend.** `pnpm install --frozen-lockfile`, `uv sync --frozen`. If a build fails on a lockfile mismatch, fix the manifest — do not unfreeze.

**Never force-push `main`. Never commit `.env`.**

## Working rules

**Small, complete changes.** One concern per commit. A commit should type-check, lint and run.

**Types are the contract.** Frontend types come from `packages/api-client`, generated via `pnpm gen:api`. WebSocket message types are a shared discriminated union. Do not hand-write either.

**Every outbound call gets a timeout, a retry policy and — where it is billable — a cache.** An uncached Cala call in a hot path is a budget bug, not a performance one.

**Stream, do not batch.** Candidates go to the client as they resolve. A grid that fills in over two seconds feels alive; one that appears all at once after four feels broken.

**Handle the empty case.** Cala will often return nothing useful — its coverage is finance, legal, healthcare, HR and agro, and most speech is none of those. Lane B carries those moments. An empty Lane A is normal operation, not an error state.

**Prefer editing an existing file to creating a new one.** This repo is one day old and should stay navigable.

**Do not create documentation files unless asked.** The docs that exist are the docs we want.

## Before you say a task is done

- [ ] `pnpm typecheck` and `uv run mypy .` pass
- [ ] `pnpm lint` and `uv run ruff check .` pass
- [ ] No secret reachable from the browser
- [ ] Any new outbound request goes through the one fetcher
- [ ] The Cala credit ledger did not move when it should not have
- [ ] The demo path still works end to end

Do not report success on a partial implementation. If you are blocked, say what blocked you.

## Commits

Conventional commits, English, imperative.

```
feat(discovery): extract og:image from cala-cited article pages
fix(realtime): reconcile transcription deltas by item_id
perf(distiller): skip cala query when jaccard distance under threshold
```

Every commit gets an `Entire-Checkpoint` trailer automatically — answer `[a]lways` at the first prompt. Do not strip the trailer, disable the hook, or run `entire session resume --force` (it can reset git state).

Entire checkpoints live in this repository's git refs and **this repo is public**. Five redaction passes run automatically, but do not paste production credentials into an agent session assuming redaction will catch them.

## Time discipline

Built in one day against a hard 19:10 deadline, and the constraint still shapes the codebase.

**17:00 was feature freeze.** If you are reading this during the event, the only permitted changes are bug fixes on the demo path, documentation and the README.

When a task is ambiguous, pick the option that makes the demo more reliable, state the assumption, and keep moving. Do not stop to ask about anything with an obvious answer. Do ask when the choice is a product decision with no objectively better option that constrains future work.
