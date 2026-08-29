# Hackathon operating rules

This repository is for a one-day hackathon. Optimize for a reliable live demo, not architectural completeness.

## Deadline and sequence

- Competition opt-in deadline: 19:00 Europe/Madrid.
- Live demos: 20:00.
- Stop adding features at 17:30.
- Keep the demo path runnable after every meaningful change.

## Build discipline

1. Define one user, one painful moment, one input, and one visible outcome.
2. Implement the vertical demo slice before secondary screens or integrations.
3. Every external provider must have a local fixture or deterministic mock.
4. Keep setup to one command and document required environment variable names in `.env.example`; never store values.
5. Use synthetic data unless the user explicitly approves real data.
6. Run the app and exercise the actual demo flow before calling work complete.
7. Make logical local commits so Entire can capture checkpoints. Do not push, deploy, open a PR, or make a repository public without Yazide's explicit approval.

## Local environment

- Prefer Bun for fast setup. Node and npm were repaired and are available as a fallback.
- `bun`, `node`, `npm`, `pnpm`, `git`, `gh`, Codex CLI, and the Entire CLI are available.
- Do not replace system runtimes during the event unless the working Bun and Node paths both fail.

## Sponsor integrations

Use sponsor products only where they materially improve the demo:

- OpenAI: multimodal understanding, structured extraction, reasoning, or voice.
- Cala: agent data/entity layer; confirm the provided API and examples with the sponsor before coding against it.
- Entire: record logical build checkpoints and make development provenance visible.
- Pioneer/Fastino: use only if its on-site model capability has a clear role.
- Fal: use only when generated media is part of the user outcome.
- Aikido: scan the final code and dependency surface before the demo.

Do not fabricate APIs or force every sponsor into the product.

## Demo quality bar

- The first screen states the problem in one sentence.
- The primary action is obvious.
- The result appears in under 15 seconds or shows honest progress.
- The presenter can finish the core story in 90 seconds.
- A recorded backup and static result exist before 18:30.
