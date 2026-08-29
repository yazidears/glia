# Summer Lock-In launchpad

Prepared for **{Tech: Europe} x Cala Hackathon — The Summer Lock-In** on Saturday, 29 August 2026.

Start here:

```bash
./scripts/preflight.sh
```

Then read, in order:

1. [`HACKATHON_RUNBOOK.md`](HACKATHON_RUNBOOK.md) — arrival, schedule, build gates, and packing list.
2. [`IDEAS.md`](IDEAS.md) — three scoped concepts, with the safest option first.
3. [`PITCH.md`](PITCH.md) — the demo narrative and fallback script.
4. [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) — fill this in during the first 20 minutes after the opening.
5. [`ENTIRE_CHALLENGE.md`](ENTIRE_CHALLENGE.md) — checkpoint workflow for the side challenge.

The folder deliberately does not contain a product scaffold yet. The event brief and sponsor APIs are handed out on the day; choosing the final product before hearing them would create rework. Once the brief is known, use Bun as the default JavaScript runtime for fast setup; Node and npm are also available.

## Non-negotiable ship gates

- One complete, visible user journey before adding a second feature.
- Synthetic demo data and a deterministic fallback path.
- No secrets in source, screenshots, Git history, or recorded sessions.
- Feature freeze at 17:30; demo rehearsal starts no later than 18:00.
- No push, deployment, or public repository without Yazide's explicit approval.
