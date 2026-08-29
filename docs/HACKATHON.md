# {Tech: Europe} x Cala Hackathon — The Summer Lock-In

Event reference for team **glia**. Everything on this page is event fact, not project design.

## Event

| | |
|---|---|
| Event | {Tech: Europe} x Cala Hackathon \| The Summer Lock-In |
| Date | Saturday, 29 August 2026 |
| Location | Barcelona |
| Event timezone | Europe/Berlin (CEST) |
| Event window | 09:30 – 21:00 CEST |
| **Submission deadline** | **19:10 CEST** |
| Team | `glia` — invite code `GV7KRQ`, 3/5 members |
| Members | Yazide (captain, submits), Sergio Pulido, Lluís Francesc Collell Erra |
| Tracks entered | Cala (by Cala), Open Innovation |

## Agenda

| Time (CEST) | Item |
|---|---|
| 09:30 | Doors open & networking |
| 10:00 | Opening & matchmaking |
| 12:30 | Lunch |
| 19:00 | Competition opt-in deadline & dinner |
| 19:10 | **Submission deadline** |
| 20:00 | Live demos |
| 20:30 | Award ceremony |

## Rules

1. Submit by **19:10**.
2. Team of **max. 5 people**. We are 3.
3. Use **minimum 3 partner technologies**. We use **6** — OpenAI, Cala, Pioneer (Fastino Labs), fal, Aikido, Entire.
4. Project must be **created newly at this hackathon**. Boilerplates are allowed. The repo was initialised empty on 29 Aug 2026; every commit is inside the event window and every commit carries an Entire checkpoint proving it.

## What must be submitted

### Project presentation
- 2-minute recorded video demo (Loom or equivalent)
- Detailed explanation of the solution
- Live walkthrough of the key features

### Open source repository
- Public GitHub repository with full source code
- Comprehensive README with setup & installation steps
- Documentation of all APIs, frameworks & tools used
- Enough technical docs for thorough jury evaluation

## Competition mode

**Stage 1 — pre-selection.** Free choice of topic. 5 finalist teams advance: 2 Open Innovation winners + 3 Cala winners. Judged on **creativity & technical complexity**, with a **bonus for partner tech**.

**Stage 2 — finalist stage.** All finalists present live, 5 minutes per team, before jury and audience. Jury then picks the top 3.

## Tracks

| Track | Prize |
|---|---|
| Cala (by Cala) | Trip to another hackathon |
| Open Innovation | Qualification for the final |

### Side challenges

| Challenge | Prize | Our position |
|---|---|---|
| Aikido | 1000 € | Zen blocking SSRF against a fetcher that requests URLs the open web chose — plus CI gating, safe-chain, secrets hook, and a live security panel inside the app |
| fal — Best Use of fal | 1000 $ fal credits | `flux-pro/kontext/max/multi` with pinned reference URLs as `image_urls`, so pinning genuinely conditions the output |
| Fastino Labs — Best Use of Pioneer | 500 € | GLiNER2 distils typed visual attributes from live speech on every pause, and gates all downstream spend |
| Entire | x3 $425 gift cards, x2 PS5 | Every commit carries a checkpoint; `entire why` is part of the demo |

### Finalist stage prizes

| Place | Prize |
|---|---|
| 1st | $2.5k OpenAI credits |
| 2nd | $1.5k OpenAI credits |
| 3rd | $1k OpenAI credits |

## Technology partners

| Partner | What it is | Link |
|---|---|---|
| Cala | Verified, structured, cited data for AI agents | https://www.cala.ai |
| OpenAI | Frontier models and realtime transcription (credits claimable from the event page) | — |
| fal | Generative media platform (image, video, audio) | https://fal.ai |
| Fastino Labs / Pioneer | Inference API with routing + adaptive retraining | https://pioneer.ai |
| Entire | Agent sessions, prompts and tool calls stored with your commits | https://entire.io |
| Aikido | Unified app + cloud security, and Zen runtime protection | https://www.aikido.dev |

## Submission checklist

Tick these before 19:00, not 19:09.

- [ ] Repo is **public** on GitHub
- [ ] `README.md` — one-command setup, verified on a clean clone
- [ ] `docs/PARTNERS.md` — every API, framework and tool documented
- [ ] `docs/ARCHITECTURE` section current (in `docs/STACK.md`)
- [ ] `docs/SECURITY.md` — threat model + controls
- [ ] `.env.example` complete, **no real keys anywhere in git history**
- [ ] Aikido scan green, GitHub Action visible in the repo
- [ ] `entire status` clean; checkpoints pushed
- [ ] Loom demo recorded, ≤ 2 minutes, link in README
- [ ] Deployed URL live and reachable from a phone
- [ ] Captain (Yazide) has submitted the form
- [ ] Competition opt-in done before 19:00

## Working timeline

Back-calculated from the 19:10 deadline. Freeze times are hard.

| Time | Milestone |
|---|---|
| 12:30 | Scaffold done: monorepo boots, web + api talk to each other |
| 12:30 | Three spikes reported: WebRTC transcription, GLiNER2 shape, Cala→og:image hit rate |
| 14:00 | Speech in, transcript live, first candidates in the grid |
| 15:30 | Distiller gate working — grid visibly reorganises when the idea changes |
| 16:30 | Pinning conditions generation; fal returns an image with the synthesised prompt |
| 17:00 | **Feature freeze.** Nothing new after this. |
| 17:30 | Deployed, Aikido green, security dashboard showing real findings |
| 18:00 | Loom recorded |
| 18:30 | README + docs final pass |
| 19:00 | **Submitted.** Opt-in confirmed. |
| 19:10 | Deadline. We are already done. |
| 20:00 | Live demo — 5 min script rehearsed twice |

## Judging translation

The jury scores **creativity & technical complexity**, plus partner-tech bonus. Concretely that means the demo must show, in order:

1. The problem in one sentence — people can describe how an image should feel but cannot write the prompt.
2. The product doing something no other team's does — references that reorganise live as a spoken idea changes direction.
3. The depth behind it — six partner integrations that each do real work, not six logos on a slide.
4. The proof — unpin an image, regenerate, and the output visibly changes. Then Zen blocking a hostile URL and `entire why` on the fetcher.
